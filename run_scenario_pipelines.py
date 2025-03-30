# EthicsEngine/run_scenario_pipelines.py
#!/usr/bin/env python3
import argparse
import json
import asyncio
import os
import sys # Import sys for stdout flushing
import time # Import time for timestamps
from datetime import datetime
from pathlib import Path
from typing import Any # Added for type hinting

# --- Updated Imports ---
# Import EthicsAgent from reasoning_agent
from reasoning_agent import EthicsAgent
# Import configs, logger, semaphore (now TrackedSemaphore), and AG2_REASONING_SPECS from config
from config.config import logger, semaphore, llm_config, AG2_REASONING_SPECS, SEMAPHORE_CAPACITY
# --- End Updated Imports ---

# Assuming dashboard_utils is available for metadata loading
try:
    from dashboard.dashboard_utils import load_json as load_json_util
except ImportError:
    logger.warning("Could not import dashboard_utils. Using basic json loader.")
    def load_json_util(path, default=None):
        # Fallback loader...
        if default is None: default = {}
        try:
            with open(path, 'r') as f: return json.load(f)
        except FileNotFoundError: logger.error(f"File not found: {path}"); return {"Error": f"File not found: {path}"}
        except json.JSONDecodeError: logger.error(f"JSON decode error: {path}"); return {"Error": f"JSON decode error: {path}"}
        except Exception as e: logger.error(f"Error loading file {path}: {e}"); return {"Error": f"Error loading file {path}: {e}"}

# --- REMOVED Semaphore Monitoring Task ---
# The monitor_semaphore async function has been removed.
# Status will be monitored by the UI instead.
# --- End REMOVED Section ---


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run a pipeline (planner -> executor) for each scenario, including reasoning tree."
    )
    parser.add_argument("--data-dir", default="data", help="Path to the data directory")
    parser.add_argument("--scenarios-file", default=os.path.join("data","scenarios.json"), help="Path to scenarios file (expects list format)")
    parser.add_argument("--results-dir", default="results", help="Directory to save the results")
    parser.add_argument("--species", default="Jiminies", help="Species name (for planner & executor)")
    parser.add_argument("--model", default="Deontological", help="Reasoning model (for planner & executor)")
    parser.add_argument("--reasoning-level", default="low", choices=["low", "medium", "high"], help="Reasoning level (low, medium, high)")
    return parser.parse_args()

def load_scenarios(path):
    """Loads scenarios from a JSON file, expecting a list of scenario objects."""
    try:
        file_path_obj = Path(path)
        if not file_path_obj.is_file():
             logger.error(f"Scenarios file path is not a file or does not exist: {file_path_obj}")
             return []
        with open(file_path_obj) as f: data = json.load(f)
        if isinstance(data, list):
            logger.info(f"Loading scenarios from list format in {file_path_obj}")
            valid_scenarios = []
            for index, item in enumerate(data):
                if isinstance(item, dict) and "id" in item and "prompt" in item: valid_scenarios.append(item)
                else: logger.warning(f"Skipping invalid scenario format at index {index} in {file_path_obj}: {item}")
            return valid_scenarios
        else:
            logger.error(f"Unexpected format in scenarios file: {file_path_obj}. Expected a JSON list.")
            return []
    except json.JSONDecodeError: logger.error(f"Error decoding JSON from scenarios file: {path}"); return []
    except Exception as e: logger.error(f"Error loading scenarios from {path}: {e}"); return []


async def run_pipeline_for_scenario(scenario, args):
    """Runs the planner and executor agents for a single scenario."""
    pipeline_start_time = time.monotonic()
    scenario_id = scenario.get("id", "unknown_id")
    scenario_text = scenario.get("prompt", "")
    logger.info(f"Pipeline {scenario_id}: Started.")
    scenario_tags = scenario.get("tags", [])
    scenario_eval_criteria = scenario.get("evaluation_criteria", {})

    # Planner stage
    planner_role = "Create an executable, concise, 3 step plan for this situation:"
    planner_prompt = f"{planner_role} {scenario_text}"
    logger.info(f"Pipeline {scenario_id}: Running planner")
    planner_output = ""
    planner_tree = None
    planner_start_time = time.monotonic()
    try:
        # Create agent instance inside the async function if needed, or pass if shared
        planner_agent = EthicsAgent(args.species, args.model, reasoning_level=args.reasoning_level, data_dir=args.data_dir)
        logger.debug(f"Pipeline {scenario_id}: Awaiting planner run_async (T={time.monotonic() - pipeline_start_time:.2f}s)")
        # run_async uses the global semaphore internally
        planner_response_dict = await planner_agent.run_async({"prompt": planner_prompt}, f"{scenario_id}_planner")
        planner_end_time = time.monotonic()
        logger.info(f"Pipeline {scenario_id}: Planner run_async finished (duration={planner_end_time - planner_start_time:.2f}s, T={planner_end_time - pipeline_start_time:.2f}s)")
        planner_output = planner_response_dict.get("result", "Error: No result")
        planner_tree = planner_response_dict.get("reasoning_tree") # Get the tree
    except Exception as e:
        logger.error(f"Pipeline {scenario_id}: Planner Error - {e}", exc_info=True)
        planner_output = f"Error: Planner failed - {e}"

    # Executor stage
    executor_role = "Execute the following plan rapidly and effectively:"
    executor_output = "" # Initialize executor output
    executor_start_time = time.monotonic()
    if "Error:" in planner_output:
         executor_prompt = f"{executor_role} Planner failed, cannot execute."
         logger.warning(f"Pipeline {scenario_id}: Skipping executor due to planner error.")
         executor_output = "Error: Skipped due to planner failure."
    else:
         executor_prompt = f"{executor_role} {planner_output}"
         logger.info(f"Pipeline {scenario_id}: Running executor")
         try:
             executor_agent = EthicsAgent(args.species, args.model, reasoning_level=args.reasoning_level, data_dir=args.data_dir)
             logger.debug(f"Pipeline {scenario_id}: Awaiting executor run_async (T={time.monotonic() - pipeline_start_time:.2f}s)")
             executor_response_dict = await executor_agent.run_async({"prompt": executor_prompt}, f"{scenario_id}_executor")
             executor_end_time = time.monotonic()
             logger.info(f"Pipeline {scenario_id}: Executor run_async finished (duration={executor_end_time - executor_start_time:.2f}s, T={executor_end_time - pipeline_start_time:.2f}s)")
             executor_output = executor_response_dict.get("result", "Error: No result")
             # Note: Executor's reasoning tree is currently not captured/saved.
         except Exception as e:
             logger.error(f"Pipeline {scenario_id}: Executor Error - {e}", exc_info=True)
             executor_output = f"Error: Executor failed - {e}"

    pipeline_end_time = time.monotonic()
    logger.info(f"Pipeline {scenario_id}: Finished (Total time={pipeline_end_time - pipeline_start_time:.2f}s)")
    # Combine results including the planner's decision tree
    return {
        "scenario_id": scenario_id,
        "scenario_text": scenario_text,
        "tags": scenario_tags,
        "evaluation_criteria": scenario_eval_criteria,
        "planner_output": planner_output,
        "executor_output": executor_output,
        "decision_tree": planner_tree # Include the planner's tree
    }

async def main():
    args = parse_args()
    logger.info(f"Running scenario pipelines: {args.species} - {args.model} - {args.reasoning_level}")

    # --- REMOVED Monitor Task Start ---
    # The monitor task is no longer started here.
    # --- End REMOVED Section ---

    # Load Metadata Dependencies
    data_dir_path = Path(args.data_dir); species_file_path = data_dir_path / "species.json"; models_file_path = data_dir_path / "golden_patterns.json"
    species_full_data = load_json_util(species_file_path, {}); models_full_data = load_json_util(models_file_path, {})

    # Check species_full_data format
    if not isinstance(species_full_data, dict):
        logger.error(f"Invalid format for {species_file_path}. Expected dict."); species_traits = ["Error: Invalid species.json format"]; species_full_data = {}
    else:
        species_traits_raw = species_full_data.get(args.species, f"Unknown species '{args.species}'");
        if "Error" in species_full_data: species_traits = [f"Error loading species data: {species_full_data['Error']}"]
        # Ensure species_traits is always a list
        species_traits = species_traits_raw.split(', ') if isinstance(species_traits_raw, str) else species_traits_raw
        if not isinstance(species_traits, list): species_traits = [str(species_traits)] # Force to list if not already

    model_description = models_full_data.get(args.model, f"Unknown model '{args.model}'")
    if isinstance(models_full_data, dict) and "Error" in models_full_data: model_description = f"Error loading model data: {models_full_data['Error']}"

    # Load Scenarios
    scenario_file_path_obj = Path(args.scenarios_file)
    scenarios = load_scenarios(scenario_file_path_obj)
    if not scenarios:
        logger.error(f"No valid scenarios loaded from {scenario_file_path_obj}.")
        print(f"Error: No valid scenarios loaded from {scenario_file_path_obj}.")
        # --- REMOVED Monitor Task Cancel on Error ---
        # monitor_task.cancel(); await asyncio.sleep(0); # Allow cancellation
        # --- End REMOVED Section ---
        return

    # Run Pipelines Concurrently
    main_gather_start_time = time.monotonic()
    logger.info(f"Starting asyncio.gather for {len(scenarios)} pipeline tasks...")
    pipeline_tasks = [run_pipeline_for_scenario(scenario, args) for scenario in scenarios]
    results_list = await asyncio.gather(*pipeline_tasks)
    main_gather_end_time = time.monotonic()
    logger.info(f"Finished asyncio.gather (Total duration={main_gather_end_time - main_gather_start_time:.2f}s)")

    # --- REMOVED Monitor Task Stop ---
    # logger.info("Main tasks completed. Stopping semaphore monitor...")
    # monitor_task.cancel()
    # try: await monitor_task # Allow cancellation to process gracefully
    # except asyncio.CancelledError: logger.info("Semaphore monitor task successfully cancelled.")
    # --- End REMOVED Section ---

    # Prepare Metadata
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # AG2_REASONING_SPECS is now imported from config
    reason_config_spec = AG2_REASONING_SPECS.get(args.reasoning_level, {})
    # Reconstruct agent config used (consistent with agent init)
    agent_reason_config = { "method": "beam_search", "max_depth": reason_config_spec.get("max_depth", 2), "beam_size": 3, "answer_approach": "pool" }
    logger.debug(f"Reconstructed agent_reason_config for metadata: {agent_reason_config}")

    # Debug LLM Config object before processing
    logger.debug(f"Preparing metadata: Type of llm_config = {type(llm_config)}")
    try: cfg_list_content = getattr(llm_config, 'config_list', 'ATTRIBUTE_NOT_FOUND'); logger.debug(f"Preparing metadata: Content of llm_config.config_list = {repr(cfg_list_content)}")
    except Exception as e_dbg: logger.debug(f"Preparing metadata: Error accessing llm_config.config_list for debug: {e_dbg}")

    # Process LLM Config for Metadata (Safer handling)
    safe_llm_config = []
    try:
        config_list = getattr(llm_config, 'config_list', [])
        if config_list:
            for config_item in config_list:
                 try:
                     # Handle both dict and potential objects in config_list
                     model_name = config_item.get('model') if isinstance(config_item, dict) else getattr(config_item, 'model', None)
                     if model_name:
                         # Add temperature from the spec used for this run
                         temp = reason_config_spec.get("temperature", "N/A")
                         safe_llm_config.append({"model": model_name, "temperature": temp})
                     else: logger.warning(f"Item lacks 'model' attribute/key: {config_item}")
                 except AttributeError: logger.warning(f"Cannot access attributes/keys on item. Type: {type(config_item)}")
                 except Exception as item_e: logger.warning(f"Error processing config item: {item_e}. Item: {config_item}")
        else: logger.warning("llm_config.config_list empty/not found during metadata prep.")
    except AttributeError: logger.warning("Could not access llm_config.config_list attribute during metadata prep.")
    except Exception as e: logger.error(f"Error processing llm_config for metadata: {e}")

    # Final Metadata Dictionary
    metadata = {
        "run_timestamp": run_timestamp,
        "run_type": "scenario_pipeline",
        "species_name": args.species,
        "species_traits": species_traits, # Already ensured it's a list
        "reasoning_model": args.model,
        "model_description": model_description,
        "reasoning_level": args.reasoning_level,
        "agent_reasoning_config": agent_reason_config,
        "llm_config": safe_llm_config,
        "tags": [], # Placeholder for potential future top-level tags
        "evaluation_criteria": {} # Top-level criteria not used for scenarios run
    }

    # Combine Metadata and Results
    output_data = {"metadata": metadata, "results": results_list}

    # Save Results
    results_dir_path = Path(args.results_dir); results_dir_path.mkdir(parents=True, exist_ok=True)
    output_filename = results_dir_path / f"scenarios_pipeline_{args.species.lower()}_{args.model.lower()}_{args.reasoning_level.lower()}_{run_timestamp}.json"
    try:
        with open(output_filename, "w") as f: json.dump(output_data, f, indent=2)
        logger.info(f"Scenario pipeline results saved to {output_filename}")
        print(f"Scenario pipeline results saved to {output_filename}") # Keep print for final user feedback
    except Exception as e:
        logger.error(f"Failed to save scenario pipeline results: {e}")
        print(f"Error: Failed to save scenario pipeline results: {e}") # Keep print for final user feedback

if __name__ == "__main__":
    # Ensure the event loop policy is compatible if needed (e.g., on Windows)
    # if sys.platform == "win32":
    #     asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
