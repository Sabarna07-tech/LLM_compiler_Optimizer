import os
from langchain_core.messages import HumanMessage
from src.agent import invoke_agent # Our agent chain wrapper
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def main():
    # Configure LangSmith tracing
    os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGCHAIN_TRACING_V2", "false")
    os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY")
    os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT", "LLMCompiler-Project")

    print("LLMCompiler Agent Ready!")
    print("Type 'exit' to quit.")

    while True:
        user_input = input("You: ")
        if user_input.lower() == 'exit':
            break

        print(f"Agent is thinking about: '{user_input}'...")
        
        # Invoke the agent
        response = invoke_agent(user_input)
        print(f"Agent: {response}")

if __name__ == "__main__":
    main()
