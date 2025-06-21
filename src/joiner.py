from typing import List, Union, Dict, Any
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage, ToolMessage, ToolCall
from langchain_core.runnables import chain as as_runnable
from langchain_google_genai import ChatGoogleGenerativeAI
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
llm_for_joiner = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0) # Use a more deterministic LLM for joiner

# The 'method' argument is not supported by the Gemini implementation and has been removed.
runnable_joiner_decision = joiner_prompt | llm_for_joiner.with_structured_output(
    JoinOutputs
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
    """
    Selects the most recent messages for the joiner's decision.
    It also synthesizes an AIMessage with tool_calls if the history
    contains ToolMessages without a preceding AIMessage with tool_calls.
    This is to ensure compatibility with models like Gemini that require
    a strict function-call/function-response sequence.
    """
    messages = state["messages"]

    # Find the index of the last HumanMessage
    last_human_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            last_human_idx = i
            break
    
    # If no HumanMessage is found, pass through
    if last_human_idx == -1:
        return {"messages": messages}

    # Slice the messages from the last human message to the end
    relevant_messages = messages[last_human_idx:]

    # Check for ToolMessages and an AIMessage with tool_calls in this slice
    has_tool_messages = any(isinstance(m, ToolMessage) for m in relevant_messages)
    has_ai_with_tool_calls = any(isinstance(m, AIMessage) and getattr(m, 'tool_calls', []) for m in relevant_messages)

    # If we have tool messages but no corresponding AIMessage with tool calls, we need to fix it
    if has_tool_messages and not has_ai_with_tool_calls:
        reconstructed_messages = []
        human_message = relevant_messages[0]
        reconstructed_messages.append(human_message)
        
        tool_messages = [m for m in relevant_messages if isinstance(m, ToolMessage)]
        
        # Create a synthetic AIMessage with tool_calls using the tool name from the ToolMessage
        synthetic_tool_calls = [
            ToolCall(
                name=tm.name, 
                # MODIFICATION: Use the embedded args, default to {} if not found
                args=tm.additional_kwargs.get("args", {}), 
                id=tm.tool_call_id
            )
            for tm in tool_messages
            if tm.name and tm.tool_call_id
        ]
        
        # Only add the synthetic message if we successfully created tool calls
        if synthetic_tool_calls:
            synthetic_ai_message = AIMessage(content="", tool_calls=synthetic_tool_calls)
            reconstructed_messages.append(synthetic_ai_message)
        
        # Add the original tool messages after the synthetic AIMessage
        reconstructed_messages.extend(tool_messages)
        
        return {"messages": reconstructed_messages}

    # Otherwise, the structure is fine, just return the relevant slice
    return {"messages": relevant_messages}


# Composed Joiner Runnable
joiner = select_recent_messages | runnable_joiner_decision | _parse_joiner_output