import schedule
import time
import threading
from src.gmeet_tool import join_gmeet

def run_threaded(func_to_run, **kwargs):
    """
    Helper function to run a job in a new thread.
    """
    job_thread = threading.Thread(target=func_to_run, kwargs=kwargs)
    job_thread.start()

def schedule_gmeet(meet_url: str, join_time: str):
    """
    Schedules a Google Meet to be joined at a specific time.

    Args:
        meet_url (str): The URL of the Google Meet.
        join_time (str): The time to join the meet in HH:MM format.
    """
    print(f"Scheduling to join {meet_url} at {join_time} using hardcoded cookies.")
    
    # Schedule the threaded job runner
    schedule.every().day.at(join_time).do(
        run_threaded, 
        func_to_run=join_gmeet, 
        meet_url=meet_url
    )

    print("Scheduler is running. Waiting for the scheduled time...")

    while True:
        schedule.run_pending()
        time.sleep(1)
