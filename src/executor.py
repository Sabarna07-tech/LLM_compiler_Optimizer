import re
import time
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any, Dict, Iterable, List, Union
from langchain_core.runnables import chain as as_runnable, RunnableConfig # Import RunnableConfig
from langchain_core.messages import FunctionMessage, BaseMessage
from langchain_core.tools import BaseTool
from typing_extensions import TypedDict
from src.output_parser import Task # Relative import

def _get_observations(messages: List[BaseMessage]) -> Dict[int, Any]:
    # Get all previous tool responses
    results = {}
    for message in messages[::-1]:
        if isinstance(message, FunctionMessage):
            # Ensure idx is an integer and convert content if needed
            idx = int(message.additional_kwargs["idx"])
            results[idx] = message.content # Store content as is, resolution happens later
    return results


class SchedulerInput(TypedDict):
    messages: List[BaseMessage]
    tasks: Iterable[Task]


def _execute_task(task: Task, observations: Dict[int, Any], config: RunnableConfig) -> Any:
    tool_to_use = task["tool"]
    
    # If the tool is a string (e.g., 'join'), just return it.
    if isinstance(tool_to_use, str):
        return tool_to_use

    args = task["args"]
    resolved_args = {}

    try:
        if isinstance(args, dict):
            for key, val in args.items():
                resolved_args[key] = _resolve_arg(val, observations)
        else:
            resolved_args = _resolve_arg(args, observations)
            
    except Exception as e:
        return (
            f"ERROR(Failed to resolve arguments for {tool_to_use.name} with args {args}. "
            f"Error: {repr(e)})"
        )
        
    try:
        # Invoke the tool with resolved arguments and config
        return tool_to_use.invoke(resolved_args, config)
    except Exception as e:
        import traceback
        return (
            f"ERROR(Failed to call {tool_to_use.name} with args {args}. "
            + f" Args resolved to {resolved_args}. Error: {repr(e)}\n{traceback.format_exc()})"
        )


def _resolve_arg(arg: Any, observations: Dict[int, Any]) -> Any:
    """Recursively resolve argument values, substituting ${ID} with observed results."""
    ID_PATTERN = r"\$\{(\d+)\}"

    if isinstance(arg, str):
        # If the string contains a single ${ID} and nothing else, return the direct observation
        match = re.fullmatch(ID_PATTERN, arg)
        if match:
            idx = int(match.group(1))
            return observations.get(idx, arg) # Return original arg if not found in observations
        
        # Otherwise, substitute all ${ID} occurrences
        def replace_match(match_obj):
            idx = int(match_obj.group(1))
            return str(observations.get(idx, match_obj.group(0))) # Replace with original placeholder if not found
        
        return re.sub(ID_PATTERN, replace_match, arg)

    elif isinstance(arg, list):
        return [_resolve_arg(item, observations) for item in arg]
    
    elif isinstance(arg, dict):
        return {k: _resolve_arg(v, observations) for k, v in arg.items()}
    
    else:
        return arg


@as_runnable
def schedule_task(task_inputs: Dict[str, Any], config: RunnableConfig) -> None:
    """Execute a single task and store its observation."""
    task: Task = task_inputs["task"]
    observations: Dict[int, Any] = task_inputs["observations"]
    
    # Execute the task
    observation = _execute_task(task, observations, config)
    
    # Store the observation. This is thread-safe as dictionary assignment is atomic.
    observations[task["idx"]] = observation


def schedule_pending_task(
    task: Task, observations: Dict[int, Any], config: RunnableConfig, retry_after: float = 0.2
):
    """Schedule a task that has dependencies, waiting for them to be met."""
    while True:
        deps = task["dependencies"]
        # Check if all dependencies are satisfied
        if deps and (any(dep not in observations for dep in deps)):
            time.sleep(retry_after)
            continue
        
        # Dependencies met, execute the task
        schedule_task.invoke({"task": task, "observations": observations}, config)
        break


@as_runnable
def schedule_tasks(scheduler_input: SchedulerInput, config: RunnableConfig) -> List[FunctionMessage]:
    """Group the tasks into a DAG schedule and execute them concurrently."""
    tasks = list(scheduler_input["tasks"]) # Convert iterable to list for multiple passes
    
    # Get initial observations from previous messages in the state
    messages = scheduler_input["messages"]
    observations = _get_observations(messages)
    
    # Store original keys to identify new observations
    original_observation_keys = set(observations.keys())

    futures = []
    
    with ThreadPoolExecutor() as executor:
        for task in tasks:
            deps = task["dependencies"]
            
            # Check if task is a 'join' tool. If so, it will be handled by the joiner node.
            if isinstance(task["tool"], str) and task["tool"] == "join":
                # Ensure join task has all preceding tasks as dependencies
                task['dependencies'] = list(range(1, task['idx']))
                # No need to execute 'join' here; its results are just
                # the collection of previous observations.
                # So, we simply schedule it to wait for its dependencies
                futures.append(
                    executor.submit(
                        schedule_pending_task, task, observations, config 
                    )
                )
                continue

            if (deps and any(dep not in observations for dep in deps)):
                # Task has dependencies not yet satisfied, submit to wait pool
                futures.append(
                    executor.submit(
                        schedule_pending_task, task, observations, config
                    )
                )
            else:
                # No dependencies or all dependencies satisfied, execute immediately
                futures.append(
                    executor.submit(
                        schedule_task.invoke, dict(task=task, observations=observations), config
                    )
                )

        # Wait for all submitted tasks (including those waiting for dependencies) to complete
        wait(futures)
        
    # Prepare messages for the next state
    tool_messages = []
    # Sort observations by index for consistent message ordering
    sorted_new_observation_keys = sorted(observations.keys() - original_observation_keys)

    for k in sorted_new_observation_keys:
        # Find the task associated with this observation key
        found_task = next((t for t in tasks if t['idx'] == k), None)

        if found_task and found_task['tool'] != 'join': # Do not create FunctionMessage for 'join' itself
            name = found_task['tool'].name if isinstance(found_task['tool'], BaseTool) else str(found_task['tool'])
            task_args = found_task['args']
            obs_content = observations[k]

            tool_messages.append(
                FunctionMessage(
                    name=name,
                    content=str(obs_content),
                    additional_kwargs={"idx": k, "args": task_args},
                    tool_call_id=str(k), # tool_call_id should be string
                )
            )
        elif found_task and found_task['tool'] == 'join':
            # For 'join' task, we need to collect all previous observations
            # and pass them to the joiner. This is done implicitly when
            # the joiner node is invoked, as it gets the full 'messages' state.
            # We don't need a FunctionMessage for the join task itself here.
            pass


    return tool_messages
