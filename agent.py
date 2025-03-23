# agent.py
import asyncio
import logging
import json
import os
from autogen.agents.experimental import ReasoningAgent
from config import llm_config, reason_config_minimal, semaphore, logger, AGENT_TIMEOUT
from contextlib import redirect_stdout, redirect_stderr
import io

# Verify that required data files exist; if any are missing, raise an error.
required_files = [
    "data/golden_patterns.json",
    "data/species.json",
    "data/scenarios.json"
]
for file_path in required_files:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Required file not found: {file_path}")

# Load reasoning models (golden patterns), species data, and scenarios from JSON files
with open("data/golden_patterns.json", "r") as f:
    golden_patterns = json.load(f)
with open("data/species.json", "r") as f:
    species_data = json.load(f)
with open("data/scenarios.json", "r") as f:
    scenarios_data = json.load(f)

def create_agent(model_name):
    """
    Create a reasoning agent with a given reasoning model.
    """
    if model_name not in golden_patterns:
        raise ValueError(f"Model '{model_name}' not found in golden patterns.")
    return ReasoningAgent(
        name=f"{model_name}_agent",
        system_message=(
            f"You reason strictly according to the {model_name} model: {golden_patterns[model_name]}. "
            "Consider species-specific traits in your analysis."
        ),
        llm_config=llm_config,
        reason_config=reason_config_minimal,
        silent=True
    )

async def run_agent(model_name, species_name, scenario_name, agent_status, agent_results, timeout_seconds=AGENT_TIMEOUT):
    key = (model_name, species_name, scenario_name)
    agent_status[key] = {"status": "Running", "last_message": "Starting..."}
    logger.info(f"Starting agent '{model_name}' on species '{species_name}' for scenario '{scenario_name}'.")

    # Ensure species and scenario exist in the respective data files
    if species_name not in species_data:
        raise ValueError(f"Species '{species_name}' not found in species data.")
    if scenario_name not in scenarios_data:
        raise ValueError(f"Scenario '{scenario_name}' not found in scenarios data.")

    scenario_text = scenarios_data[scenario_name]
    species_traits = species_data[species_name]

    async with semaphore:
        agent = create_agent(model_name)
        dummy = io.StringIO()
        # Build a combined prompt including species traits and scenario details.
        combined_prompt = (
            f"Species: {species_name} - Traits: {species_traits}\n"
            f"Scenario ({scenario_name}): {scenario_text}"
        )
        try:
            with redirect_stdout(dummy), redirect_stderr(dummy):
                chat_result = await asyncio.wait_for(
                    asyncio.to_thread(
                        agent.generate_reply,
                        [{"role": "user", "content": combined_prompt}]
                    ),
                    timeout=timeout_seconds
                )
            final_response = chat_result.strip()
            agent_status[key]["status"] = "✅ Done"
            agent_status[key]["last_message"] = (
                final_response[:120] + ("..." if len(final_response) > 120 else "")
            )
            agent_results[key] = final_response
            logger.info(f"Completed agent '{model_name}' on species '{species_name}' for scenario '{scenario_name}'.")
        except asyncio.TimeoutError:
            agent_status[key]["status"] = "⚠️ Timeout"
            agent_status[key]["last_message"] = "Agent took too long!"
            agent_results[key] = "Timeout"
            logger.warning(f"Agent '{model_name}' on species '{species_name}' for scenario '{scenario_name}' timed out.")

if __name__ == "__main__":
    import sys
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    logger.setLevel(logging.DEBUG)

    agent_status = {}
    agent_results = {}

    # For testing, using sample values that must exist in the data files.
    test_model = "Deontological"
    test_species = "Megacricks"
    test_scenario = "Integrity"                                 # Must exist in scenarios.json

    asyncio.run(run_agent(test_model, test_species, test_scenario, agent_status, agent_results))
    print("\nAgent Results:", agent_results)
