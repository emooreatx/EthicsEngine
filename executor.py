# executor.py
import asyncio
from autogen.agents.experimental import ReasoningAgent
from config import llm_config, reason_config_minimal, semaphore, logger
from contextlib import redirect_stdout, redirect_stderr
import io

async def run_executor(agent_name, scenario_name, reasoning_output, simulation_results, timeout_seconds=60):
    key = (agent_name, scenario_name)
    logger.info(f"Starting executor for '{agent_name}' on scenario '{scenario_name}'.")
    async with semaphore:
        # Create an executor agent that uses the reasoning output to simulate a cricket world outcome.
        executor_agent = ReasoningAgent(
            name=f"{agent_name}_executor",
            system_message=(
                f"You are an executor agent. Given the following reasoning:\n\n{reasoning_output}\n\n"
                "Simulate and describe the likely outcome in the cricket world in 2-3 concise sentences."
            ),
            llm_config=llm_config,
            reason_config=reason_config_minimal,
            silent=True
        )
        dummy = io.StringIO()
        try:
            with redirect_stdout(dummy), redirect_stderr(dummy):
                # Directly generate a reply without using a proxy.
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        executor_agent.generate_reply,
                        [{"role": "user", "content": reasoning_output}]
                    ),
                    timeout=timeout_seconds
                )
            simulation_response = result.strip()
            simulation_results[key] = simulation_response
            logger.info(f"Completed executor for '{agent_name}' on scenario '{scenario_name}'.")
        except asyncio.TimeoutError:
            simulation_results[key] = "Timeout"
            logger.warning(f"Executor for '{agent_name}' on scenario '{scenario_name}' timed out.")

if __name__ == "__main__":
    import sys
    import logging
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    logger.setLevel(logging.DEBUG)

    # Testing the executor module with cricket world outcomes
    simulation_results = {}
    # Sample reasoning output from a previous reasoning agent run
    reasoning_output = (
        "The reasoning agent concluded that a utilitarian approach would favor sacrificing a lesser value for the benefit of the many."
    )
    # Run the executor for a test scenario
    asyncio.run(run_executor("Deontological", "trolley_problem", reasoning_output, simulation_results))
    print("\nSimulation Results:", simulation_results)
