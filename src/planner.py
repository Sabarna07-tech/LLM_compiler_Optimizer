from typing import Sequence, List, Dict

from langchain import hub
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    BaseMessage,
    ToolMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableBranch
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from src.output_parser import LLMCompilerPlanParser, Task

def create_planner(
    llm: BaseChatModel, tools: Sequence[BaseTool], base_prompt: ChatPromptTemplate
):
    tool_descriptions = "\\n".join(
        f"{i+1}. {tool.name}: {tool.description}\\n" # Use tool.name for consistency
        for i, tool in enumerate(tools)
    )
    planner_prompt = base_prompt.partial(
        replan="",
        num_tools=len(tools) + 1,
        tool_descriptions=tool_descriptions,
    )
    # MODIFIED: Added more explicit instructions to the replanner prompt
    replanner_prompt = base_prompt.partial(
        replan=' - You are given "Previous Plan" which is the plan that the previous agent created along with the execution results '
        "(given as Observation) of each plan and a general thought (given as Thought) about the executed results."
        'You MUST use these information to create the next plan under "Current Plan".\\n'
        ' - When starting the Current Plan, you should start with "Thought" that outlines the strategy for the next plan.\\n'
        " - In the Current Plan, you should NEVER repeat the actions that are already executed in the Previous Plan.\\n"
        " - Analyze the Observation from the last failed attempt to understand the error. Do not repeat the same failed action. Pay close attention to the required arguments for each tool.\\n"
        " - You must continue the task index from the end of the previous one. Do not repeat task indices.",
        num_tools=len(tools) + 1,
        tool_descriptions=tool_descriptions,
    )

    def should_replan(state: List[BaseMessage]):
        return isinstance(state[-1], SystemMessage)

    def wrap_messages(state: List[BaseMessage]) -> Dict[str, List[BaseMessage]]:
        return {"messages": state}

    def wrap_and_get_last_index(state: List[BaseMessage]) -> Dict[str, List[BaseMessage]]:
        next_task = 0
        for message in state[::-1]:
            if isinstance(message, ToolMessage):
                if message.tool_call_id and message.tool_call_id.startswith('call_'):
                    try:
                        task_id = int(message.tool_call_id.split('_')[-1])
                        next_task = task_id + 1
                        break
                    except (ValueError, IndexError):
                        continue
        
        replan_context = f"Begin the Current Plan. Continue task numbering from {next_task}."
        if state and isinstance(state[-1], SystemMessage):
             state[-1].content = f"{state[-1].content}\n{replan_context}"
        else:
            state.append(SystemMessage(content=replan_context))

        return {"messages": state}

    return (
        RunnableBranch(
            (should_replan, wrap_and_get_last_index | replanner_prompt),
            wrap_messages | planner_prompt,
        )
        | llm
        | LLMCompilerPlanParser(tools=tools)
    )