from typing import Sequence, List, Dict # Added Dict for type hinting

from langchain import hub
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    BaseMessage,
    FunctionMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableBranch
from langchain_core.tools import BaseTool
# REMOVED: from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI # NEW: ADDED THIS LINE
from src.output_parser import LLMCompilerPlanParser, Task # Relative import

def create_planner(
    llm: BaseChatModel, tools: Sequence[BaseTool], base_prompt: ChatPromptTemplate
):
    tool_descriptions = "\\n".join(
        f"{i+1}. {tool.description}\\n"
        for i, tool in enumerate(
            tools
        )  # +1 to offset the 0 starting index, we want it count normally from 1.
    )
    planner_prompt = base_prompt.partial(
        replan="",
        num_tools=len(tools)
        + 1,  # Add one because we're adding the join() tool at the end.
        tool_descriptions=tool_descriptions,
    )
    replanner_prompt = base_prompt.partial(
        replan=' - You are given "Previous Plan" which is the plan that the previous agent created along with the execution results '
        "(given as Observation) of each plan and a general thought (given as Thought) about the executed results."
        'You MUST use these information to create the next plan under "Current Plan".\\n'
        ' - When starting the Current Plan, you should start with "Thought" that outlines the strategy for the next plan.\\n'
        " - In the Current Plan, you should NEVER repeat the actions that are already executed in the Previous Plan.\\n"
        " - You must continue the task index from the end of the previous one. Do not repeat task indices.",
        num_tools=len(tools) + 1,
        tool_descriptions=tool_descriptions,
    )

    def should_replan(state: List[BaseMessage]):
        # Context is passed as a system message
        return isinstance(state[-1], SystemMessage)

    def wrap_messages(state: List[BaseMessage]) -> Dict[str, List[BaseMessage]]:
        return {"messages": state}

    def wrap_and_get_last_index(state: List[BaseMessage]) -> Dict[str, List[BaseMessage]]:
        next_task = 0
        for message in state[::-1]:
            if isinstance(message, FunctionMessage) and "idx" in message.additional_kwargs:
                next_task = message.additional_kwargs["idx"] + 1
                break
        # Ensure the last message is a SystemMessage for replan context
        if state and isinstance(state[-1], SystemMessage):
             state[-1].content = state[-1].content + f" - Begin counting at : {next_task}"
        else:
            # If the last message isn't a SystemMessage (e.g., first replan), add one.
            state.append(SystemMessage(content=f"Begin counting at : {next_task}"))

        return {"messages": state}

    return (
        RunnableBranch(
            (should_replan, wrap_and_get_last_index | replanner_prompt),
            wrap_messages | planner_prompt,
        )
        | llm # 'llm' is passed from agent.py, which will be ChatGoogleGenerativeAI
        | LLMCompilerPlanParser(tools=tools)
    )

