#!/usr/bin/env python3
import argparse
import json
import os
import asyncio
from datetime import datetime
from pathlib import Path  # Added Path
from reasoning_agent import EthicsAgent
from config.config import logger, llm_config  # Added llm_config import
# Assuming dashboard_utils is available in the path
try:
    from dashboard.dashboard_utils import load_json as load_json_util # Renamed to avoid conflict with json module
except ImportError:
    logger.warning("Could not import dashboard_utils. Using basic json loader.")
    # Basic fallback loader if dashboard_utils is not importable in this context
    def load_json_util(path, default=None):
        if default is None: default = {}
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"File not found: {path}")
            return {"Error": f"File not found: {path}"}
        except json.JSONDecodeError:
            logger.error(f"JSON decode error in file: {path}")
            return {"Error": f"JSON decode error in file: {path}"}
        except Exception as e:
            logger.error(f"Error loading file {path}: {e}")
            return {"Error": f"Error loading file {path}: {e}"}

# Define paths relative to the script location or assume execution from project root
# Use Path(__file__).parent if running as script, otherwise assume relative to project root
try:
    _script_dir = Path(__file__).parent
except NameError: # __file__ not defined, likely interactive use or different execution context
    _script_dir = Path.cwd() # Fallback to current working directory

# Note: Path logic relies on args.data_dir now, these are less relevant
# DATA_DIR = _script_dir / "data"
# SPECIES_FILE = DATA_DIR / "species.json"
# GOLDEN_PATTERNS_FILE = DATA_DIR / "golden_patterns.json"


def parse_args():
    parser = argparse.ArgumentParser(description="Run EthicsEngine benchmarks")
    # Default data_dir to "data" assuming it's relative to CWD or project root
    parser.add_argument("--data-dir", default="data", help="Path to the data directory")
    parser.add_argument("--results-dir", default="results")
    # Default bench_file assuming data_dir is relative to CWD or project root
    parser.add_argument("--bench-file", default=os.path.join("data", "simple_bench_public.json"),
                        help="Path to the benchmark file")
    parser.add_argument("--species", default="Jiminies", help="Species name")
    parser.add_argument("--model", default="Deontological", help="Reasoning model")
    parser.add_argument("--reasoning-level", default="low", help="Reasoning level (low, medium, high)")
    return parser.parse_args()

def load_benchmarks(file_path):
    """Loads the benchmark data, returning the list under 'eval_data'."""
    try:
        # Use Path object for consistency
        file_path_obj = Path(file_path)
        if not file_path_obj.is_file(): # Check if it's actually a file
            logger.error(f"Benchmark file path is not a file or does not exist: {file_path_obj}")
            return []
        with open(file_path_obj) as f:
            data = json.load(f)
            # Ensure 'eval_data' exists and is a list
            eval_data = data.get("eval_data")
            if isinstance(eval_data, list):
                return eval_data
            else:
                logger.error(f"Key 'eval_data' not found or not a list in {file_path_obj}")
                return [] # Return empty list on error
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from benchmark file: {file_path_obj}")
        return []
    except Exception as e:
        logger.error(f"Error loading benchmarks from {file_path_obj}: {e}")
        return []


async def run_item(item, answer_agent):
    """Runs a single benchmark item and evaluates using direct comparison."""
    question = item.get("prompt", "")
    qid = item.get("question_id", "unknown")
    expected = item.get("answer", "") # Get expected answer as string

    # Get answer from the answer agent
    # Make the prompt very specific to get just the letter
    answer_payload = {
        "prompt": (
            f"Carefully analyze the following question and choose the best answer from the options provided. "
            f"Respond ONLY with the single capital letter corresponding to your final choice (e.g., 'A', 'B', 'C'). Do not include any explanation, punctuation, or other text.\\n\\n"
            f"Question:\\n{question}"
        )
    }
    logger.info(f"Running benchmark item with QID: {qid} for agent {answer_agent.species['name']}/{answer_agent.golden_pattern}")

    try:
        answer_data = await answer_agent.run_async(answer_payload, qid)
        raw_response = answer_data.get("result", "")
    except Exception as e:
        logger.error(f"Error running agent for QID {qid}: {e}")
        raw_response = f"Error: Agent execution failed ({e})"


    # --- Direct String Comparison Logic ---
    logger.info(f"QID: {qid} - Raw Response: '{raw_response}' | Expected: '{expected}'")
    # Clean up both response and expected answer for robust comparison
    response_cleaned = raw_response.strip().upper()
    expected_cleaned = str(expected).strip().upper()

    # Simple comparison (adjust if more complex logic needed, e.g., handling "A." vs "A")
    # Check if response is an error before comparing
    is_error = raw_response.startswith("Error:")
    if is_error:
        is_correct = False
        evaluation_result = "Error"
    else:
        is_correct = (response_cleaned == expected_cleaned) and (len(response_cleaned) == 1) # Add length check for robustness
        evaluation_result = "Correct" if is_correct else "Incorrect"

    logger.info(f"QID: {qid} - Cleaned Response: '{response_cleaned}' | Cleaned Expected: '{expected_cleaned}' | Evaluation: {evaluation_result}")
    # --- End Direct Comparison Logic ---

    # --- Judge Agent Call REMOVED (Kept removed as per previous file state) ---

    return {
        "question_id": qid,
        "question": question,
        "expected_answer": expected, # Keep original expected answer
        "response": raw_response, # Keep original raw response
        "evaluation": evaluation_result # Use result from direct comparison or Error
    }

async def run_benchmarks_async(benchmarks, answer_agent):
    """Runs multiple benchmark items concurrently."""
    if not benchmarks:
        logger.warning("No benchmark items to run.")
        return []
    # Launch all benchmark tasks concurrently
    logger.info(f"Running {len(benchmarks)} benchmarks asynchronously...")
    tasks = [run_item(item, answer_agent) for item in benchmarks]
    results = await asyncio.gather(*tasks)
    logger.info("Benchmark async run completed.")
    return results

def run_benchmarks():
    """Main function to load data, run benchmarks, and save results."""
    print("Running benchmarks...") # Keep print for CLI execution start
    args = parse_args()

    # Define data paths using args.data_dir
    data_dir_path = Path(args.data_dir)
    species_file_path = data_dir_path / "species.json"
    models_file_path = data_dir_path / "golden_patterns.json"

    # Load external data for metadata
    species_full_data = load_json_util(species_file_path, {})
    models_full_data = load_json_util(models_file_path, {})

    # Use the robust load_benchmarks function defined above
    # Ensure bench_file path is correctly resolved relative to CWD or absolute
    bench_file_path_obj = Path(args.bench_file)
    benchmarks = load_benchmarks(bench_file_path_obj)
    if not benchmarks:
        print(f"Error: No benchmark data loaded from {bench_file_path_obj}. Exiting.")
        logger.error(f"No benchmark data loaded from {bench_file_path_obj}. Exiting benchmark run.")
        return # Exit if no data

    # Create the agent that will answer the questions
    try:
        # Pass data_dir argument explicitly
        answer_agent = EthicsAgent(args.species, args.model, reasoning_level=args.reasoning_level, data_dir=str(data_dir_path))
        logger.info(f"Running benchmarks with agent: {args.species} - {args.model} - {args.reasoning_level}")
    except ValueError as e:
        print(f"Error creating agent: {e}")
        logger.error(f"Error creating agent: {e}")
        return
    except FileNotFoundError as e:
        print(f"Error creating agent, data file not found: {e}")
        logger.error(f"Error creating agent, data file not found: {e}")
        return


    # Run the benchmarks asynchronously
    results_list = asyncio.run(run_benchmarks_async(benchmarks, answer_agent))

    # Log and print results summary (optional, can be verbose)
    correct_count = 0
    error_count = 0
    for record in results_list:
        # Safely access evaluation key
        evaluation = record.get('evaluation', 'Unknown')
        logger.debug(f"QID: {record.get('question_id', 'N/A')} | Expected: {record.get('expected_answer', 'N/A')} | Response: {record.get('response', 'N/A')} | Eval: {evaluation}")
        # print(record) # Optionally print full record
        if evaluation == "Correct":
            correct_count += 1
        elif evaluation == "Error":
            error_count += 1

    total_questions = len(results_list)
    accuracy = (correct_count / total_questions * 100) if total_questions > 0 else 0
    error_rate = (error_count / total_questions * 100) if total_questions > 0 else 0
    summary_msg = f"Benchmark Summary: {correct_count}/{total_questions} Correct ({accuracy:.2f}%). Errors: {error_count} ({error_rate:.2f}%)."
    print(summary_msg)
    logger.info(summary_msg)

    # --- Prepare Metadata ---
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Safely get species traits and model description
    species_traits = species_full_data.get(args.species, f"Unknown species '{args.species}'")
    if isinstance(species_full_data, dict) and "Error" in species_full_data:
         species_traits = f"Error loading species data: {species_full_data['Error']}"

    model_description = models_full_data.get(args.model, f"Unknown model '{args.model}'")
    if isinstance(models_full_data, dict) and "Error" in models_full_data:
         model_description = f"Error loading model data: {models_full_data['Error']}"


    # Prepare LLM config for metadata (excluding API key)
    safe_llm_config = []
    try:
        if hasattr(llm_config, 'config_list') and isinstance(llm_config.config_list, list):
            for config_item in llm_config.config_list:
                 if isinstance(config_item, dict):
                     safe_item = config_item.copy()
                     safe_item.pop('api_key', None) # Remove API key
                     # Optionally remove other potentially sensitive or verbose keys
                     safe_item.pop('base_url', None)
                     safe_item.pop('api_type', None)
                     safe_item.pop('api_version', None)
                     safe_llm_config.append(safe_item)
                 else:
                     logger.warning(f"Item in llm_config.config_list is not a dict: {config_item}")
        elif isinstance(llm_config, dict): # Handle case where llm_config might be a dict
             safe_item = llm_config.copy()
             safe_item.pop('api_key', None)
             safe_llm_config.append(safe_item)
        else:
             logger.warning("llm_config structure not recognized for metadata.")
    except Exception as e:
        logger.error(f"Error processing llm_config for metadata: {e}")


    metadata = {
        "run_timestamp": run_timestamp,
        "run_type": "benchmark",
        "species_name": args.species,
        "species_traits": species_traits,
        "reasoning_model": args.model,
        "model_description": model_description,
        "reasoning_level": args.reasoning_level,
        "llm_config": safe_llm_config,
        "tags": [], # Placeholder
        "evaluation_criteria": {} # Placeholder
    }

    # --- Combine Metadata and Results ---
    output_data = {
        "metadata": metadata,
        "results": results_list
    }

    # Save results to file
    try:
        results_dir_path = Path(args.results_dir)
        results_dir_path.mkdir(parents=True, exist_ok=True) # Use Path object's mkdir
        # Use timestamp from metadata for consistency
        output_file = results_dir_path / f"bench_{args.species.lower()}_{args.model.lower()}_{args.reasoning_level.lower()}_{run_timestamp}.json"
        with open(output_file, "w") as f:
            json.dump(output_data, f, indent=2) # Save the combined output_data
        logger.info(f"Benchmark results saved to {output_file}")
        print(f"Benchmark results saved to {output_file}") # Also print for CLI user
    except Exception as e:
        logger.error(f"Failed to save benchmark results: {e}")
        print(f"Error: Failed to save benchmark results: {e}")


if __name__ == "__main__":
    # Setup logger for CLI execution if needed (config should handle file logging)
    # import logging
    # logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    run_benchmarks()