import os
import argparse
from langchain_core.messages import HumanMessage
from src.agent import invoke_agent
from src.scheduler import schedule_gmeet
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def main():
    # Configure LangSmith tracing
    os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGCHAIN_TRACING_V2", "false")
    os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY")
    os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT", "LLMCompiler-Project")

    parser = argparse.ArgumentParser(description="LLMCompiler Agent")
    parser.add_argument("--meet_url", type=str, help="The URL of the Google Meet to join.")
    parser.add_argument("--join_time", type=str, help="The time to join the meet in HH:MM format.")
    args = parser.parse_args()

    # Logic for scheduling a meeting with hardcoded cookies
    if args.meet_url and args.join_time:
        schedule_gmeet(meet_url=args.meet_url, join_time=args.join_time)
    else:
        # Fallback to the interactive agent mode
        print("LLMCompiler Agent Ready!")
        print("Type 'exit' to quit.")

        while True:
            user_input = input("You: ")
            if user_input.lower() == 'exit':
                break

            print(f"Agent is thinking about: '{user_input}'...")
            
            response = invoke_agent(user_input)
            print(f"Agent: {response}")

if __name__ == "__main__":
    main()
