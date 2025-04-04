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
from typing import Dict, Any, Optional # Added typing

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
# This function definition remains, but it will be called by the main execution script (e.g., ethicsengine.py)
async def monitor_semaphore_cli(semaphore_instance: TrackedSemaphore, interval: float = 2.0): # Type hint TrackedSemaphore
    """Periodically logs the TrackedSemaphore status."""
    if not hasattr(semaphore_instance, 'capacity') or not hasattr(semaphore_instance, 'active_count') or not hasattr(semaphore_instance, 'waiting_count'): # Added waiting_count check
        logger.error("Monitor: Invalid TrackedSemaphore instance provided (missing properties).")
        return
    capacity = semaphore_instance.capacity
    logger.info(f"Starting CLI semaphore monitor (Capacity: {capacity}, Interval: {interval}s)")
    try:
        while True:
            active_count = semaphore_instance.active_count
            waiting_count = semaphore_instance.waiting_count # Get waiting count
            logger.info(f"running: {active_count} waiting: {waiting_count} limit: {capacity}")
            await asyncio.sleep(interval) # Use the interval parameter
    except asyncio.CancelledError:
        logger.info("CLI semaphore monitor cancelled.")
    except Exception as e:
        logger.error(f"CLI semaphore monitor error: {e}", exc_info=True)
# --- End CLI Semaphore Monitoring Task ---


def parse_args():
    # This function remains for potential direct script usage or testing
    parser = argparse.ArgumentParser(description="Run EthicsEngine benchmarks")
    parser.add_argument("--data-dir", default="data", help="Path to the data directory")
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--bench-file", default=os.path.join("data", "simple_bench_public.json"), help="Path to the benchmark file")
    parser.add_argument("--species", default="Neutral", help="Species name") # Default changed to Neutral
    parser.add_argument("--model", default="Agentic", help="Reasoning model") # Default changed to Agentic
    parser.add_argument("--reasoning-level", default="low", choices=["low", "medium", "high"], help="Reasoning level (low, medium, high)")
    parser.add_argument("-m", "--multiple-runs", type=int, default=1, help="Number of concurrent benchmark jobs to run") # Kept for direct run, but not used by ethicsengine call
    return parser.parse_args()

def load_benchmarks(file_path):
    """Loads benchmark data, expecting a list under the 'eval_data' key."""
    try:
        file_path_obj = Path(file_path)
        if not file_path_obj.is_file():
            logger.error(f"Benchmark file path is not a file or does not exist: {file_path_obj}")
            return []
        data = load_json(file_path_obj)
        if "Error" in data:
            logger.error(f"Failed to load benchmark JSON from {file_path_obj}: {data['Error']}")
            return []
        eval_data = data.get("eval_data")
        if isinstance(eval_data, list):
            return eval_data
        else:
            logger.error(f"Key 'eval_data' not found or not a list in {file_path_obj}")
            return []
    except Exception as e:
        logger.error(f"Unexpected error loading benchmarks from {file_path_obj}: {e}", exc_info=True)
        return []

async def run_item(item, answer_agent):
    """Runs a single benchmark item using the provided agent."""
    question = item.get("prompt", ""); qid = item.get("question_id", "unknown"); expected = item.get("answer", "")
    answer_payload = { "prompt": ( f"Carefully analyze the following question and options. Respond ONLY with the single capital letter corresponding to the best answer.\n\nQuestion:\n{question}" ) }
    logger.info(f"Running benchmark item with QID: {qid} for agent {answer_agent.species['name']}/{answer_agent.golden_pattern}")
    raw_response = ""
    # Initialize reasoning_tree to ensure it exists even if agent fails
    reasoning_tree = None
    answer_data = {} # Initialize answer_data as well
    try:
        answer_data = await answer_agent.run_async(answer_payload, f"bench_{qid}")
        raw_response = answer_data.get("result", "")
        # Capture the reasoning tree AFTER the await completes successfully
        reasoning_tree = answer_data.get("reasoning_tree")
    except Exception as e:
        logger.error(f"Error running agent for QID {qid}: {e}", exc_info=True); raw_response = f"Error: Agent execution failed ({e})"
        # Ensure reasoning_tree remains None or set to an error indicator if preferred

    logger.info(f"QID: {qid} - Raw Response: '{raw_response}' | Expected: '{expected}'")
    response_cleaned = raw_response.strip().upper(); expected_cleaned = str(expected).strip().upper()
    is_error = raw_response.startswith("Error:")
    if is_error: evaluation_result = "Error"
    elif (response_cleaned == expected_cleaned) and (len(response_cleaned) == 1) and ('A' <= response_cleaned <= 'Z'):
        evaluation_result = "Correct"
    else:
        evaluation_result = "Incorrect"

    logger.info(f"QID: {qid} - Cleaned Response: '{response_cleaned}' | Cleaned Expected: '{expected_cleaned}' | Evaluation: {evaluation_result}")
    # --- DEBUG LOGGING ---
    logger.debug(f"QID: {qid} - Value of reasoning_tree before returning: {'Present' if reasoning_tree else 'None'}")
    # --- END DEBUG LOGGING ---
    return {
        "item_id": qid, # Renamed from question_id
        "item_text": question, # Renamed from question
        # Removed expected_answer from top level
        "tags": [], # Added for consistency
        "evaluation_criteria": {
            "expected_answer": expected # Moved here
        },
        "output": { # Nested output structure
            "answer": raw_response,
            "judgement": evaluation_result
        },
        # Ensure the key is always present, even if the value is None
        "decision_tree": reasoning_tree
    }

# Renamed first arg, added default handling, agent creation, benchmark loading, metadata/saving
async def run_benchmarks_async(cli_args=None):
    """Core async function to load data, run all benchmark items, and save results."""
    # Use cli_args if provided, otherwise create an empty namespace
    args = cli_args if cli_args is not None else argparse.Namespace()

    # --- Determine effective arguments using getattr with defaults ---
    default_species = "Neutral" # Default changed to Neutral
    default_model = "Agentic" # Default changed to Agentic
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

    # Create a new args object with effective values
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

    # Convert paths AFTER ensuring they are not None
    data_dir_path = Path(effective_args.data_dir)
    results_dir_path = Path(effective_args.results_dir)
    bench_file_path_obj = Path(effective_args.bench_file)

    # --- Load Metadata Dependencies ---
    metadata_deps = load_metadata_dependencies(data_dir_path)
    species_full_data = metadata_deps["species"]
    models_full_data = metadata_deps["models"]
    if "Error" in species_full_data or "Error" in models_full_data:
        logger.error("Failed to load essential metadata (species/models). Exiting.")
        print("Error: Failed to load species.json or golden_patterns.json. Check logs.")
        return None # Return None on failure
    # --- End Metadata Loading ---

    # --- Load Benchmarks ---
    loaded_benchmarks = load_benchmarks(bench_file_path_obj)
    if not loaded_benchmarks:
        logger.error(f"No valid benchmarks loaded from {bench_file_path_obj}.")
        print(f"Error: No valid benchmarks loaded from {bench_file_path_obj}.")
        return None # Return None on failure
    # --- End Load Benchmarks ---

    # --- Create Agent ---
    try:
        answer_agent = EthicsAgent(
            effective_args.species,
            effective_args.model,
            reasoning_level=effective_args.reasoning_level,
            data_dir=str(data_dir_path) # Agent expects string path
        )
        logger.info(f"Created agent for benchmark run: {effective_args.species} - {effective_args.model} - {effective_args.reasoning_level}")
    except Exception as e:
        print(f"Error creating agent: {e}")
        logger.error(f"Error creating agent: {e}", exc_info=True)
        return None # Return None on agent creation failure
    # --- End Agent Creation ---

    # --- Run Benchmark Items Concurrently ---
    if not loaded_benchmarks: # Double check after loading
        logger.warning("No benchmark items to run."); return None
    logger.info(f"Running {len(loaded_benchmarks)} benchmarks asynchronously...") # Use len on loaded list
    tasks = [run_item(item, answer_agent) for item in loaded_benchmarks] # Use loaded list

    # Monitor is handled by the caller (ethicsengine.py)
    results_or_exceptions = []
    try:
        results_or_exceptions = await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        pass # Monitor cancellation handled by caller

    logger.info("Benchmark async gather completed.")
    # --- End Run Benchmark Items ---

    # --- Process Results ---
    processed_results = []
    for i, res_or_exc in enumerate(results_or_exceptions):
        # Use loaded_benchmarks to get original item info for error reporting
        item_qid = loaded_benchmarks[i].get("question_id", f"unknown_index_{i}")
        if isinstance(res_or_exc, Exception):
            logger.error(f"Benchmark item QID {item_qid} failed with exception: {res_or_exc}", exc_info=res_or_exc)
            processed_results.append({
                "question_id": item_qid,
                "question": loaded_benchmarks[i].get("prompt", "N/A"),
                "expected_answer": loaded_benchmarks[i].get("answer", "N/A"),
                "output": { "answer": f"Error: Task failed - {res_or_exc}", "judgement": "Error" }
            })
        elif isinstance(res_or_exc, dict):
            processed_results.append(res_or_exc)
        else:
            logger.warning(f"Benchmark item QID {item_qid} returned unexpected type: {type(res_or_exc)}. Value: {res_or_exc}")
            processed_results.append({
                "question_id": item_qid,
                "question": loaded_benchmarks[i].get("prompt", "N/A"),
                "expected_answer": loaded_benchmarks[i].get("answer", "N/A"),
                "output": { "answer": f"Error: Unexpected return type - {type(res_or_exc)}", "judgement": "Error" }
            })
    # --- End Process Results ---

    # --- Calculate Summary ---
    correct_count = sum(1 for r in processed_results if r.get('output', {}).get('judgement') == "Correct")
    error_count = sum(1 for r in processed_results if r.get('output', {}).get('judgement') == "Error")
    total_questions = len(processed_results)
    accuracy = (correct_count / total_questions * 100) if total_questions > 0 else 0
    error_rate = (error_count / total_questions * 100) if total_questions > 0 else 0
    summary_msg = f"Benchmark Summary: {correct_count}/{total_questions} Correct ({accuracy:.2f}%). Errors: {error_count} ({error_rate:.2f}%)."
    print(summary_msg)
    logger.info(summary_msg)
    # --- End Calculate Summary ---

    # --- Generate Metadata ---
    metadata = generate_run_metadata(
        run_type="benchmark",
        species=effective_args.species,
        model=effective_args.model,
        reasoning_level=effective_args.reasoning_level,
        species_data=species_full_data,
        model_data=models_full_data
    )
    # --- End Metadata Generation ---

    # --- Save Results ---
    output_data = {"metadata": metadata, "results": processed_results}
    saved_file_path = save_results_with_standard_name(
        results_dir=results_dir_path,
        run_type=metadata.get("run_type", "benchmark"),
        species=effective_args.species,
        model=effective_args.model,
        level=effective_args.reasoning_level,
        data_to_save=output_data,
        timestamp=metadata.get("run_timestamp")
    )

    if saved_file_path:
        print(f"Benchmark results saved to {saved_file_path}")
    else:
        print(f"Error saving benchmark results.")

    return saved_file_path # Return the path string or None
    # --- End Save Results ---


# --- Function for Single Benchmark Run & Save ---
# This function remains largely the same, but calls the updated run_item
async def run_and_save_single_benchmark(item_dict: dict, args: argparse.Namespace) -> str | None:
    """Runs a single benchmark item, generates metadata, and saves the result."""
    qid = item_dict.get("question_id", "unknown")
    logger.info(f"Running single benchmark pipeline for QID: {qid}")

    # --- Create Agent ---
    try:
        # Apply defaults for single run agent creation
        default_species = "Neutral" # Default changed to Neutral
        default_model = "Agentic" # Default changed to Agentic
        default_reasoning_level = "low"
        default_data_dir = "data"
        s_species = getattr(args, 'species', default_species)
        s_model = getattr(args, 'model', default_model)
        s_level = getattr(args, 'reasoning_level', default_reasoning_level)
        s_data_dir = getattr(args, 'data_dir', default_data_dir)
        s_species = s_species if s_species is not None else default_species
        s_model = s_model if s_model is not None else default_model
        s_level = s_level if s_level is not None else default_reasoning_level
        s_data_dir = s_data_dir if s_data_dir is not None else default_data_dir

        data_dir_path = Path(s_data_dir)
        answer_agent = EthicsAgent(s_species, s_model, reasoning_level=s_level, data_dir=str(data_dir_path))
        logger.info(f"Agent created for single benchmark QID {qid}: {s_species} - {s_model} - {s_level}")
    except Exception as e:
        logger.error(f"Error creating agent for single benchmark QID {qid}: {e}", exc_info=True)
        return None
    # --- End Agent Creation ---

    # --- Run Single Item ---
    single_result_data = await run_item(item_dict, answer_agent)
    if not single_result_data:
        logger.error(f"Benchmark run for QID {qid} returned no data.")
        return None
    # --- End Run Single Item ---

    results_list_for_file = [single_result_data]

    # --- Load Metadata Dependencies ---
    # Use the effective data dir path determined above
    metadata_deps = load_metadata_dependencies(data_dir_path)
    species_full_data = metadata_deps["species"]
    models_full_data = metadata_deps["models"]
    if "Error" in species_full_data or "Error" in models_full_data:
        logger.error("Failed to load essential metadata (species/models) for single benchmark run.")
        return None
    # --- End Metadata Loading ---

    # --- Generate Metadata ---
    # Use the effective args determined above for metadata
    metadata = generate_run_metadata(
        run_type="benchmark_single",
        species=s_species,
        model=s_model,
        reasoning_level=s_level,
        species_data=species_full_data,
        model_data=models_full_data
    )
    metadata["evaluation_criteria"] = { "positive": ["BENCHMARK_CORRECT"], "negative": ["BENCHMARK_INCORRECT", "BENCHMARK_ERROR"] }
    # --- End Metadata Generation ---

    output_data_to_save = {"metadata": metadata, "results": results_list_for_file}

    # --- Use Centralized Save Function ---
    # Use the effective results dir from args or default
    default_results_dir = "results"
    s_results_dir = getattr(args, 'results_dir', default_results_dir)
    s_results_dir = s_results_dir if s_results_dir is not None else default_results_dir
    results_dir_path = Path(s_results_dir)

    saved_file_path = save_results_with_standard_name(
        results_dir=results_dir_path,
        run_type=metadata.get("run_type", "benchmark_single"),
        species=s_species, # Use effective args
        model=s_model,     # Use effective args
        level=s_level,     # Use effective args
        data_to_save=output_data_to_save,
        item_id=qid,
        timestamp=metadata.get("run_timestamp")
    )

    if not saved_file_path:
        logger.error(f"Failed to save single benchmark result for QID: {qid}")

    return saved_file_path
# --- End New Function ---

# Removed the old run_benchmarks function (now combined into run_benchmarks_async)
# Removed the if __name__ == "__main__": block
