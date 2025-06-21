import ast
import re
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import BaseMessage
from langchain_core.output_parsers.transform import BaseTransformOutputParser
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from typing_extensions import TypedDict


THOUGHT_PATTERN = r"Thought: ([^\n]*)"
ACTION_PATTERN = r"\n*(\d+)\. (\w+)\((.*)\)(\s*#\w+\n)?"
# $1 or ${1} -> 1
ID_PATTERN = r"\$\{(\d+)\}" # Adjusted to strictly match ${ID} format
SINGLE_ID_PATTERN = r"^\$(\d+)$" # To parse single ID arguments directly
END_OF_PLAN = "<END_OF_PLAN>"


### Helper functions


def _ast_parse(arg: str) -> Any:
    try:
        # Evaluate simple literal expressions like numbers, strings, lists, dicts
        return ast.literal_eval(arg)
    except (ValueError, SyntaxError):
        # If it's not a simple literal, return as is (e.g., for unresolved variables)
        return arg


def _parse_llm_compiler_action_args(args: str, tool: Union[str, BaseTool]) -> Dict[str, Any]:
    """Parse arguments from a string.
    Expects args in the format: key="value", another_key=${id}, list_key=[1,2]
    """
    if args == "":
        return {}

    parsed_args = {}
    # Use a regex to capture key-value pairs
    # This regex is more robust for various argument formats
    arg_pairs = re.findall(r'(\w+)=(.*?)(?:, (?=\w+=)|$)', args)

    for key, value_str in arg_pairs:
        value_str = value_str.strip()
        # Handle cases where value might be a variable reference like ${id}
        if re.match(ID_PATTERN, value_str):
            # Keep it as string for later resolution in executor
            parsed_args[key] = value_str
        elif value_str.startswith('[') and value_str.endswith(']'):
            # Handle list arguments
            try:
                list_elements = [_ast_parse(s.strip()) for s in value_str[1:-1].split(',')]
                parsed_args[key] = list_elements
            except Exception:
                parsed_args[key] = value_str # Fallback if parsing fails
        else:
            # Attempt to parse other literals (strings, numbers, booleans)
            parsed_args[key] = _ast_parse(value_str)
    
    return parsed_args


def default_dependency_rule(idx, args: str):
    # This rule is primarily used to identify dependencies in the raw args string from the LLM.
    # The actual resolution happens in the executor.
    matches = re.findall(ID_PATTERN, args)
    numbers = [int(match) for match in matches]
    return idx in numbers


def _get_dependencies_from_graph(
    idx: int, tool_name: str, args: Dict[str, Any]
) -> List[int]:
    """Get dependencies from a graph."""
    if tool_name == "join":
        # Join depends on all preceding tasks
        return list(range(1, idx))
    
    # Check dependencies within the parsed arguments
    dependencies = []
    for arg_value in args.values():
        if isinstance(arg_value, str):
            # Find all ${ID} patterns in the string argument
            matches = re.findall(ID_PATTERN, arg_value)
            dependencies.extend([int(match) for match in matches])
        elif isinstance(arg_value, list):
            # Recursively check list elements for dependencies
            for item in arg_value:
                if isinstance(item, str):
                    matches = re.findall(ID_PATTERN, item)
                    dependencies.extend([int(match) for match in matches])
    
    # Ensure dependencies are within valid preceding indices
    return sorted(list(set([dep for dep in dependencies if dep < idx])))


class Task(TypedDict):
    idx: int
    tool: Union[BaseTool, str] # 'join' is a string
    args: Dict[str, Any]
    dependencies: List[int]
    thought: Optional[str]


class LLMCompilerPlanParser(BaseTransformOutputParser[Dict[str, Any]], extra="allow"):
    """Planning output parser."""

    tools: List[BaseTool]

    def _transform(self, input: Iterator[Union[str, BaseMessage]]) -> Iterator[Task]:
        texts = []
        thought = None
        current_idx = 0 # Track the current task index being parsed

        for chunk in input:
            text = chunk if isinstance(chunk, str) else str(chunk.content)
            for task, new_thought in self.ingest_token(text, texts, thought):
                if task:
                    current_idx = task['idx'] # Update current_idx based on parsed task
                    yield task
                thought = new_thought # Update thought state
        
        # After the stream ends, parse any remaining buffer content
        remaining_text = "".join(texts).strip()
        if remaining_text:
            # Attempt to parse the last line, even if not newline-terminated
            task, final_thought = self._parse_task(remaining_text, thought, current_idx + 1)
            if task:
                yield task


    def parse(self, text: str) -> List[Task]:
        return list(self._transform([text]))

    def stream(
        self,
        input: Union[str, BaseMessage],
        config: Optional[RunnableConfig] = None,
        **kwargs: Any,
    ) -> Iterator[Task]:
        yield from self.transform([input], config, **kwargs)

    def ingest_token(
        self, token: str, buffer: List[str], thought: Optional[str]
    ) -> Iterator[Tuple[Optional[Task], Optional[str]]]:
        buffer.append(token)
        if "\n" in token:
            buffer_ = "".join(buffer).split("\n")
            suffix = buffer_[-1]
            current_thought = thought
            for line in buffer_[:-1]:
                task, current_thought = self._parse_task(line, current_thought, self._get_next_task_idx(self.tools, line, current_thought)) # Pass a dummy idx for _parse_task
                if task:
                    yield task, current_thought
            buffer.clear()
            buffer.append(suffix)
            
            # Special handling for <END_OF_PLAN>
            if END_OF_PLAN in "".join(buffer):
                # The remaining buffer might contain the join task
                remaining_text = "".join(buffer).strip()
                if remaining_text:
                    task, _ = self._parse_task(remaining_text, current_thought, self._get_next_task_idx(self.tools, remaining_text, current_thought))
                    if task:
                        yield task, current_thought
                buffer.clear() # Clear buffer after processing END_OF_PLAN
        
        # Yield current thought even if no task is produced in this token
        yield None, thought


    def _parse_task(self, line: str, thought: Optional[str] = None, next_expected_idx: int = 1) -> Tuple[Optional[Task], Optional[str]]:
        task = None
        if match := re.match(THOUGHT_PATTERN, line):
            thought = match.group(1)
        elif match := re.match(ACTION_PATTERN, line):
            idx_str, tool_name, args_str, _ = match.groups()
            idx = int(idx_str)

            # Validate if the parsed index is what we expect or a valid continuation
            if idx < next_expected_idx:
                # This could indicate a parsing error or unexpected replan format
                # For robustness, we'll try to proceed but log/handle the anomaly
                print(f"Warning: Parsed task index {idx} is less than expected {next_expected_idx}. Line: {line}")
            
            task = self.instantiate_task_safe(
                tools=self.tools,
                idx=idx,
                tool_name=tool_name,
                args=args_str,
                thought=thought,
            )
            thought = None  # Clear thought after it's consumed by a task
        return task, thought

    def instantiate_task_safe(
        self,
        tools: Sequence[BaseTool],
        idx: int,
        tool_name: str,
        args: Union[str, Any],
        thought: Optional[str] = None,
    ) -> Task:
        if tool_name == "join":
            tool_obj = "join"
        else:
            try:
                tool_obj = tools[[tool.name for tool in tools].index(tool_name)]
            except ValueError as e:
                raise OutputParserException(f"Tool {tool_name} not found.") from e
        
        tool_args = _parse_llm_compiler_action_args(args, tool_obj)
        dependencies = _get_dependencies_from_graph(idx, tool_name, tool_args)

        return Task(
            idx=idx,
            tool=tool_obj,
            args=tool_args,
            dependencies=dependencies,
            thought=thought,
        )

    def _get_next_task_idx(self, tools, line, thought):
        # This is a dummy function. The real index tracking happens in _transform
        # by updating current_idx based on successfully parsed tasks.
        # This function is mainly here to satisfy the signature for self._parse_task call in ingest_token.
        # For actual parsing logic that relies on sequential indices,
        # the parsing needs to occur in a stateful way or after all chunks are received.
        return 1 # Default to 1, as this value is overridden by actual parsed idx.
