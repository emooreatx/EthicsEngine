import asyncio
from config.config import semaphore, logger
from reasoning_agent import create_agent

async def main():
    # Create an EthicsAgent with species "Jiminies", model "Deontological", and low reasoning level.
    agent = create_agent("Jiminies", "Deontological", reasoning_level="low")

    # Define the prompt (identical for all occurrences)
    prompt = "What is the capital of France?"

    # Function to run the agent asynchronously with a given ID.
    async def run_with_id(task_id, prompt):
        async with semaphore:
            # Correctly pass both the prompt payload and the task ID to run_async.
            response = await agent.run_async({"prompt": prompt}, task_id)
            return task_id, response

    # Create tasks for three occurrences with task IDs 1, 2, and 3.
    tasks = [run_with_id(i, prompt) for i in [1, 2, 3]]
    
    # Await all tasks concurrently.
    responses = await asyncio.gather(*tasks)
    
    # Build a dictionary with task IDs as keys and responses as values.
    result_dict = {task_id: resp for task_id, resp in responses}
    
    print("Combined responses:")
    print(result_dict)

if __name__ == "__main__":
    asyncio.run(main())