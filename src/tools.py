import math
import re
import os
from typing import List, Optional
import numexpr

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool, BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools.tavily_search import TavilySearchResults
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from src.gmeet_tool import gmeet_tool # Import the new gmeet_tool

load_dotenv()

# --- Tavily Search Tool ---
class SearchInput(BaseModel):
    query: str = Field(description="The search query for information on the web.")

search = StructuredTool.from_function(
    func=TavilySearchResults(max_results=2).invoke,
    name="search",
    description="A search engine. Use this to search for information on the web.",
    args_schema=SearchInput,
)

# --- Math Tool ---
_MATH_DESCRIPTION = "A calculator that solves a single mathematical expression. Do not pass in word problems."

_SYSTEM_PROMPT = """Translate a math problem into a expression that can be executed using Python's numexpr library. Use the output of running this code to answer the question.

Question: ${{Question with math problem.}}
```text
${{single line mathematical expression that solves the problem}}
Use code with caution.
Python
...numexpr.evaluate(text)...
Generated output
${{Output of running the code}}
Use code with caution.
Output
Answer: ${{Answer}}
Begin.
Question: What is 37593 * 67?
ExecuteCode({{"code": "37593 * 67"}})
...numexpr.evaluate("37593 * 67")...
Generated output
2518731
Use code with caution.
Output
Answer: 2518731
Question: 37593^(1/5)
ExecuteCode({{"code": "37593**(1/5)"}})
...numexpr.evaluate("37593**(1/5)")...
Generated output
8.222831614237718
Use code with caution.
Output
Answer: 8.222831614237718
"""

_ADDITIONAL_CONTEXT_PROMPT = """The following additional context is provided from other functions.
Use it to substitute into any variables or expressions in the problem.
\n\n{context}\n\nNote that context variables are not defined in code yet.
You must extract the relevant numbers and directly put them in code."""

class ExecuteCode(BaseModel):
    reasoning: str = Field(..., description="The reasoning behind the code expression, including how context is included, if applicable.")
    code: str = Field(..., description="The simple code expression to execute by numexpr.evaluate().")

def _evaluate_expression(expression: str) -> str:
    try:
        local_dict = {"pi": math.pi, "e": math.e}
        output = str(
            numexpr.evaluate(
                expression.strip(),
                global_dict={},
                local_dict=local_dict,
            )
        )
    except Exception as e:
        raise ValueError(f'Failed to evaluate "{expression}". Raised error: {repr(e)}. Please try again with a valid numerical expression.')
    return re.sub(r"^\[|\]$", "", output)

class MathToolArgs(BaseModel):
    problem: str = Field(..., description="The math problem to solve.")
    context: Optional[List[str]] = Field(None, description="Optional a list of strings as context to help solve the problem.")

def get_math_tool(llm: ChatGoogleGenerativeAI) -> StructuredTool:
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", _SYSTEM_PROMPT),
            ("user", "{problem}"),
            MessagesPlaceholder(variable_name="context", optional=True),
        ]
    )
    extractor = prompt | llm.with_structured_output(ExecuteCode)

    def calculate_expression(
        problem: str,
        context: Optional[List[str]] = None,
        config: Optional[RunnableConfig] = None,
    ) -> str:
        chain_input = {"problem": problem}
        if context:
            context_str = "\n".join(context)
            if context_str.strip():
                context_str = _ADDITIONAL_CONTEXT_PROMPT.format(context=context_str.strip())
                chain_input["context"] = [SystemMessage(content=context_str)]
        
        code_model = extractor.invoke(chain_input, config)
        
        try:
            return _evaluate_expression(code_model.code)
        except Exception as e:
            return repr(e)

    return StructuredTool.from_function(
        name="math",
        func=calculate_expression,
        description=_MATH_DESCRIPTION,
        args_schema=MathToolArgs
    )

llm_for_tools = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)
math_tool = get_math_tool(llm_for_tools)
tools: List[BaseTool] = [search, math_tool, gmeet_tool]
