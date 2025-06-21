import itertools
from typing import Annotated, List, Dict, Any, TypedDict
from langgraph.graph import END, StateGraph, START
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain import hub

from src.tools import tools # Our defined tools
from src.planner import create_planner
from src.executor import schedule_tasks
from src.joiner import joiner # Our joiner runnable

# Define the state for our LangGraph agent
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]

# Instantiate the main LLM for the planner
# Use a higher temperature for creativity in planning
llm_for_planner = ChatGoogleGenerativeAI(
    model="gemini-pro", 
    temperature=0.2,
    client_options={"api_version": "v1"} # Explicitly setting API version to v1
) 
planner_prompt = hub.pull("wfh/llm-compiler") # The prompt for the planner

# Create the planner runnable
planner = create_planner(llm_for_planner, tools, planner_prompt)

# --- Define the LangGraph workflow ---
graph_builder = StateGraph(AgentState)

# 1. Add nodes (vertices) to the graph
# The 'plan_and_schedule' node combines planning and concurrent task execution
# The 'join' node decides whether to provide a final response or replan
graph_builder.add_node("plan_and_schedule", lambda state, config: 
                       {"messages": schedule_tasks.invoke(
                           {"messages": state["messages"], "tasks": planner.stream(state["messages"])}, 
                           config)})
graph_builder.add_node("join", joiner)

# 2. Define edges (transitions) between nodes

# After planning and scheduling, transition to the joiner to decide next steps
graph_builder.add_edge("plan_and_schedule", "join")

# This condition determines looping logic from the 'join' node
def should_continue(state: AgentState) -> str:
    messages = state["messages"]
    # If the last message is an AIMessage, it means the joiner returned a FinalResponse.
    # Otherwise, it returned a SystemMessage with feedback for replanning.
    if isinstance(messages[-1], AIMessage):
        return END # End the graph execution
    return "plan_and_schedule" # Loop back to plan and schedule

# Add conditional edges from the 'join' node
# The `should_continue` function determines the next node based on the state
graph_builder.add_conditional_edges(
    "join",
    should_continue,
    {"plan_and_schedule": "plan_and_schedule", END: END} # Map outcomes to nodes/END
)

# Set the starting point of the graph
graph_builder.set_entry_point("plan_and_schedule")

# Compile the graph
agent_chain = graph_builder.compile()

# You can add a helper function to invoke the agent
def invoke_agent(question: str, config: Dict[str, Any] = None) -> Any:
    # LangGraph expects the initial state to be a dictionary matching the AgentState
    initial_state = {"messages": [HumanMessage(content=question)]}
    
    # Use stream() for potentially long-running multi-step agents
    # This allows you to see intermediate steps if desired
    # The final result is usually in the last step's 'join' output
    
    full_output = None
    for s in agent_chain.stream(initial_state, config=config):
        full_output = s # Keep track of the last state
        # print(s) # Uncomment to see all intermediate steps
        # print("---")
    
    # Extract the final answer from the last 'join' step
    if full_output and 'join' in full_output and full_output['join'] and 'messages' in full_output['join']:
        # The joiner's output is parsed into a list of messages.
        # The actual final response is the content of the last AIMessage.
        final_messages = full_output['join']['messages']
        if final_messages and isinstance(final_messages[-1], AIMessage):
            return final_messages[-1].content
    return "Could not determine a final answer."

