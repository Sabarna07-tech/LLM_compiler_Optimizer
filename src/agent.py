import itertools
from typing import Annotated, List, Dict, Any, TypedDict
from enum import Enum
from langgraph.graph import END, StateGraph, START
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from pydantic import BaseModel, Field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain import hub

from src.tools import tools
from src.planner import create_planner
from src.executor import task_scheduler
from src.joiner import joiner

# --- State Definition ---
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]

# --- Router Logic ---
class Routes(Enum):
    """The possible routes the agent can take."""
    PLANNER = "planner"
    RESPONSE = "response"

class Route(BaseModel):
    """The decision on which route to take."""
    destination: Routes = Field(
        ...,
        description="The destination route for the user's input. Route to 'planner' if tools are needed, otherwise route to 'response'."
    )

# --- LLM and Prompt Instantiation ---
llm_for_router = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)
llm_for_planner = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.2)
llm_for_response = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.7)

planner_prompt = hub.pull("wfh/llm-compiler")
router_prompt_template = (
    "You are an expert at routing a user question to a specialist. "
    "Based on the user's query, you must decide whether to route them to a 'planner' that can use tools to answer complex questions, "
    "or to a 'response' node for simple conversational replies (like greetings or thank-yous).\n"
    "The user's query is: '{query}'"
)

# --- Node Definitions ---
planner = create_planner(llm_for_planner, tools, planner_prompt)

def router_node(state: AgentState) -> Dict[str, str]:
    """Determines the next step based on the user's query."""
    query = state["messages"][-1].content
    prompt = router_prompt_template.format(query=query)
    
    router_runnable = llm_for_router.with_structured_output(Route)
    route_decision = router_runnable.invoke(prompt)
    
    if route_decision.destination == Routes.PLANNER:
        return {"destination": "plan_and_schedule"}
    else:
        return {"destination": "response"}

def response_node(state: AgentState) -> Dict[str, List[BaseMessage]]:
    """Generates a simple conversational response."""
    user_input = state["messages"][-1]
    response = llm_for_response.invoke([user_input])
    return {"messages": [response]}

def plan_and_schedule_node(state: AgentState, config) -> Dict[str, List[BaseMessage]]:
    """Plans and executes tasks."""
    # The planner returns a generator, so we stream it
    tasks_generator = planner.stream(state["messages"])
    # The scheduler invokes the tasks from the generator
    return {"messages": task_scheduler.invoke({"messages": state["messages"], "tasks": tasks_generator}, config)}

# --- Graph Construction ---
graph_builder = StateGraph(AgentState)

# Add all nodes
graph_builder.add_node("router", router_node)
graph_builder.add_node("plan_and_schedule", plan_and_schedule_node)
graph_builder.add_node("join", joiner)
graph_builder.add_node("response", response_node)

# Set the entry point
graph_builder.set_entry_point("router")

# Define conditional edges from the router
graph_builder.add_conditional_edges(
    "router",
    lambda x: x["destination"],
    {
        "plan_and_schedule": "plan_and_schedule",
        "response": "response",
    },
)

# Define edges for the planner route
graph_builder.add_edge("plan_and_schedule", "join")

def should_continue(state: AgentState) -> str:
    """Determines whether to loop or end after the joiner."""
    messages = state["messages"]
    if isinstance(messages[-1], AIMessage):
        return END
    return "plan_and_schedule"

graph_builder.add_conditional_edges(
    "join",
    should_continue,
    {"plan_and_schedule": "plan_and_schedule", END: END}
)

# The response node is always an end state
graph_builder.add_edge("response", END)

# Compile the graph
agent_chain = graph_builder.compile()

# --- Invocation Helper ---
def invoke_agent(question: str, config: Dict[str, Any] = None) -> Any:
    initial_state = {"messages": [HumanMessage(content=question)]}
    full_output = None
    for s in agent_chain.stream(initial_state, config=config):
        full_output = s
    
    # Check the last node that was executed to extract the correct final response
    last_executed_node = list(full_output.keys())[-1]
    
    if last_executed_node == 'join' and full_output['join'] and 'messages' in full_output['join']:
        final_messages = full_output['join']['messages']
        if final_messages and isinstance(final_messages[-1], AIMessage):
            return final_messages[-1].content
    
    elif last_executed_node == 'response' and full_output['response'] and 'messages' in full_output['response']:
        final_messages = full_output['response']['messages']
        if final_messages and isinstance(final_messages[-1], AIMessage):
            return final_messages[-1].content

    return "Could not determine a final answer."