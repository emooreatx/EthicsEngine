# EthicsEngine/run_benchmarks.py
#!/usr/bin/env python3
import argparse
import json
import os
import asyncio
from datetime import datetime
from pathlib import Path

# --- Updated Imports ---
# Import EthicsAgent from reasoning_agent
from reasoning_agent import EthicsAgent
# Import logger, llm_config, and AG2_REASONING_SPECS from config
from config.config import logger, llm_config, AG2_REASONING_SPECS
# --- End Updated Imports ---

# Assuming dashboard_utils is available in the path
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
    # (load_benchmarks function remains the same)
    try:
        file_path_obj = Path(file_path)
        if not file_path_obj.is_file(): logger.error(f"Benchmark file path is not a file or does not exist: {file_path_obj}"); return []
        with open(file_path_obj) as f: data = json.load(f)
        # Expects benchmark data under "eval_data" key as a list
        eval_data = data.get("eval_data")
        if isinstance(eval_data, list): return eval_data
        else: logger.error(f"Key 'eval_data' not found or not a list in {file_path_obj}"); return []
    except json.JSONDecodeError: logger.error(f"Error decoding JSON from benchmark file: {file_path_obj}"); return []
    except Exception as e: logger.error(f"Error loading benchmarks from {file_path_obj}: {e}"); return []

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
    results = await asyncio.gather(*tasks)
    logger.info("Benchmark async run completed.")
    return results

def run_benchmarks():
    """Main function to load data, run benchmarks, and save results."""
    print("Running benchmarks...")
    args = parse_args()

    data_dir_path = Path(args.data_dir)
    species_file_path = data_dir_path / "species.json"
    models_file_path = data_dir_path / "golden_patterns.json"

    species_full_data = load_json_util(species_file_path, {})
    models_full_data = load_json_util(models_file_path, {})

    # Check species data format and extract traits
    if not isinstance(species_full_data, dict):
        logger.error(f"Invalid format for {species_file_path}. Expected dict."); species_traits = ["Error: Invalid species.json format"]; species_full_data = {}
    else:
        species_traits_raw = species_full_data.get(args.species, f"Unknown species '{args.species}'")
        if "Error" in species_full_data: species_traits = [f"Error loading species data: {species_full_data['Error']}"]
        # Ensure species_traits is always a list
        species_traits = species_traits_raw.split(', ') if isinstance(species_traits_raw, str) else species_traits_raw
        if not isinstance(species_traits, list): species_traits = [str(species_traits)] # Force to list if not already

    model_description = models_full_data.get(args.model, f"Unknown model '{args.model}'")
    if isinstance(models_full_data, dict) and "Error" in models_full_data: model_description = f"Error loading model data: {models_full_data['Error']}"

    bench_file_path_obj = Path(args.bench_file)
    benchmarks = load_benchmarks(bench_file_path_obj)
    if not benchmarks:
        print(f"Error: No benchmark data loaded from {bench_file_path_obj}. Exiting.")
        logger.error(f"No benchmark data loaded from {bench_file_path_obj}. Exiting benchmark run.")
        return

    try:
        answer_agent = EthicsAgent(args.species, args.model, reasoning_level=args.reasoning_level, data_dir=str(data_dir_path))
        logger.info(f"Running benchmarks with agent: {args.species} - {args.model} - {args.reasoning_level}")
    except Exception as e: print(f"Error creating agent: {e}"); logger.error(f"Error creating agent: {e}", exc_info=True); return

    # Run the benchmarks asynchronously
    results_list = asyncio.run(run_benchmarks_async(benchmarks, answer_agent))

    # Calculate summary statistics
    correct_count = sum(1 for r in results_list if r.get('output', {}).get('judgement') == "Correct")
    error_count = sum(1 for r in results_list if r.get('output', {}).get('judgement') == "Error")
    total_questions = len(results_list)
    accuracy = (correct_count / total_questions * 100) if total_questions > 0 else 0
    error_rate = (error_count / total_questions * 100) if total_questions > 0 else 0
    summary_msg = f"Benchmark Summary: {correct_count}/{total_questions} Correct ({accuracy:.2f}%). Errors: {error_count} ({error_rate:.2f}%)."
    print(summary_msg)
    logger.info(summary_msg)

    # Prepare metadata for the results file
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # AG2_REASONING_SPECS is now imported from config
    reason_config_spec = AG2_REASONING_SPECS.get(args.reasoning_level, {})
    # Reconstruct agent config used
    agent_reason_config = { "method": "beam_search", "max_depth": reason_config_spec.get("max_depth", 2), "beam_size": 3, "answer_approach": "pool" }
    logger.debug(f"Reconstructed agent_reason_config for metadata: {agent_reason_config}")

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

    # Final Metadata Dictionary (aligned with new format)
    metadata = {
        "run_timestamp": run_timestamp,
        "run_type": "benchmark", # Clearly identify as benchmark run
        "species_name": args.species,
        "species_traits": species_traits, # Already ensured it's a list
        "reasoning_model": args.model,
        "model_description": model_description,
        "reasoning_level": args.reasoning_level,
        "agent_reasoning_config": agent_reason_config,
        "llm_config": safe_llm_config,
        "tags": [], # Benchmark specific tags could go here if needed
        "evaluation_criteria": { # Using consistent structure
             "positive": ["BENCHMARK_CORRECT"],
             "negative": ["BENCHMARK_INCORRECT", "BENCHMARK_ERROR"]
        }
    }
    output_data = {"metadata": metadata, "results": results_list}

    # Save results to JSON file
    try:
        results_dir_path = Path(args.results_dir); results_dir_path.mkdir(parents=True, exist_ok=True)
        output_file = results_dir_path / f"bench_{args.species.lower()}_{args.model.lower()}_{args.reasoning_level.lower()}_{run_timestamp}.json"
        with open(output_file, "w") as f: json.dump(output_data, f, indent=2)
        logger.info(f"Benchmark results saved to {output_file}")
        print(f"Benchmark results saved to {output_file}")
    except Exception as e:
        logger.error(f"Failed to save benchmark results: {e}"); print(f"Error saving results: {e}")

if __name__ == "__main__":
    run_benchmarks()

