import asyncio
from typing import List, Dict, Any, Optional
from uuid import uuid4
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
import json

# This class appears to be unused based on the tracebacks,
# but is kept as part of the file structure you provided.
class Task:
    """
    A task to be executed by the agent.
    """
    def __init__(self, tool: BaseTool, tool_input: Dict[str, Any], id: str, depends_on: Optional[List[str]] = None):
        self.id = id
        self.tool = tool
        self.input = tool_input
        self.depends_on = depends_on or []
        self.status = 'ready'
        self.output = None

    def invoke(self, state: Dict[str, Any], config: RunnableConfig) -> ToolMessage:
        """Invoke the tool and return the output as a ToolMessage."""
        try:
            # Substitute inputs from the state
            substituted_input = self.substitute_inputs(self.input, state)
            output = self.tool.invoke(substituted_input, config)
            self.status = 'done'
            self.output = output
            # Pass the tool's name in the ToolMessage
            return ToolMessage(content=str(output), name=self.tool.name, tool_call_id=self.id)
        except Exception as e:
            self.status = 'error'
            self.output = str(e)
            return ToolMessage(content=f"Error: {e}", name=self.tool.name, tool_call_id=self.id)

    def substitute_inputs(self, tool_input: Any, state: Dict[str, Any]) -> Any:
        """Recursively substitute task outputs in the input."""
        if isinstance(tool_input, str) and tool_input.startswith('$'):
            task_id = tool_input[1:]
            if task_id in state:
                return state[task_id]
        elif isinstance(tool_input, dict):
            return {k: self.substitute_inputs(v, state) for k, v in tool_input.items()}
        elif isinstance(tool_input, list):
            return [self.substitute_inputs(i, state) for i in tool_input]
        return tool_input

# MODIFIED FUNCTION
async def _execute_task(task: Dict, state: Dict, config: Dict) -> Optional[ToolMessage]:
    """
    Executes a single task and returns a ToolMessage or None for join tasks.
    """
    if task['tool'] == 'join':
        return None

    try:
        # Execute the tool with its arguments
        result = await asyncio.to_thread(task['tool'].invoke, task['args'])

        # --- START OF NEW LOGIC ---
        # If the result is a list of dicts (like from Tavily), extract the content.
        if isinstance(result, list) and all(isinstance(i, dict) for i in result):
            # This specifically targets search results to make them readable for the joiner
            content = "\n".join([item.get("content", "") for item in result])
        elif isinstance(result, list):
            # Fallback for other kinds of lists
            content = json.dumps(result)
        else:
            # For any other data type
            content = str(result)
        # --- END OF NEW LOGIC ---
        
        # Return a ToolMessage for LangGraph
        return ToolMessage(
            content=content, 
            name=task['tool'].name, 
            # Use a more robust ID format and embed the original arguments
            tool_call_id=f"call_{task['idx']}",
            additional_kwargs={"args": task['args']}
        )

    except Exception as e:
        # In case of an error during tool execution
        return ToolMessage(
            content=f"Error: {e}", 
            name=getattr(task.get('tool'), 'name', 'unknown_tool'), 
            tool_call_id=f"call_{task['idx']}"
        )

# MODIFIED FUNCTION
async def _schedule_tasks_async(tasks: List[Dict], config: RunnableConfig) -> List[BaseMessage]:
    """
    Main coroutine to schedule and execute tasks concurrently.
    """
    print("Inspecting tasks:", tasks)
    task_map = {task['idx']: task for task in tasks}
    task_outputs: Dict[str, Any] = {}
    pending_tasks = list(tasks)
    messages = []
    
    while pending_tasks:
        ready_tasks = [
            task for task in pending_tasks
            if all(dep in task_outputs for dep in task['dependencies'])
        ]
        
        if not ready_tasks:
            # Handle deadlock or finished execution
            break

        # Execute ready tasks concurrently
        results = await asyncio.gather(
            *[_execute_task(task, task_outputs, config) for task in ready_tasks]
        )
        
        # Process results
        for task, tool_message in zip(ready_tasks, results):
            # Store output for other tasks to use. Join tasks will have None.
            if tool_message:
                task_outputs[task['idx']] = tool_message.content
            else:
                task_outputs[task['idx']] = None

            # Only append actual ToolMessages to the final list for LangGraph
            if tool_message is not None:
                messages.append(tool_message)

        # Remove completed tasks from the pending list
        pending_tasks = [task for task in pending_tasks if task not in ready_tasks]
        
    return messages


def schedule_tasks(scheduler_input: Dict[str, Any], config: RunnableConfig) -> List[BaseMessage]:
    """
    Synchronous wrapper for the async task scheduler.
    """
    # The input from the planner is a generator, so convert it to a list to allow iteration
    tasks = list(scheduler_input["tasks"]) 
    return asyncio.run(_schedule_tasks_async(tasks, config))

# This runnable class wraps the scheduling logic for LangGraph
class TaskScheduler(Runnable):
    def invoke(self, input: Dict[str, Any], config: Optional[RunnableConfig] = None) -> List[BaseMessage]:
        return schedule_tasks(input, config or {})

    async def ainvoke(self, input: Dict[str, Any], config: Optional[RunnableConfig] = None) -> List[BaseMessage]:
        # The input from the planner is a generator, so convert it to a list
        tasks = list(input["tasks"])
        return await _schedule_tasks_async(tasks, config or {})


# Instantiate the scheduler for use in your graph
task_scheduler = TaskScheduler()