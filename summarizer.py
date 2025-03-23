# summarizer.py
import asyncio
import logging
import io
from autogen.agents.experimental import ReasoningAgent
from config import llm_config, reason_config_minimal, semaphore, logger, AGENT_TIMEOUT
from contextlib import redirect_stdout, redirect_stderr

async def run_summarizer(prompt, summarizer_results, timeout_seconds=AGENT_TIMEOUT):
    key = "summarizer"
    logger.info("Starting summarizer.")
    
    async with semaphore:
        summarizer_agent = ReasoningAgent(
            name="summarizer_agent",
            system_message=(
                "You are a summarizer agent. Your task is to generate a detailed and descriptive summary "
                "of the following prompt. Highlight the key differences in outcomes and ethical reasoning in the species world. "
                "Please ensure your response is detailed and avoids generic termination outputs such as 'TERMINATE'."
            ),
            llm_config=llm_config,
            reason_config=reason_config_minimal,
            silent=True
        )
        dummy = io.StringIO()
        try:
            with redirect_stdout(dummy), redirect_stderr(dummy):
                summary_result = await asyncio.wait_for(
                    asyncio.to_thread(
                        summarizer_agent.generate_reply,
                        [{
                            "role": "user",
                            "content": (
                                prompt + "\n\n"
                                "Based on the prompt above, generate a detailed summary in 2-3 sentences. "
                                "Do not include any generic termination outputs such as 'TERMINATE'."
                            )
                        }]
                    ),
                    timeout=timeout_seconds
                )
            final_summary = summary_result.strip()
            summarizer_results[key] = final_summary
            logger.info("Completed summarizer.")
        except asyncio.TimeoutError:
            summarizer_results[key] = "Timeout"
            logger.warning("Summarizer timed out.")

if __name__ == "__main__":
    import sys
    import logging
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    logger.setLevel(logging.DEBUG)

    # End-to-End Test Block: Use actual agent.py and executor.py functions for two species.
    from agent import run_agent
    from executor import run_executor

    async def end_to_end_test():
        agent_status = {}
        agent_results = {}
        simulation_results = {}

        # Define test parameters.
        test_model = "Deontological"       # Must exist in data/golden_patterns.json.
        test_scenario = "Integrity"          # Must exist in data/scenarios.json.
        species_list = ["Megacricks", "Jiminies"]  # Both must exist in data/species.json.

        # Run the reasoning stage for each species.
        for species in species_list:
            await run_agent(test_model, species, test_scenario, agent_status, agent_results)

        # Run the simulation stage for each species.
        for species in species_list:
            reasoning_output = agent_results.get((test_model, species, test_scenario), "No reasoning output")
            await run_executor(test_model, species, test_scenario, reasoning_output, simulation_results)

        # Build a summarizer prompt using the outputs from both species.
        summary_prompt = (
            "Compare the outcomes for the reasoning model '{}' on the scenario '{}' across two species. "
            "Provide specific examples from the following outputs:\n\n".format(test_model, test_scenario)
        )
        for species in species_list:
            reasoning_text = agent_results.get((test_model, species, test_scenario), "No reasoning output")
            simulation_text = simulation_results.get((test_model, species, test_scenario), "No simulation output")
            summary_prompt += (
                f"Species: {species}\n"
                f"Reasoning Output: {reasoning_text}\n"
                f"Simulation Output: {simulation_text}\n\n"
            )

        # Call the summarizer.
        summarizer_results = {}
        await run_summarizer(summary_prompt, summarizer_results)
        print("\nSummarizer Results:", summarizer_results)

    asyncio.run(end_to_end_test())
