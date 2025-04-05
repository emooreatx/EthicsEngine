# EthicsEngine/dashboard/run_scenario_pipelines.py
#!/usr/bin/env python3
"""
Handles the execution of scenario pipelines, both full sets and single items.

A scenario pipeline typically involves multiple agent steps (e.g., planner, executor).
This script defines functions to load scenario data, run the pipeline for each
scenario using the EthicsAgent, generate metadata, handle concurrency via semaphore,
and save results in a standardized format. Includes CLI argument parsing for
standalone use and a semaphore monitoring function for CLI runs.
"""
import argparse
import json
import asyncio
import os
import sys # For stdout flushing (though less needed with logging)
import time # For timing operations
from datetime import datetime
from pathlib import Path
from typing import Any, Optional # Added Optional

# --- Project Imports ---
from reasoning_agent import EthicsAgent # The core agent class
from config.config import logger, semaphore, TrackedSemaphore # Logger, semaphore, and its type
from dashboard.dashboard_utils import (
    load_json, # Utility for loading JSON
    save_json, # Utility for saving JSON
    load_metadata_dependencies, # Helper to load species/model data
    generate_run_metadata, # Helper to create metadata dict
    save_results_with_standard_name # Helper to save results with standard naming
)

# --- CLI Semaphore Monitoring Task ---
# This function is intended for use when running scenarios via the main CLI entry point.
async def monitor_semaphore_cli(semaphore_instance: TrackedSemaphore, interval: float = 2.0):
    """
    Periodically logs the status (active, waiting, capacity) of the TrackedSemaphore.
    Designed to be run as a background task during concurrent CLI operations.

    Args:
        semaphore_instance: The TrackedSemaphore instance to monitor.
        interval: How often (in seconds) to log the status.
    """
    # Validate the semaphore instance
    if not hasattr(semaphore_instance, 'capacity') or not hasattr(semaphore_instance, 'active_count') or not hasattr(semaphore_instance, 'waiting_count'):
        logger.error("Monitor: Invalid TrackedSemaphore instance provided (missing properties).")
        return

    capacity = semaphore_instance.capacity
    logger.info(f"Starting CLI semaphore monitor (Capacity: {capacity}, Interval: {interval}s)")
    try:
        # Loop indefinitely until cancelled
        while True:
            active_count = semaphore_instance.active_count
            waiting_count = semaphore_instance.waiting_count
            # Log current status
            logger.info(f"running: {active_count} waiting: {waiting_count} limit: {capacity}")
            await asyncio.sleep(interval) # Wait for the specified interval
    except asyncio.CancelledError:
        # Log when the task is cancelled (expected during shutdown)
        logger.info("CLI semaphore monitor cancelled.")
    except Exception as e:
        # Log any unexpected errors during monitoring
        logger.error(f"CLI semaphore monitor error: {e}", exc_info=True)

# --- Argument Parsing (for standalone use/testing) ---
def parse_args():
    """
    Parses command-line arguments if the script is run directly.
    Note: This is generally not used when called from ethicsengine.py.
    """
    parser = argparse.ArgumentParser(
        description="Run EthicsEngine scenario pipelines (Planner -> Executor)."
    )
    parser.add_argument("--data-dir", default="data", help="Path to the data directory")
    parser.add_argument("--scenarios-file", default=os.path.join("data","scenarios.json"), help="Path to scenarios JSON file (expects list format)")
    parser.add_argument("--results-dir", default="results", help="Directory to save the results")
    parser.add_argument("--species", default="Neutral", help="Species name (for planner & executor)")
    parser.add_argument("--model", default="Agentic", help="Reasoning model (golden pattern)")
    parser.add_argument("--reasoning-level", default="low", choices=["low", "medium", "high"], help="Reasoning level")
    # Note: Concurrency for multiple runs is handled by the main ethicsengine.py script
    return parser.parse_args()

# --- Data Loading ---
def load_scenarios(path: Path | str) -> list:
    """
    Loads scenario items from a JSON file.

    Expects the JSON file to contain a list of scenario dictionaries,
    each having at least 'id' and 'prompt' keys.

    Args:
        path: Path object or string path to the scenarios JSON file.

    Returns:
        A list of valid scenario item dictionaries, or an empty list if loading fails.
    """
    try:
        file_path_obj = Path(path) # Ensure it's a Path object
        if not file_path_obj.is_file():
            # Log error if the path is not a file or doesn't exist
            logger.error(f"Scenarios file path is not a file or does not exist: {file_path_obj}")
            return []
        # Use the robust load_json utility, defaulting to an empty list on error
        data = load_json(file_path_obj, default_data=[])
        if isinstance(data, dict) and "Error" in data: # Check for load_json errors
             logger.error(f"Failed to load scenarios JSON from {file_path_obj}: {data['Error']}")
             return []

        # Check if the loaded data is a list
        if isinstance(data, list):
            logger.info(f"Loading scenarios from list format in {file_path_obj}")
            valid_scenarios = []
            # Validate basic structure of each item in the list
            for index, item in enumerate(data):
                if isinstance(item, dict) and "id" in item and "prompt" in item:
                    valid_scenarios.append(item)
                else:
                    # Log warning for invalid items
                    logger.warning(f"Skipping invalid scenario format at index {index} in {file_path_obj}: {item}")
            return valid_scenarios
        else:
            # Log error if the file root is not a list
            logger.error(f"Unexpected format in scenarios file: {file_path_obj}. Expected a JSON list.")
            return []
    except Exception as e:
        # Log any other unexpected errors during loading
        logger.error(f"Unexpected error loading scenarios from {path}: {e}", exc_info=True)
        return []

# --- Core Pipeline Execution Logic ---
async def run_pipeline_for_scenario(scenario: dict, args: argparse.Namespace) -> dict:
    """
    Runs the two-stage (planner -> executor) pipeline for a single scenario.

    Args:
        scenario: A dictionary representing the scenario item (must contain 'id', 'prompt').
        args: An argparse.Namespace containing run parameters (species, model, etc.).

    Returns:
        A dictionary containing the structured result for this scenario pipeline,
        including inputs, planner/executor outputs, and the planner's decision tree.
    """
    pipeline_start_time = time.monotonic()
    # Extract scenario details
    scenario_id = scenario.get("id", "unknown_id")
    scenario_text = scenario.get("prompt", "")
    logger.info(f"Pipeline {scenario_id}: Started.")
    scenario_tags = scenario.get("tags", []) # Get tags if present
    scenario_eval_criteria = scenario.get("evaluation_criteria", {}) # Get criteria if present

    # --- Planner Stage ---
    planner_role = "Create an executable, concise, 3 step plan for this situation:"
    planner_prompt = f"{planner_role} {scenario_text}"
    logger.info(f"Pipeline {scenario_id}: Running planner")
    planner_output = ""
    planner_tree = None # Initialize planner tree
    planner_start_time = time.monotonic()
    try:
        # Create a planner agent instance (could potentially reuse agents)
        planner_agent = EthicsAgent(args.species, args.model, reasoning_level=args.reasoning_level, data_dir=args.data_dir)
        logger.debug(f"Pipeline {scenario_id}: Awaiting planner run_async (T={time.monotonic() - pipeline_start_time:.2f}s)")
        # Run the planner agent (uses semaphore internally)
        planner_response_dict = await planner_agent.run_async({"prompt": planner_prompt}, f"{scenario_id}_planner")
        planner_end_time = time.monotonic()
        logger.info(f"Pipeline {scenario_id}: Planner run_async finished (duration={planner_end_time - planner_start_time:.2f}s, T={planner_end_time - pipeline_start_time:.2f}s)")
        planner_output = planner_response_dict.get("result", "Error: No result")
        planner_tree = planner_response_dict.get("reasoning_tree") # Capture the planner's tree
    except Exception as e:
        # Log errors during planner execution
        logger.error(f"Pipeline {scenario_id}: Planner Error - {e}", exc_info=True)
        planner_output = f"Error: Planner failed - {e}"
        planner_tree = None # Ensure tree is None on error

    # --- Executor Stage ---
    executor_role = "Execute the following plan rapidly and effectively:"
    executor_output = "" # Initialize executor output
    executor_start_time = time.monotonic()
    if "Error:" in planner_output:
         # Skip executor if planner failed
         executor_prompt = f"{executor_role} Planner failed, cannot execute."
         logger.warning(f"Pipeline {scenario_id}: Skipping executor due to planner error.")
         executor_output = "Error: Skipped due to planner failure."
    else:
         # Run executor with the planner's output as the plan
         executor_prompt = f"{executor_role} {planner_output}"
         logger.info(f"Pipeline {scenario_id}: Running executor")
         try:
             # Create an executor agent instance (could potentially reuse agents)
             executor_agent = EthicsAgent(args.species, args.model, reasoning_level=args.reasoning_level, data_dir=args.data_dir)
             logger.debug(f"Pipeline {scenario_id}: Awaiting executor run_async (T={time.monotonic() - pipeline_start_time:.2f}s)")
             # Run the executor agent (uses semaphore internally)
             executor_response_dict = await executor_agent.run_async({"prompt": executor_prompt}, f"{scenario_id}_executor")
             executor_end_time = time.monotonic()
             logger.info(f"Pipeline {scenario_id}: Executor run_async finished (duration={executor_end_time - executor_start_time:.2f}s, T={executor_end_time - pipeline_start_time:.2f}s)")
             executor_output = executor_response_dict.get("result", "Error: No result")
             # Note: Executor's reasoning tree is currently not captured/saved. Could be added if needed.
         except Exception as e:
             # Log errors during executor execution
             logger.error(f"Pipeline {scenario_id}: Executor Error - {e}", exc_info=True)
             executor_output = f"Error: Executor failed - {e}"

    pipeline_end_time = time.monotonic()
    logger.info(f"Pipeline {scenario_id}: Finished (Total time={pipeline_end_time - pipeline_start_time:.2f}s)")

    # --- Structure the result ---
    # Follows the defined output schema
    return {
        "item_id": scenario_id, # Standardized key
        "item_text": scenario_text, # Standardized key
        "tags": scenario_tags, # Include tags from original scenario
        "evaluation_criteria": scenario_eval_criteria, # Include criteria from original scenario
        "output": { # Nested output structure
            "planner": planner_output,
            "executor": executor_output
        },
        "decision_tree": planner_tree # Include the planner's reasoning tree
    }

async def run_all_scenarios_async(cli_args: Optional[argparse.Namespace] = None) -> Optional[str]:
    """
    Core async function to load scenario data, run all pipelines concurrently,
    generate metadata, and save results to a standardized file.

    Args:
        cli_args: An argparse.Namespace containing run parameters (species, model, etc.).
                  If None, defaults will be used.

    Returns:
        The absolute path string of the saved results file on success, or None on failure.
    """
    args = cli_args if cli_args is not None else argparse.Namespace()

    # --- Determine Effective Arguments (with defaults) ---
    # Set default values
    default_species = "Neutral"
    default_model = "Agentic"
    default_reasoning_level = "low"
    default_data_dir = "data"
    default_results_dir = "results"
    default_scenarios_file = os.path.join("data", "scenarios.json")

    # Get values from args or use defaults
    effective_species = getattr(args, 'species', default_species)
    effective_model = getattr(args, 'model', default_model)
    effective_reasoning_level = getattr(args, 'reasoning_level', default_reasoning_level)
    effective_data_dir = getattr(args, 'data_dir', default_data_dir)
    effective_results_dir = getattr(args, 'results_dir', default_results_dir)
    effective_scenarios_file = getattr(args, 'scenarios_file', default_scenarios_file)

    # Ensure None values are replaced with defaults
    effective_species = effective_species if effective_species is not None else default_species
    effective_model = effective_model if effective_model is not None else default_model
    effective_reasoning_level = effective_reasoning_level if effective_reasoning_level is not None else default_reasoning_level
    effective_data_dir = effective_data_dir if effective_data_dir is not None else default_data_dir
    effective_results_dir = effective_results_dir if effective_results_dir is not None else default_results_dir
    effective_scenarios_file = effective_scenarios_file if effective_scenarios_file is not None else default_scenarios_file

    # Create a new namespace with effective arguments
    effective_args = argparse.Namespace(
        species=effective_species,
        model=effective_model,
        reasoning_level=effective_reasoning_level,
        data_dir=effective_data_dir,
        results_dir=effective_results_dir,
        scenarios_file=effective_scenarios_file
    )
    # --- End Argument Handling ---

    logger.info(f"Running scenario pipelines: {effective_args.species} - {effective_args.model} - {effective_args.reasoning_level}")

    # Convert paths to Path objects
    data_dir_path = Path(effective_args.data_dir)
    results_dir_path = Path(effective_args.results_dir)

    # --- Load Metadata Dependencies ---
    metadata_deps = load_metadata_dependencies(data_dir_path)
    species_full_data = metadata_deps["species"]
    models_full_data = metadata_deps["models"]
    if "Error" in species_full_data or "Error" in models_full_data:
        logger.error("Failed to load essential metadata (species/models). Exiting scenario run.")
        print("Error: Failed to load species.json or golden_patterns.json. Check logs.")
        return None # Indicate failure

    # --- Load Scenarios ---
    scenario_file_path_obj = Path(effective_args.scenarios_file)
    scenarios = load_scenarios(scenario_file_path_obj)
    if not scenarios:
        logger.error(f"No valid scenarios loaded from {scenario_file_path_obj}. Exiting scenario run.")
        print(f"Error: No valid scenarios loaded from {scenario_file_path_obj}.")
        return None # Indicate failure

    # --- Run Pipelines Concurrently ---
    main_gather_start_time = time.monotonic()
    logger.info(f"Starting asyncio.gather for {len(scenarios)} pipeline tasks...")

    # Create a list of async tasks, one for each scenario pipeline
    # Pass the effective_args namespace to each pipeline run
    pipeline_tasks = [run_pipeline_for_scenario(scenario, effective_args) for scenario in scenarios]

    # Run tasks concurrently using asyncio.gather
    # Semaphore limiting is handled within the agent's run_async method
    # Monitor task (if running) is handled by the caller (e.g., ethicsengine.py)
    results_list = []
    try:
        # return_exceptions=True ensures gather doesn't stop on the first error
        results_or_exceptions = await asyncio.gather(*pipeline_tasks, return_exceptions=True)

        # Process results, logging exceptions
        for i, res_or_exc in enumerate(results_or_exceptions):
            scenario_id = scenarios[i].get("id", f"unknown_index_{i}") # Get ID for logging
            if isinstance(res_or_exc, Exception):
                # Log exception and create an error placeholder
                logger.error(f"Scenario pipeline for ID {scenario_id} failed with exception: {res_or_exc}", exc_info=res_or_exc)
                results_list.append({
                    "item_id": scenario_id, # Use standardized key
                    "error": f"Task failed: {res_or_exc}"
                })
            elif isinstance(res_or_exc, dict):
                 # Append successful result dictionary
                 results_list.append(res_or_exc)
            else:
                 # Handle unexpected return types
                 logger.warning(f"Scenario pipeline for ID {scenario_id} returned unexpected type: {type(res_or_exc)}. Value: {res_or_exc}")
                 results_list.append({
                     "item_id": scenario_id,
                     "error": f"Unexpected return type: {type(res_or_exc)}"
                 })
    finally:
        # No need to cancel monitor task here; caller handles it
        pass

    main_gather_end_time = time.monotonic()
    logger.info(f"Finished asyncio.gather (Total duration={main_gather_end_time - main_gather_start_time:.2f}s)")
    # --- End Run Pipelines ---

    # --- Generate Metadata ---
    metadata = generate_run_metadata(
        run_type="scenario_pipeline", # Set run type
        species=effective_args.species,
        model=effective_args.model,
        reasoning_level=effective_args.reasoning_level,
        species_data=species_full_data,
        model_data=models_full_data
        # llm_config and reasoning_specs are taken from defaults
    )
    # --- End Metadata Generation ---

    # --- Save Results ---
    # Filter out potential error placeholders before saving
    final_results_to_save = [r for r in results_list if "error" not in r]
    output_data = {"metadata": metadata, "results": final_results_to_save}

    # Use the standardized saving function
    saved_file_path = save_results_with_standard_name(
        results_dir=results_dir_path,
        run_type=metadata.get("run_type", "scenario_pipeline"), # Get type from metadata
        species=effective_args.species,
        model=effective_args.model,
        level=effective_args.reasoning_level,
        data_to_save=output_data,
        timestamp=metadata.get("run_timestamp") # Use timestamp from metadata
    )

    if saved_file_path:
        print(f"Scenario pipeline results saved to {saved_file_path}")
    else:
        print(f"Error saving scenario pipeline results.")

    return saved_file_path # Return the path string or None
    # --- End Save Results ---

# --- Function for Single Scenario Run & Save ---
async def run_and_save_single_scenario(scenario_dict: dict, args: argparse.Namespace) -> Optional[str]:
    """
    Runs a single scenario pipeline, generates metadata, and saves the result
    to a uniquely named file.

    Args:
        scenario_dict: The dictionary representing the single scenario item to run.
        args: An argparse.Namespace containing run parameters (species, model, etc.).

    Returns:
        The absolute path string of the saved results file on success, or None on failure.
    """
    scenario_id = scenario_dict.get("id", "unknown") # Get ID for logging/filename
    logger.info(f"Running single scenario pipeline for ID: {scenario_id}")

    # --- Run Single Pipeline ---
    # Await the result from the core run_pipeline_for_scenario function
    single_result_data = await run_pipeline_for_scenario(scenario_dict, args)
    if not single_result_data:
        logger.error(f"Pipeline for scenario ID {scenario_id} returned no data.")
        return None # Failure
    # --- End Run Single Pipeline ---

    # Prepare results list (containing only the single result)
    results_list_for_file = [single_result_data]

    # --- Load Metadata Dependencies ---
    # Use data_dir from the passed args
    data_dir_path = Path(args.data_dir)
    metadata_deps = load_metadata_dependencies(data_dir_path)
    species_full_data = metadata_deps["species"]
    models_full_data = metadata_deps["models"]
    if "Error" in species_full_data or "Error" in models_full_data:
        logger.error("Failed to load essential metadata (species/models) for single scenario run.")
        return None # Failure
    # --- End Metadata Loading ---

    # --- Generate Metadata ---
    # Use args passed to this function for metadata
    metadata = generate_run_metadata(
        run_type="scenario_pipeline_single", # Specific run type for single item
        species=args.species,
        model=args.model,
        reasoning_level=args.reasoning_level,
        species_data=species_full_data,
        model_data=models_full_data
    )
    # Note: Evaluation criteria for single scenarios are typically within the item itself
    # --- End Metadata Generation ---

    # Combine metadata and the single result
    output_data_to_save = {"metadata": metadata, "results": results_list_for_file}

    # --- Use Centralized Save Function ---
    # Determine results directory from args
    results_dir_path = Path(args.results_dir)

    # Call the save helper, providing the item_id for filename generation
    saved_file_path = save_results_with_standard_name(
        results_dir=results_dir_path,
        run_type=metadata.get("run_type", "scenario_pipeline_single"), # Use type from metadata
        species=args.species,
        model=args.model,
        level=args.reasoning_level,
        data_to_save=output_data_to_save,
        item_id=scenario_id, # Pass the specific scenario ID
        timestamp=metadata.get("run_timestamp") # Use timestamp from metadata
    )

    if not saved_file_path:
        logger.error(f"Failed to save single scenario result for ID: {scenario_id}")
        # Failure already logged by save_results_with_standard_name

    return saved_file_path # Return path string or None
# --- End Single Scenario Function ---
