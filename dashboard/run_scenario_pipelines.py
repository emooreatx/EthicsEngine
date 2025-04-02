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
# Import logger and semaphore (which is TrackedSemaphore) from config
from config.config import logger, semaphore, TrackedSemaphore # Import TrackedSemaphore for type hint
# Import new utility functions from dashboard_utils
from dashboard.dashboard_utils import (
    load_json, # Use the enhanced load_json
    save_json,
    load_metadata_dependencies,
    generate_run_metadata,
    save_results_with_standard_name # Import the new helper
)
# --- End Updated Imports ---

# --- CLI Semaphore Monitoring Task ---
async def monitor_semaphore_cli(semaphore_instance: TrackedSemaphore, interval: float = 2.0): # Type hint TrackedSemaphore
    """Periodically logs the TrackedSemaphore status."""
    # Check if it has the expected properties instead of isinstance
    if not hasattr(semaphore_instance, 'capacity') or not hasattr(semaphore_instance, 'active_count'):
        logger.error("Monitor: Invalid TrackedSemaphore instance provided (missing properties).")
        return

    # Use the public properties of TrackedSemaphore
    capacity = semaphore_instance.capacity

    logger.info(f"Starting CLI semaphore monitor (Capacity: {capacity}, Interval: {interval}s)")
    try:
        while True:
            # Use the public property of TrackedSemaphore
            active_count = semaphore_instance.active_count
            # Log the status using public properties
            logger.info(f"Semaphore Status: Active Tasks = {active_count}/{capacity}")
            # No flush needed for logger
            await asyncio.sleep(interval) # Use the interval parameter
    except asyncio.CancelledError:
        # Log cancellation
        logger.info("CLI semaphore monitor cancelled.")
    except Exception as e:
        # Log error
        logger.error(f"CLI semaphore monitor error: {e}", exc_info=True)
# --- End CLI Semaphore Monitoring Task ---


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
        # Use the utility load_json here
        # Corrected keyword argument from 'default' to 'default_data'
        data = load_json(file_path_obj, default_data=[]) # Default to empty list
        # Note: The original "Error" check might not be effective if load_json returns default on error.
        # Keeping it for now in case load_json is modified later.
        if isinstance(data, dict) and "Error" in data: # Check if load_json returned an error indicator (safer check)
             logger.error(f"Failed to load scenarios JSON from {file_path_obj}: {data['Error']}")
             return []

        if isinstance(data, list):
            logger.info(f"Loading scenarios from list format in {file_path_obj}")
            valid_scenarios = []
            for index, item in enumerate(data):
                if isinstance(item, dict) and "id" in item and "prompt" in item:
                    valid_scenarios.append(item)
                else:
                    logger.warning(f"Skipping invalid scenario format at index {index} in {file_path_obj}: {item}")
            # Return the populated list if the format was correct (list of dicts)
            return valid_scenarios
        else:
            # This case handles if the top-level JSON structure wasn't a list
            logger.error(f"Unexpected format in scenarios file: {file_path_obj}. Expected a JSON list.")
            return []
    except Exception as e:
        # Catch any unexpected errors during processing
        logger.error(f"Unexpected error loading scenarios from {path}: {e}", exc_info=True)
        return []


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

async def main(effective_args): # Expect effective args already resolved
    # Use the effective arguments passed in
    args = effective_args
    # Log only once after determining args
    logger.info(f"Running scenario pipelines: {args.species} - {args.model} - {args.reasoning_level}")
    data_dir_path = Path(args.data_dir)
    results_dir_path = Path(args.results_dir)

    # --- Use Utility Function to Load Metadata Dependencies ---
    metadata_deps = load_metadata_dependencies(data_dir_path)
    species_full_data = metadata_deps["species"]
    models_full_data = metadata_deps["models"]
    if "Error" in species_full_data or "Error" in models_full_data:
        logger.error("Failed to load essential metadata (species/models). Exiting.")
        print("Error: Failed to load species.json or golden_patterns.json. Check logs.")
        return
    # --- End Metadata Loading ---

    # Load Scenarios
    scenario_file_path_obj = Path(args.scenarios_file)
    scenarios = load_scenarios(scenario_file_path_obj) # load_scenarios now uses utility load_json
    if not scenarios:
        # Removed duplicated error logging/printing
        logger.error(f"No valid scenarios loaded from {scenario_file_path_obj}.")
        print(f"Error: No valid scenarios loaded from {scenario_file_path_obj}.")
        return

    # Run Pipelines Concurrently with CLI Monitoring
    main_gather_start_time = time.monotonic()
    logger.info(f"Starting asyncio.gather for {len(scenarios)} pipeline tasks...")

    # Start CLI semaphore monitor task
    monitor_task = asyncio.create_task(monitor_semaphore_cli(semaphore)) # Use imported semaphore

    results_list = []
    try:
        # Note: run_pipeline_for_scenario creates its own agent instances currently.
        # This could be optimized later if agent creation is expensive.
        pipeline_tasks = [run_pipeline_for_scenario(scenario, args) for scenario in scenarios]
        results_list = await asyncio.gather(*pipeline_tasks)
    finally:
        # Ensure monitor task is cancelled and awaited
        if monitor_task and not monitor_task.done():
            monitor_task.cancel()
            # Use gather with return_exceptions=True to wait for cancellation to complete
            await asyncio.gather(monitor_task, return_exceptions=True)
        # Print a newline to move past the monitor's line
        print()

    main_gather_end_time = time.monotonic()
    logger.info(f"Finished asyncio.gather (Total duration={main_gather_end_time - main_gather_start_time:.2f}s)")


    # --- Use Utility Function to Generate Metadata ---
    metadata = generate_run_metadata(
        run_type="scenario_pipeline",
        species=args.species,
        model=args.model,
        reasoning_level=args.reasoning_level,
        species_data=species_full_data,
        model_data=models_full_data
        # llm_config and reasoning_specs are picked up from imported defaults in the util
    )
    # --- End Metadata Generation ---

    # Combine Metadata and Results
    output_data = {"metadata": metadata, "results": results_list}

    # --- Use Centralized Save Function ---
    saved_file_path = save_results_with_standard_name(
        results_dir=results_dir_path,
        run_type=metadata.get("run_type", "scenario_pipeline"), # Get type from metadata
        species=args.species,
        model=args.model,
        level=args.reasoning_level,
        data_to_save=output_data,
        timestamp=metadata.get("run_timestamp") # Pass timestamp from metadata
    )

    if saved_file_path:
        print(f"Scenario pipeline results saved to {saved_file_path}") # Keep print for final user feedback
    else:
        # Error is already logged by save_results_with_standard_name or save_json
        print(f"Error saving scenario pipeline results.")

    return saved_file_path # Return the path string or None
    # --- End Centralized Save Function ---

# --- New Function for Single Scenario Run & Save ---
async def run_and_save_single_scenario(scenario_dict: dict, args: argparse.Namespace) -> str | None:
    """Runs a single scenario, generates metadata, and saves the result."""
    logger.info(f"Running single scenario pipeline for ID: {scenario_dict.get('id', 'unknown')}")
    single_result_data = await run_pipeline_for_scenario(scenario_dict, args)

    if not single_result_data:
        logger.error(f"Pipeline for scenario ID {scenario_dict.get('id', 'unknown')} returned no data.")
        return None

    results_list_for_file = [single_result_data]

    # --- Load Metadata Dependencies ---
    data_dir_path = Path(args.data_dir)
    metadata_deps = load_metadata_dependencies(data_dir_path)
    species_full_data = metadata_deps["species"]
    models_full_data = metadata_deps["models"]
    if "Error" in species_full_data or "Error" in models_full_data:
        logger.error("Failed to load essential metadata (species/models) for single scenario run.")
        return None
    # --- End Metadata Loading ---

    # --- Generate Metadata ---
    metadata = generate_run_metadata(
        run_type="scenario_pipeline_single", # Indicate single run
        species=args.species,
        model=args.model,
        reasoning_level=args.reasoning_level,
        species_data=species_full_data,
        model_data=models_full_data
    )
    # --- End Metadata Generation ---

    output_data_to_save = {"metadata": metadata, "results": results_list_for_file}

    # --- Use Centralized Save Function ---
    results_dir_path = Path(args.results_dir)
    scenario_id = scenario_dict.get("id", "unknown")

    saved_file_path = save_results_with_standard_name(
        results_dir=results_dir_path,
        run_type=metadata.get("run_type", "scenario_pipeline_single"), # Get type from metadata
        species=args.species,
        model=args.model,
        level=args.reasoning_level,
        data_to_save=output_data_to_save,
        item_id=scenario_id, # Pass the scenario ID
        timestamp=metadata.get("run_timestamp") # Pass timestamp from metadata
    )

    if not saved_file_path:
        # Error is already logged by save_results_with_standard_name or save_json
        logger.error(f"Failed to save single scenario result for ID: {scenario_id}") # Add specific log

    return saved_file_path # Return the path string or None
    # --- End Centralized Save Function ---
# --- End New Function ---


# --- New Synchronous Entry Point ---
def run_all_scenarios(cli_args=None): # Accept optional args from ethicsengine
    """Synchronous wrapper to run the main async logic."""
    # Use cli_args if provided, otherwise create an empty namespace
    args = cli_args if cli_args is not None else argparse.Namespace()

    # --- Determine effective arguments using getattr with defaults ---
    default_species = "Jiminies"
    default_model = "Deontological"
    default_reasoning_level = "low"
    default_data_dir = "data"
    default_results_dir = "results"
    default_scenarios_file = os.path.join("data", "scenarios.json")

    effective_species = getattr(args, 'species', default_species)
    effective_model = getattr(args, 'model', default_model)
    effective_reasoning_level = getattr(args, 'reasoning_level', default_reasoning_level)
    effective_data_dir = getattr(args, 'data_dir', default_data_dir)
    effective_results_dir = getattr(args, 'results_dir', default_results_dir)
    effective_scenarios_file = getattr(args, 'scenarios_file', default_scenarios_file)

    # Ensure None values passed from ethicsengine are handled (use defaults if None)
    effective_species = effective_species if effective_species is not None else default_species
    effective_model = effective_model if effective_model is not None else default_model
    effective_reasoning_level = effective_reasoning_level if effective_reasoning_level is not None else default_reasoning_level
    effective_data_dir = effective_data_dir if effective_data_dir is not None else default_data_dir
    effective_results_dir = effective_results_dir if effective_results_dir is not None else default_results_dir
    effective_scenarios_file = effective_scenarios_file if effective_scenarios_file is not None else default_scenarios_file

    # Create a namespace with the effective arguments to pass to main
    effective_args_ns = argparse.Namespace(
        species=effective_species,
        model=effective_model,
        reasoning_level=effective_reasoning_level,
        data_dir=effective_data_dir,
        results_dir=effective_results_dir,
        scenarios_file=effective_scenarios_file
    )

    logger.info(f"Executing run_all_scenarios with effective args: {effective_args_ns}")
    result_filename = None # Initialize result
    try:
        # Pass the resolved effective arguments to the async main function and capture the result
        result_filename = asyncio.run(main(effective_args=effective_args_ns))
        return result_filename # Return the filename on success
    except Exception as e:
        logger.error(f"Error during run_all_scenarios execution: {e}", exc_info=True)
        # Optionally return None or re-raise depending on desired error handling for the caller
        # For now, let's return None to indicate failure to the caller without crashing
        return None
        # Alternatively, re-raise if the caller should handle the exception:
        raise

if __name__ == "__main__":
    # Original __main__ block now calls the new synchronous entry point
    # after parsing its own args if run directly.
    script_args = parse_args()
    run_all_scenarios(script_args)
