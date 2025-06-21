from typing import List, Union, Dict, Any
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
from langchain_core.runnables import chain as as_runnable
from langchain_openai import ChatOpenAI
from langchain import hub
from pydantic import BaseModel, Field

# --- Joiner Output Models ---
class FinalResponse(BaseModel):
    """The final response/answer."""
    response: str

class Replan(BaseModel):
    feedback: str = Field(
        description="Analysis of the previous attempts and recommendations on what needs to be fixed."
    )

class JoinOutputs(BaseModel):
    """Decide whether to replan or whether you can return the final response."""
    thought: str = Field(
        description="The chain of thought reasoning for the selected action"
    )
    action: Union[FinalResponse, Replan]

# --- Joiner Logic ---
# You can optionally add examples to the joiner prompt
joiner_prompt = hub.pull("wfh/llm-compiler-joiner").partial(examples="") 
llm_for_joiner = ChatOpenAI(model="gpt-4o", temperature=0) # Use a more deterministic LLM for joiner

runnable_joiner_decision = joiner_prompt | llm_for_joiner.with_structured_output(
    JoinOutputs, method="function_calling"
)

def _parse_joiner_output(decision: JoinOutputs) -> Dict[str, List[BaseMessage]]:
    """Parse the Joiner's decision into LangGraph messages."""
    response_messages = [AIMessage(content=f"Thought: {decision.thought}")]
    
    if isinstance(decision.action, Replan):
        # If replanning, add a SystemMessage to carry feedback for the next planning phase
        response_messages.append(
            SystemMessage(
                content=f"Context from last attempt: {decision.action.feedback}"
            )
        )
    else: # FinalResponse
        response_messages.append(AIMessage(content=decision.action.response))
        
    return {"messages": response_messages}


def select_recent_messages(state: Dict[str, List[BaseMessage]]) -> Dict[str, List[BaseMessage]]:
    """Select only the most recent messages relevant for the joiner's decision."""
    messages = state["messages"]
    selected = []
    # Iterate backwards to find the last HumanMessage and all subsequent FunctionMessages/AIMessages
    for msg in messages[::-1]:
        selected.append(msg)
        if isinstance(msg, HumanMessage):
            break
    return {"messages": selected[::-1]} # Reverse to get chronological order


# Composed Joiner Runnable
joiner = select_recent_messages | runnable_joiner_decision | _parse_joiner_output

