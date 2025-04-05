# EthicsEngine/dashboard/run_benchmarks.py
#!/usr/bin/env python3
"""
Handles the execution of benchmark runs, both full suites and single items.

Provides functions to load benchmark data, run items using the EthicsAgent,
generate metadata, handle concurrent execution via semaphore, and save results
in a standardized format. Includes CLI argument parsing for standalone use
and a semaphore monitoring function for CLI runs.
"""
import argparse
import json
import os
import asyncio
import sys # For stderr output
import time # For timing operations
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

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
# This function is intended for use when running benchmarks via the main CLI entry point.
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
    parser = argparse.ArgumentParser(description="Run EthicsEngine benchmarks")
    parser.add_argument("--data-dir", default="data", help="Path to the data directory")
    parser.add_argument("--results-dir", default="results", help="Directory to save results")
    parser.add_argument("--bench-file", default=os.path.join("data", "simple_bench_public.json"), help="Path to the benchmark JSON file")
    parser.add_argument("--species", default="Neutral", help="Species name")
    parser.add_argument("--model", default="Agentic", help="Reasoning model (golden pattern)")
    parser.add_argument("--reasoning-level", default="low", choices=["low", "medium", "high"], help="Reasoning level")
    parser.add_argument("-m", "--multiple-runs", type=int, default=1, help="Number of concurrent runs (for standalone testing)")
    return parser.parse_args()

# --- Data Loading ---
def load_benchmarks(file_path: Path | str) -> list:
    """
    Loads benchmark items from a JSON file.

    Expects the JSON file to have a top-level key 'eval_data' containing a list
    of benchmark item dictionaries.

    Args:
        file_path: Path object or string path to the benchmark JSON file.

    Returns:
        A list of benchmark item dictionaries, or an empty list if loading fails.
    """
    try:
        file_path_obj = Path(file_path) # Ensure it's a Path object
        if not file_path_obj.is_file():
            # Log error if the path is not a file or doesn't exist
            logger.error(f"Benchmark file path is not a file or does not exist: {file_path_obj}")
            return []
        # Use the robust load_json utility
        data = load_json(file_path_obj)
        if isinstance(data, dict) and "Error" in data: # Check for load_json errors
            logger.error(f"Failed to load benchmark JSON from {file_path_obj}: {data['Error']}")
            return []
        # Extract the list under the 'eval_data' key
        eval_data = data.get("eval_data")
        if isinstance(eval_data, list):
            # Return the list if found and it's actually a list
            return eval_data
        else:
            # Log error if 'eval_data' key is missing or not a list
            logger.error(f"Key 'eval_data' not found or not a list in {file_path_obj}")
            return []
    except Exception as e:
        # Log any other unexpected errors during loading
        logger.error(f"Unexpected error loading benchmarks from {file_path_obj}: {e}", exc_info=True)
        return []

# --- Core Benchmark Execution Logic ---
async def run_item(item: dict, answer_agent: EthicsAgent) -> dict:
    """
    Runs a single benchmark item using the provided EthicsAgent.

    Args:
        item: A dictionary representing the benchmark item (must contain 'prompt', 'question_id', 'answer').
        answer_agent: An initialized EthicsAgent instance.

    Returns:
        A dictionary containing the structured result for this item, including
        input details, agent output, evaluation judgement, and decision tree.
    """
    # Extract data from the item dictionary
    question = item.get("prompt", "")
    qid = item.get("question_id", "unknown")
    expected = item.get("answer", "")

    # Format the prompt specifically for benchmark questions (expecting single letter answer)
    answer_payload = { "prompt": ( f"Carefully analyze the following question and options. Respond ONLY with the single capital letter corresponding to the best answer.\n\nQuestion:\n{question}" ) }
    logger.info(f"Running benchmark item with QID: {qid} for agent {answer_agent.species['name']}/{answer_agent.golden_pattern}")

    raw_response = ""
    reasoning_tree = None # Initialize reasoning_tree
    answer_data = {} # Initialize answer_data

    try:
        # Run the agent asynchronously
        answer_data = await answer_agent.run_async(answer_payload, f"bench_{qid}")
        raw_response = answer_data.get("result", "")
        # Capture the reasoning tree if available
        reasoning_tree = answer_data.get("reasoning_tree")
    except Exception as e:
        # Log errors during agent execution and set error response
        logger.error(f"Error running agent for QID {qid}: {e}", exc_info=True)
        raw_response = f"Error: Agent execution failed ({e})"
        # reasoning_tree remains None

    logger.info(f"QID: {qid} - Raw Response: '{raw_response}' | Expected: '{expected}'")

    # --- Evaluate the response ---
    response_cleaned = raw_response.strip().upper()
    expected_cleaned = str(expected).strip().upper()
    is_error = raw_response.startswith("Error:")

    if is_error:
        evaluation_result = "Error"
    elif (response_cleaned == expected_cleaned) and (len(response_cleaned) == 1) and ('A' <= response_cleaned <= 'Z'):
        # Correct if the cleaned response matches expected and is a single capital letter
        evaluation_result = "Correct"
    else:
        # Incorrect otherwise
        evaluation_result = "Incorrect"

    logger.info(f"QID: {qid} - Cleaned Response: '{response_cleaned}' | Cleaned Expected: '{expected_cleaned}' | Evaluation: {evaluation_result}")
    logger.debug(f"QID: {qid} - Value of reasoning_tree before returning: {'Present' if reasoning_tree else 'None'}")

    # --- Structure the result ---
    # Follows the defined output schema
    return {
        "item_id": qid, # Standardized key
        "item_text": question, # Standardized key
        "tags": [], # Placeholder for potential future tags
        "evaluation_criteria": {
            "expected_answer": expected # Expected answer nested here
        },
        "output": { # Agent's output nested here
            "answer": raw_response, # The raw response from the agent
            "judgement": evaluation_result # The evaluation result (Correct/Incorrect/Error)
        },
        "decision_tree": reasoning_tree # Include the reasoning tree (can be None)
    }

async def run_benchmarks_async(cli_args: Optional[argparse.Namespace] = None) -> Optional[str]:
    """
    Core async function to load benchmark data, run all items concurrently,
    generate metadata, calculate summary, and save results to a standardized file.

    Args:
        cli_args: An argparse.Namespace containing run parameters (species, model, etc.).
                  If None, defaults will be used.

    Returns:
        The absolute path string of the saved results file on success, or None on failure.
    """
    args = cli_args if cli_args is not None else argparse.Namespace()

    # --- Determine Effective Arguments (with defaults) ---
    # Set default values for parameters
    default_species = "Neutral"
    default_model = "Agentic"
    default_reasoning_level = "low"
    default_data_dir = "data"
    default_results_dir = "results"
    default_bench_file = os.path.join("data", "simple_bench_public.json")

    # Get values from args or use defaults
    effective_species = getattr(args, 'species', default_species)
    effective_model = getattr(args, 'model', default_model)
    effective_reasoning_level = getattr(args, 'reasoning_level', default_reasoning_level)
    effective_data_dir = getattr(args, 'data_dir', default_data_dir)
    effective_results_dir = getattr(args, 'results_dir', default_results_dir)
    effective_bench_file = getattr(args, 'bench_file', default_bench_file)

    # Ensure None values (potentially passed from UI/CLI) are replaced with defaults
    effective_species = effective_species if effective_species is not None else default_species
    effective_model = effective_model if effective_model is not None else default_model
    effective_reasoning_level = effective_reasoning_level if effective_reasoning_level is not None else default_reasoning_level
    effective_data_dir = effective_data_dir if effective_data_dir is not None else default_data_dir
    effective_results_dir = effective_results_dir if effective_results_dir is not None else default_results_dir
    effective_bench_file = effective_bench_file if effective_bench_file is not None else default_bench_file

    # Create a new namespace with the final effective arguments for clarity
    effective_args = argparse.Namespace(
        species=effective_species,
        model=effective_model,
        reasoning_level=effective_reasoning_level,
        data_dir=effective_data_dir,
        results_dir=effective_results_dir,
        bench_file=effective_bench_file
    )
    # --- End Argument Handling ---

    logger.info(f"Executing benchmark run with effective args: species='{effective_args.species}', model='{effective_args.model}', level='{effective_args.reasoning_level}', data='{effective_args.data_dir}', results='{effective_args.results_dir}', bench_file='{effective_args.bench_file}'")

    # Convert paths to Path objects
    data_dir_path = Path(effective_args.data_dir)
    results_dir_path = Path(effective_args.results_dir)
    bench_file_path_obj = Path(effective_args.bench_file)

    # --- Load Metadata Dependencies ---
    metadata_deps = load_metadata_dependencies(data_dir_path)
    species_full_data = metadata_deps["species"]
    models_full_data = metadata_deps["models"]
    if "Error" in species_full_data or "Error" in models_full_data:
        logger.error("Failed to load essential metadata (species/models). Exiting benchmark run.")
        print("Error: Failed to load species.json or golden_patterns.json. Check logs.")
        return None # Indicate failure

    # --- Load Benchmarks ---
    loaded_benchmarks = load_benchmarks(bench_file_path_obj)
    if not loaded_benchmarks:
        logger.error(f"No valid benchmarks loaded from {bench_file_path_obj}. Exiting benchmark run.")
        print(f"Error: No valid benchmarks loaded from {bench_file_path_obj}.")
        return None # Indicate failure

    # --- Create Agent ---
    try:
        # Instantiate the agent using effective arguments
        answer_agent = EthicsAgent(
            effective_args.species,
            effective_args.model,
            reasoning_level=effective_args.reasoning_level,
            data_dir=str(data_dir_path) # Agent expects string path
        )
        logger.info(f"Created agent for benchmark run: {effective_args.species} - {effective_args.model} - {effective_args.reasoning_level}")
    except Exception as e:
        # Handle errors during agent creation
        print(f"Error creating agent: {e}")
        logger.error(f"Error creating agent: {e}", exc_info=True)
        return None # Indicate failure

    # --- Run Benchmark Items Concurrently ---
    if not loaded_benchmarks: # Double check after loading
        logger.warning("No benchmark items to run."); return None
    logger.info(f"Running {len(loaded_benchmarks)} benchmarks asynchronously...")
    # Create a list of async tasks, one for each item
    tasks = [run_item(item, answer_agent) for item in loaded_benchmarks]

    # Run tasks concurrently using asyncio.gather
    # Note: Semaphore limiting is handled within answer_agent.run_async
    # The semaphore monitor task (if running) is managed by the caller (e.g., ethicsengine.py)
    results_or_exceptions = []
    try:
        # return_exceptions=True ensures gather doesn't stop on the first error
        results_or_exceptions = await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        # No need to cancel monitor task here; caller handles it
        pass

    logger.info("Benchmark async gather completed.")
    # --- End Run Benchmark Items ---

    # --- Process Results ---
    processed_results = []
    # Iterate through results/exceptions returned by gather
    for i, res_or_exc in enumerate(results_or_exceptions):
        # Get original item info for error reporting
        item_qid = loaded_benchmarks[i].get("question_id", f"unknown_index_{i}")
        if isinstance(res_or_exc, Exception):
            # Log exception and create an error placeholder in results
            logger.error(f"Benchmark item QID {item_qid} failed with exception: {res_or_exc}", exc_info=res_or_exc)
            processed_results.append({
                "item_id": item_qid, # Use standardized key
                "item_text": loaded_benchmarks[i].get("prompt", "N/A"),
                "evaluation_criteria": {"expected_answer": loaded_benchmarks[i].get("answer", "N/A")},
                "output": { "answer": f"Error: Task failed - {res_or_exc}", "judgement": "Error" },
                "decision_tree": None # No tree if error occurred
            })
        elif isinstance(res_or_exc, dict):
            # Append successful result dictionary
            processed_results.append(res_or_exc)
        else:
            # Handle unexpected return types
            logger.warning(f"Benchmark item QID {item_qid} returned unexpected type: {type(res_or_exc)}. Value: {res_or_exc}")
            processed_results.append({
                "item_id": item_qid,
                "item_text": loaded_benchmarks[i].get("prompt", "N/A"),
                "evaluation_criteria": {"expected_answer": loaded_benchmarks[i].get("answer", "N/A")},
                "output": { "answer": f"Error: Unexpected return type - {type(res_or_exc)}", "judgement": "Error" },
                "decision_tree": None
            })
    # --- End Process Results ---

    # --- Calculate Summary ---
    correct_count = sum(1 for r in processed_results if r.get('output', {}).get('judgement') == "Correct")
    error_count = sum(1 for r in processed_results if r.get('output', {}).get('judgement') == "Error")
    total_questions = len(processed_results)
    accuracy = (correct_count / total_questions * 100) if total_questions > 0 else 0
    error_rate = (error_count / total_questions * 100) if total_questions > 0 else 0
    summary_msg = f"Benchmark Summary: {correct_count}/{total_questions} Correct ({accuracy:.2f}%). Errors: {error_count} ({error_rate:.2f}%)."
    print(summary_msg) # Print summary to console
    logger.info(summary_msg) # Log summary
    # --- End Calculate Summary ---

    # --- Generate Metadata ---
    metadata = generate_run_metadata(
        run_type="benchmark", # Set run type
        species=effective_args.species,
        model=effective_args.model,
        reasoning_level=effective_args.reasoning_level,
        species_data=species_full_data,
        model_data=models_full_data
        # llm_config and reasoning_specs are taken from defaults in generate_run_metadata
    )
    # --- End Metadata Generation ---

    # --- Save Results ---
    # Combine metadata and processed results into the final output structure
    output_data = {"metadata": metadata, "results": processed_results}
    # Use the standardized saving function
    saved_file_path = save_results_with_standard_name(
        results_dir=results_dir_path,
        run_type=metadata.get("run_type", "benchmark"), # Get type from metadata
        species=effective_args.species,
        model=effective_args.model,
        level=effective_args.reasoning_level,
        data_to_save=output_data,
        timestamp=metadata.get("run_timestamp") # Use timestamp from metadata
    )

    if saved_file_path:
        print(f"Benchmark results saved to {saved_file_path}")
    else:
        print(f"Error saving benchmark results.")

    return saved_file_path # Return the path string or None
    # --- End Save Results ---

# --- Function for Single Benchmark Run & Save ---
async def run_and_save_single_benchmark(item_dict: dict, args: argparse.Namespace) -> Optional[str]:
    """
    Runs a single benchmark item, generates metadata, and saves the result
    to a uniquely named file.

    Args:
        item_dict: The dictionary representing the single benchmark item to run.
        args: An argparse.Namespace containing run parameters (species, model, etc.).

    Returns:
        The absolute path string of the saved results file on success, or None on failure.
    """
    qid = item_dict.get("question_id", "unknown")
    logger.info(f"Running single benchmark pipeline for QID: {qid}")

    # --- Create Agent ---
    try:
        # Apply defaults specifically for this single run's agent creation
        default_species = "Neutral"
        default_model = "Agentic"
        default_reasoning_level = "low"
        default_data_dir = "data"
        # Get args or defaults
        s_species = getattr(args, 'species', default_species)
        s_model = getattr(args, 'model', default_model)
        s_level = getattr(args, 'reasoning_level', default_reasoning_level)
        s_data_dir = getattr(args, 'data_dir', default_data_dir)
        # Ensure None is replaced by default
        s_species = s_species if s_species is not None else default_species
        s_model = s_model if s_model is not None else default_model
        s_level = s_level if s_level is not None else default_reasoning_level
        s_data_dir = s_data_dir if s_data_dir is not None else default_data_dir

        data_dir_path = Path(s_data_dir)
        # Instantiate the agent
        answer_agent = EthicsAgent(s_species, s_model, reasoning_level=s_level, data_dir=str(data_dir_path))
        logger.info(f"Agent created for single benchmark QID {qid}: {s_species} - {s_model} - {s_level}")
    except Exception as e:
        logger.error(f"Error creating agent for single benchmark QID {qid}: {e}", exc_info=True)
        return None # Failure
    # --- End Agent Creation ---

    # --- Run Single Item ---
    # Await the result from the core run_item function
    single_result_data = await run_item(item_dict, answer_agent)
    if not single_result_data:
        logger.error(f"Benchmark run for QID {qid} returned no data.")
        return None # Failure
    # --- End Run Single Item ---

    # Prepare results list (containing only the single result)
    results_list_for_file = [single_result_data]

    # --- Load Metadata Dependencies ---
    # Use the effective data dir path determined during agent creation
    metadata_deps = load_metadata_dependencies(data_dir_path)
    species_full_data = metadata_deps["species"]
    models_full_data = metadata_deps["models"]
    if "Error" in species_full_data or "Error" in models_full_data:
        logger.error("Failed to load essential metadata (species/models) for single benchmark run.")
        return None # Failure
    # --- End Metadata Loading ---

    # --- Generate Metadata ---
    # Use the effective args determined above for metadata generation
    metadata = generate_run_metadata(
        run_type="benchmark_single", # Specific run type for single item
        species=s_species,
        model=s_model,
        reasoning_level=s_level,
        species_data=species_full_data,
        model_data=models_full_data
    )
    # Add benchmark-specific evaluation criteria to metadata
    metadata["evaluation_criteria"] = { "positive": ["BENCHMARK_CORRECT"], "negative": ["BENCHMARK_INCORRECT", "BENCHMARK_ERROR"] }
    # --- End Metadata Generation ---

    # Combine metadata and the single result
    output_data_to_save = {"metadata": metadata, "results": results_list_for_file}

    # --- Use Centralized Save Function ---
    # Determine results directory from args or default
    default_results_dir = "results"
    s_results_dir = getattr(args, 'results_dir', default_results_dir)
    s_results_dir = s_results_dir if s_results_dir is not None else default_results_dir
    results_dir_path = Path(s_results_dir)

    # Call the save helper, providing the item_id for filename generation
    saved_file_path = save_results_with_standard_name(
        results_dir=results_dir_path,
        run_type=metadata.get("run_type", "benchmark_single"), # Use type from metadata
        species=s_species, # Use effective args
        model=s_model,     # Use effective args
        level=s_level,     # Use effective args
        data_to_save=output_data_to_save,
        item_id=qid, # Pass the specific item ID
        timestamp=metadata.get("run_timestamp") # Use timestamp from metadata
    )

    if not saved_file_path:
        logger.error(f"Failed to save single benchmark result for QID: {qid}")
        # Failure already logged by save_results_with_standard_name

    return saved_file_path # Return path string or None
# --- End Single Benchmark Function ---
