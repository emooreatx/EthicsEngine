# main.py
import asyncio
import warnings
import json
import os
import sys
import logging
from agent import run_agent
from executor import run_executor
from config import user_proxy, llm_config, reason_config_minimal, logger
from summarizer import run_summarizer

warnings.filterwarnings("ignore", category=UserWarning)

# Load required data from the data folder
with open("data/golden_patterns.json", "r") as f:
    reasoning_models = json.load(f)
with open("data/species.json", "r") as f:
    species_data = json.load(f)
with open("data/scenarios.json", "r") as f:
    scenarios = json.load(f)

# Global dictionaries for storing outputs.
agent_status = {}      # Keys: (model, species, scenario)
agent_results = {}     # Keys: (model, species, scenario)
simulation_results = {}  # Keys: (model, species, scenario)

async def main():
    # Reset global state to avoid duplicates on re-run.
    global agent_status, agent_results, simulation_results
    agent_status = {}
    agent_results = {}
    simulation_results = {}

    # Phase 1: Reasoning Stage (for every triple)
    reasoning_tasks = []
    for model in reasoning_models:
        for species in species_data:
            for scenario in scenarios:
                key = (model, species, scenario)
                agent_status[key] = {"status": "Queued", "last_message": "Waiting..."}
                # Here, we pass the species so that the agent can factor it into the reasoning.
                reasoning_tasks.append(
                    run_agent(model, species, scenario, agent_status, agent_results)
                )
    logger.debug(f"Created {len(reasoning_tasks)} reasoning tasks.")
    try:
        await asyncio.gather(*reasoning_tasks, return_exceptions=True)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.debug("Execution halted by user during reasoning phase.")

    # Phase 2: Simulation Stage (for every triple)
    executor_tasks = []
    for model in reasoning_models:
        for species in species_data:
            for scenario in scenarios:
                key = (model, species, scenario)
                reasoning_output = agent_results.get(key, "No output")
                executor_tasks.append(
                    run_executor(model, species, scenario, reasoning_output, simulation_results)
                )
    logger.debug(f"Created {len(executor_tasks)} executor tasks.")
    try:
        await asyncio.gather(*executor_tasks)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.debug("Execution halted by user during simulation phase.")

    # Phase 3: Summarization Stage (combine results for all triples)
    summary_prompt = (
        "Compare and contrast the outcomes across the following reasoning models, species, and scenarios, "
        "focusing on how differences in reasoning lead to different outcomes in the species world.\n\n"
    )
    for model in reasoning_models:
        for species in species_data:
            for scenario in scenarios:
                key = (model, species, scenario)
                reasoning_text = agent_results.get(key, "No reasoning output")
                simulation_text = simulation_results.get(key, "No simulation result")
                short_reasoning = (
                    reasoning_text if len(reasoning_text) < 300 else reasoning_text[:300] + "..."
                )
                short_simulation = (
                    simulation_text if len(simulation_text) < 300 else simulation_text[:300] + "..."
                )
                summary_prompt += (
                    f"{model} ({species}, {scenario}):\n"
                    f"- Reasoning: {short_reasoning}\n"
                    f"- Outcome: {short_simulation}\n\n"
                )
    
    summarizer_results = {}
    await run_summarizer(summary_prompt, summarizer_results)
    
    print("\n🚀 Ethical Approaches & Outcomes Summary:\n", flush=True)
    summary = summarizer_results.get("summarizer", "No summary produced.")
    print(summary, flush=True)
    
    # Prepare detailed run data.
    runs_data = []
    for model in reasoning_models:
        for species in species_data:
            for scenario in scenarios:
                runs_data.append({
                    "model": model,
                    "species": species,
                    "scenario": scenario,
                    "reasoning": agent_results.get((model, species, scenario), ""),
                    "simulation": simulation_results.get((model, species, scenario), "")
                })

    final_results = {
        "runs": runs_data,
        "summary": summary
    }

    # Save the detailed results to a JSON file in the results/ directory.
    results_dir = "results"
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
    results_path = os.path.join(results_dir, "results.json")
    with open(results_path, "w") as f:
        json.dump(final_results, f, indent=4)

    # Shutdown the default executor to allow the program to exit.
    await asyncio.get_running_loop().shutdown_default_executor()

def run_analysis_for_dashboard(scenarios, reasoning_models, summarizer_prompts):
    """Run analysis with data from the dashboard and return results as text."""
    import io
    from contextlib import redirect_stdout

    # Update the data files.
    with open("data/scenarios.json", "w") as f:
         json.dump(scenarios, f, indent=4)
    with open("data/golden_patterns.json", "w") as f:
         json.dump(reasoning_models, f, indent=4)
    
    f = io.StringIO()
    with redirect_stdout(f):
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            return "Analysis interrupted by user"
    return f.getvalue()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExecution halted by user. Exiting gracefully...\n")
