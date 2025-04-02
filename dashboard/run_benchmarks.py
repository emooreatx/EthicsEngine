# EthicsEngine/run_benchmarks.py
#!/usr/bin/env python3
import argparse
import json
import os
import asyncio
import sys # Added for stderr
import time # Added for timing
from datetime import datetime
from pathlib import Path

# --- Updated Imports ---
# Import EthicsAgent from reasoning_agent
from reasoning_agent import EthicsAgent
# Import logger, semaphore, TrackedSemaphore from config
from config.config import logger, semaphore, TrackedSemaphore # Added semaphore imports
# Import new utility functions from dashboard_utils
from dashboard.dashboard_utils import (
    load_json, # Use the enhanced load_json
    save_json,
    load_metadata_dependencies,
    generate_run_metadata,
    save_results_with_standard_name # Import the new helper
)
# --- End Updated Imports ---

# --- CLI Semaphore Monitoring Task (Copied from run_scenario_pipelines.py) ---
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
    # (parse_args function remains the same)
    parser = argparse.ArgumentParser(description="Run EthicsEngine benchmarks")
    parser.add_argument("--data-dir", default="data", help="Path to the data directory")
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--bench-file", default=os.path.join("data", "simple_bench_public.json"), help="Path to the benchmark file")
    parser.add_argument("--species", default="Jiminies", help="Species name")
    parser.add_argument("--model", default="Deontological", help="Reasoning model")
    parser.add_argument("--reasoning-level", default="low", choices=["low", "medium", "high"], help="Reasoning level (low, medium, high)")
    return parser.parse_args()

def load_benchmarks(file_path):
    """Loads benchmark data, expecting a list under the 'eval_data' key."""
    try:
        file_path_obj = Path(file_path)
        if not file_path_obj.is_file():
            logger.error(f"Benchmark file path is not a file or does not exist: {file_path_obj}")
            return []
        # Use the utility load_json here
        data = load_json(file_path_obj) # Removed default={} argument
        if "Error" in data: # Check if load_json returned an error indicator
            logger.error(f"Failed to load benchmark JSON from {file_path_obj}: {data['Error']}")
            return []

        eval_data = data.get("eval_data")
        if isinstance(eval_data, list):
            return eval_data
        else:
            logger.error(f"Key 'eval_data' not found or not a list in {file_path_obj}")
            return []
    except Exception as e:
        # Catch any unexpected errors during processing
        logger.error(f"Unexpected error loading benchmarks from {file_path_obj}: {e}", exc_info=True)
        return []

async def run_item(item, answer_agent):
    # (run_item function remains the same, returning nested 'output')
    # It uses the agent's run_async, which handles the semaphore internally.
    question = item.get("prompt", ""); qid = item.get("question_id", "unknown"); expected = item.get("answer", "")
    # Construct prompt for benchmark task (expecting single letter answer)
    answer_payload = { "prompt": ( f"Carefully analyze the following question and options. Respond ONLY with the single capital letter corresponding to the best answer.\n\nQuestion:\n{question}" ) }
    logger.info(f"Running benchmark item with QID: {qid} for agent {answer_agent.species['name']}/{answer_agent.golden_pattern}")
    raw_response = ""
    try:
        # Agent's run_async handles semaphore acquisition/release
        answer_data = await answer_agent.run_async(answer_payload, f"bench_{qid}")
        raw_response = answer_data.get("result", "")
    except Exception as e: logger.error(f"Error running agent for QID {qid}: {e}", exc_info=True); raw_response = f"Error: Agent execution failed ({e})"

    logger.info(f"QID: {qid} - Raw Response: '{raw_response}' | Expected: '{expected}'")
    # Clean and evaluate the response
    response_cleaned = raw_response.strip().upper(); expected_cleaned = str(expected).strip().upper()
    is_error = raw_response.startswith("Error:")
    if is_error: evaluation_result = "Error"
    # Check if response is a single capital letter and matches expected
    elif (response_cleaned == expected_cleaned) and (len(response_cleaned) == 1) and ('A' <= response_cleaned <= 'Z'):
        evaluation_result = "Correct"
    else:
        evaluation_result = "Incorrect"

    logger.info(f"QID: {qid} - Cleaned Response: '{response_cleaned}' | Cleaned Expected: '{expected_cleaned}' | Evaluation: {evaluation_result}")
    # Return results in the nested structure expected by the UI/analysis
    return {
        "question_id": qid,
        "question": question,
        "expected_answer": expected,
        "output": { # Nested output structure
            "answer": raw_response,
            "judgement": evaluation_result
        }
    }

async def run_benchmarks_async(benchmarks, answer_agent):
    # (run_benchmarks_async function remains the same)
    # Runs multiple benchmark items concurrently using asyncio.gather
    if not benchmarks: logger.warning("No benchmark items to run."); return []
    logger.info(f"Running {len(benchmarks)} benchmarks asynchronously...")
    tasks = [run_item(item, answer_agent) for item in benchmarks]
    # Note: Semaphore isn't directly applied here at the gather level;
    # it's handled within each run_item call via answer_agent.run_async

    # Start CLI semaphore monitor task
    monitor_task = asyncio.create_task(monitor_semaphore_cli(semaphore)) # Use imported semaphore

    results_or_exceptions = []
    try:
        # Use return_exceptions=True to ensure gather completes even if some tasks fail
        results_or_exceptions = await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        # Ensure monitor task is cancelled and awaited
        if monitor_task and not monitor_task.done():
            monitor_task.cancel()
            # Use gather with return_exceptions=True to wait for cancellation to complete
            await asyncio.gather(monitor_task, return_exceptions=True)
        # Print a newline to move past the monitor's line (if it was printing)
        # Since we log now, this might not be strictly necessary, but doesn't hurt
        print() # Keep for potential future print debugging

    logger.info("Benchmark async gather completed.")


    # Process results, logging any exceptions
    processed_results = []
    for i, res_or_exc in enumerate(results_or_exceptions):
        item_qid = benchmarks[i].get("question_id", f"unknown_index_{i}")
        if isinstance(res_or_exc, Exception):
            logger.error(f"Benchmark item QID {item_qid} failed with exception: {res_or_exc}", exc_info=res_or_exc)
            # Create a placeholder error result structure consistent with run_item output
            processed_results.append({
                "question_id": item_qid,
                "question": benchmarks[i].get("prompt", "N/A"),
                "expected_answer": benchmarks[i].get("answer", "N/A"),
                "output": {
                    "answer": f"Error: Task failed - {res_or_exc}",
                    "judgement": "Error"
                }
            })
        elif isinstance(res_or_exc, dict):
            processed_results.append(res_or_exc)
        else:
            logger.warning(f"Benchmark item QID {item_qid} returned unexpected type: {type(res_or_exc)}. Value: {res_or_exc}")
            # Handle unexpected return type if necessary
            processed_results.append({
                "question_id": item_qid,
                "question": benchmarks[i].get("prompt", "N/A"),
                "expected_answer": benchmarks[i].get("answer", "N/A"),
                "output": {
                    "answer": f"Error: Unexpected return type - {type(res_or_exc)}",
                    "judgement": "Error"
                }
            })

    return processed_results

def run_benchmarks(cli_args=None): # Accept optional args
    """Main function to load data, run benchmarks, and save results."""
    # Use cli_args if provided, otherwise create an empty namespace
    # This ensures getattr doesn't fail if cli_args is None
    args = cli_args if cli_args is not None else argparse.Namespace()

    print("Running benchmarks...") # Keep this for user feedback

    # --- Determine effective arguments using getattr with defaults ---
    # Get defaults from the parser definition or hardcode them here
    default_species = "Jiminies"
    default_model = "Deontological"
    default_reasoning_level = "low"
    default_data_dir = "data"
    default_results_dir = "results"
    default_bench_file = os.path.join("data", "simple_bench_public.json")

    effective_species = getattr(args, 'species', default_species)
    effective_model = getattr(args, 'model', default_model)
    effective_reasoning_level = getattr(args, 'reasoning_level', default_reasoning_level)
    effective_data_dir = getattr(args, 'data_dir', default_data_dir)
    effective_results_dir = getattr(args, 'results_dir', default_results_dir)
    effective_bench_file = getattr(args, 'bench_file', default_bench_file)

    # Ensure None values passed from ethicsengine are handled (use defaults if None)
    effective_species = effective_species if effective_species is not None else default_species
    effective_model = effective_model if effective_model is not None else default_model
    effective_reasoning_level = effective_reasoning_level if effective_reasoning_level is not None else default_reasoning_level
    effective_data_dir = effective_data_dir if effective_data_dir is not None else default_data_dir
    effective_results_dir = effective_results_dir if effective_results_dir is not None else default_results_dir
    effective_bench_file = effective_bench_file if effective_bench_file is not None else default_bench_file


    logger.info(f"Executing benchmark run with effective args: species='{effective_species}', model='{effective_model}', level='{effective_reasoning_level}', data='{effective_data_dir}', results='{effective_results_dir}', bench_file='{effective_bench_file}'")

    # Convert paths AFTER ensuring they are not None
    data_dir_path = Path(effective_data_dir)
    results_dir_path = Path(effective_results_dir)
    bench_file_path_obj = Path(effective_bench_file)
    # --- End Argument Handling ---

    # --- Use Utility Function to Load Metadata Dependencies ---
    metadata_deps = load_metadata_dependencies(data_dir_path)
    species_full_data = metadata_deps["species"]
    models_full_data = metadata_deps["models"]
    if "Error" in species_full_data or "Error" in models_full_data:
        logger.error("Failed to load essential metadata (species/models). Exiting.")
        print("Error: Failed to load species.json or golden_patterns.json. Check logs.")
        return
    # --- End Metadata Loading ---

    # Load benchmarks using the determined path
    benchmarks = load_benchmarks(bench_file_path_obj)
    if not benchmarks:
        print(f"Error: No benchmark data loaded from {bench_file_path_obj}. Exiting.")
        logger.error(f"No benchmark data loaded from {bench_file_path_obj}. Exiting benchmark run.")
        return

    # Use determined paths and effective args for agent
    try:
        answer_agent = EthicsAgent(effective_species, effective_model, reasoning_level=effective_reasoning_level, data_dir=str(data_dir_path))
        logger.info(f"Running benchmarks with agent: {effective_species} - {effective_model} - {effective_reasoning_level}")
    except Exception as e:
        print(f"Error creating agent: {e}")
        logger.error(f"Error creating agent: {e}", exc_info=True)
        return

    # Run the benchmarks asynchronously
    results_list = asyncio.run(run_benchmarks_async(benchmarks, answer_agent))

    # Calculate summary statistics (remains the same)
    correct_count = sum(1 for r in results_list if r.get('output', {}).get('judgement') == "Correct")
    error_count = sum(1 for r in results_list if r.get('output', {}).get('judgement') == "Error")
    total_questions = len(results_list)
    accuracy = (correct_count / total_questions * 100) if total_questions > 0 else 0
    error_rate = (error_count / total_questions * 100) if total_questions > 0 else 0
    summary_msg = f"Benchmark Summary: {correct_count}/{total_questions} Correct ({accuracy:.2f}%). Errors: {error_count} ({error_rate:.2f}%)."
    print(summary_msg)
    logger.info(summary_msg)

    # --- Use Utility Function to Generate Metadata ---
    # Use the effective species/model/level
    metadata = generate_run_metadata(
        run_type="benchmark",
        species=effective_species,
        model=effective_model,
        reasoning_level=effective_reasoning_level,
        species_data=species_full_data,
        model_data=models_full_data
        # llm_config and reasoning_specs are picked up from imported defaults in the util
    )
    # --- End Metadata Generation ---

    output_data = {"metadata": metadata, "results": results_list}

    # --- Use Centralized Save Function ---
    saved_file_path = save_results_with_standard_name(
        results_dir=results_dir_path,
        run_type=metadata.get("run_type", "benchmark"), # Get type from metadata
        species=effective_species,
        model=effective_model,
        level=effective_reasoning_level,
        data_to_save=output_data,
        timestamp=metadata.get("run_timestamp") # Pass timestamp from metadata
    )

    if saved_file_path:
        print(f"Benchmark results saved to {saved_file_path}") # Keep print for final user feedback
    else:
        # Error is already logged by save_results_with_standard_name or save_json
        print(f"Error saving benchmark results.")

    return saved_file_path # Return the path string or None
    # --- End Centralized Save Function ---

# --- New Function for Single Benchmark Run & Save ---
async def run_and_save_single_benchmark(item_dict: dict, args: argparse.Namespace) -> str | None:
    """Runs a single benchmark item, generates metadata, and saves the result."""
    qid = item_dict.get("question_id", "unknown")
    logger.info(f"Running single benchmark pipeline for QID: {qid}")

    # --- Create Agent ---
    try:
        data_dir_path = Path(args.data_dir) # Ensure data_dir is a Path object if needed by agent
        answer_agent = EthicsAgent(args.species, args.model, reasoning_level=args.reasoning_level, data_dir=str(data_dir_path))
        logger.info(f"Agent created for single benchmark QID {qid}: {args.species} - {args.model} - {args.reasoning_level}")
    except Exception as e:
        logger.error(f"Error creating agent for single benchmark QID {qid}: {e}", exc_info=True)
        return None # Cannot proceed without agent
    # --- End Agent Creation ---

    # --- Run Single Item ---
    single_result_data = await run_item(item_dict, answer_agent)
    if not single_result_data:
        logger.error(f"Benchmark run for QID {qid} returned no data.")
        return None
    # --- End Run Single Item ---

    results_list_for_file = [single_result_data]

    # --- Load Metadata Dependencies ---
    data_dir_path = Path(args.data_dir) # Reuse path object
    metadata_deps = load_metadata_dependencies(data_dir_path)
    species_full_data = metadata_deps["species"]
    models_full_data = metadata_deps["models"]
    if "Error" in species_full_data or "Error" in models_full_data:
        logger.error("Failed to load essential metadata (species/models) for single benchmark run.")
        return None
    # --- End Metadata Loading ---

    # --- Generate Metadata ---
    metadata = generate_run_metadata(
        run_type="benchmark_single", # Indicate single run
        species=args.species,
        model=args.model,
        reasoning_level=args.reasoning_level,
        species_data=species_full_data,
        model_data=models_full_data
    )
    # Add benchmark-specific evaluation criteria
    metadata["evaluation_criteria"] = { "positive": ["BENCHMARK_CORRECT"], "negative": ["BENCHMARK_INCORRECT", "BENCHMARK_ERROR"] }
    # --- End Metadata Generation ---

    output_data_to_save = {"metadata": metadata, "results": results_list_for_file}

    # --- Use Centralized Save Function ---
    results_dir_path = Path(args.results_dir)

    saved_file_path = save_results_with_standard_name(
        results_dir=results_dir_path,
        run_type=metadata.get("run_type", "benchmark_single"), # Get type from metadata
        species=args.species,
        model=args.model,
        level=args.reasoning_level,
        data_to_save=output_data_to_save,
        item_id=qid, # Pass the question ID
        timestamp=metadata.get("run_timestamp") # Pass timestamp from metadata
    )

    if not saved_file_path:
        # Error is already logged by save_results_with_standard_name or save_json
        logger.error(f"Failed to save single benchmark result for QID: {qid}") # Add specific log

    return saved_file_path # Return the path string or None
    # --- End Centralized Save Function ---
# --- End New Function ---


if __name__ == "__main__":
    # Original __main__ block now calls the function after parsing its own args
    script_args = parse_args()
    run_benchmarks(script_args)
