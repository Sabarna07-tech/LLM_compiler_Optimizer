

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
ID_PATTERN = r"\$\{(\d+)\}"
SINGLE_ID_PATTERN = r"^\$(\d+)$"
END_OF_PLAN = "<END_OF_PLAN>"

def _ast_parse(arg: str) -> Any:
    try:
        return ast.literal_eval(arg)
    except (ValueError, SyntaxError):
        return arg

def _parse_llm_compiler_action_args(args: str, tool: Union[str, BaseTool]) -> Dict[str, Any]:
    if args == "":
        return {}
    parsed_args = {}
    arg_pairs = re.findall(r'(\w+)=(.*?)(?:, (?=\w+=)|$)', args)
    for key, value_str in arg_pairs:
        value_str = value_str.strip()
        if re.match(ID_PATTERN, value_str):
            parsed_args[key] = value_str
        elif value_str.startswith('[') and value_str.endswith(']'):
            try:
                list_elements = [_ast_parse(s.strip()) for s in value_str[1:-1].split(',')]
                parsed_args[key] = list_elements
            except Exception:
                parsed_args[key] = value_str
        else:
            parsed_args[key] = _ast_parse(value_str)
    return parsed_args

def _get_dependencies_from_graph(idx: int, tool_name: str, args: Dict[str, Any]) -> List[int]:
    if tool_name == "join":
        return list(range(1, idx))
    
    dependencies = []
    for arg_value in args.values():
        if isinstance(arg_value, str):
            matches = re.findall(ID_PATTERN, arg_value)
            dependencies.extend([int(match) for match in matches])
        elif isinstance(arg_value, list):
            for item in arg_value:
                if isinstance(item, str):
                    matches = re.findall(ID_PATTERN, item)
                    dependencies.extend([int(match) for match in matches])
    return sorted(list(set([dep for dep in dependencies if dep < idx])))

class Task(TypedDict):
    idx: int
    tool: Union[BaseTool, str]
    args: Dict[str, Any]
    dependencies: List[int]
    thought: Optional[str]

class LLMCompilerPlanParser(BaseTransformOutputParser[Dict[str, Any]], extra="allow"):
    tools: List[BaseTool]

    def _transform(self, input: Iterator[Union[str, BaseMessage]]) -> Iterator[Task]:
        texts = []
        thought = None
        current_idx = 0
        for chunk in input:
            text = chunk if isinstance(chunk, str) else str(chunk.content)
            for task, new_thought in self.ingest_token(text, texts, thought, current_idx):
                if task:
                    current_idx = task['idx']
                    yield task
                thought = new_thought
        
        remaining_text = "".join(texts).strip()
        if remaining_text:
            task, final_thought = self._parse_task(remaining_text, thought, current_idx + 1)
            if task:
                yield task

    def parse(self, text: str) -> List[Task]:
        return list(self._transform([text]))

    def stream(self, input: Union[str, BaseMessage], config: Optional[RunnableConfig] = None, **kwargs: Any) -> Iterator[Task]:
        yield from self.transform([input], config, **kwargs)

    def ingest_token(self, token: str, buffer: List[str], thought: Optional[str], current_idx: int) -> Iterator[Tuple[Optional[Task], Optional[str]]]:
        buffer.append(token)
        if "\n" in token:
            buffer_ = "".join(buffer).split("\n")
            suffix = buffer_[-1]
            current_thought = thought
            for line in buffer_[:-1]:
                task, current_thought = self._parse_task(line, current_thought, current_idx + 1)
                if task:
                    yield task, current_thought
            buffer.clear()
            buffer.append(suffix)
            
            if END_OF_PLAN in "".join(buffer):
                remaining_text = "".join(buffer).strip()
                if remaining_text:
                    task, _ = self._parse_task(remaining_text, current_thought, current_idx + 1)
                    if task:
                        yield task, current_thought
                buffer.clear()
        
        yield None, thought

    def _parse_task(self, line: str, thought: Optional[str] = None, next_expected_idx: int = 1) -> Tuple[Optional[Task], Optional[str]]:
        task = None
        if match := re.match(THOUGHT_PATTERN, line):
            thought = match.group(1)
        elif match := re.match(ACTION_PATTERN, line):
            idx_str, tool_name, args_str, _ = match.groups()
            idx = int(idx_str)

            if idx < next_expected_idx:
                print(f"Warning: Parsed task index {idx} is less than expected {next_expected_idx}. Line: {line}")
            
            task = self.instantiate_task_safe(tools=self.tools, idx=idx, tool_name=tool_name, args=args_str, thought=thought)
            thought = None
        return task, thought

    def instantiate_task_safe(self, tools: Sequence[BaseTool], idx: int, tool_name: str, args: Union[str, Any], thought: Optional[str] = None) -> Task:
        # MODIFIED: Add a safeguard for the 'join' tool
        if tool_name == "join":
            tool_obj = "join"
            # Crucially, ignore any arguments the LLM might have hallucinated
            tool_args = {}
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