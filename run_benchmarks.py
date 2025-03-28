#!/usr/bin/env python3
import argparse
import json
import os
import asyncio
from datetime import datetime
from reasoning_agent import EthicsAgent
from config.config import logger

def parse_args():
    parser = argparse.ArgumentParser(description="Run EthicsEngine benchmarks")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--bench-file", default="data/simple_bench_public.json",
                        help="Path to the benchmark file")
    parser.add_argument("--species", default="Jiminies", help="Species name")
    parser.add_argument("--model", default="Deontological", help="Reasoning model")
    parser.add_argument("--reasoning-level", default="medium", help="Reasoning level (low, medium, high)")
    return parser.parse_args()

def load_benchmarks(file_path):
    """Loads the benchmark data, returning the list under 'eval_data'."""
    try:
        with open(file_path) as f:
            data = json.load(f)
            # Ensure 'eval_data' exists and is a list
            eval_data = data.get("eval_data")
            if isinstance(eval_data, list):
                return eval_data
            else:
                logger.error(f"Key 'eval_data' not found or not a list in {file_path}")
                return [] # Return empty list on error
    except FileNotFoundError:
        logger.error(f"Benchmark file not found: {file_path}")
        return []
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from benchmark file: {file_path}")
        return []
    except Exception as e:
        logger.error(f"Error loading benchmarks from {file_path}: {e}")
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
            f"Respond ONLY with the single capital letter corresponding to your final choice (e.g., 'A', 'B', 'C'). Do not include any explanation, punctuation, or other text.\n\n"
            f"Question:\n{question}"
        )
    }
    logger.info(f"Running benchmark item with QID: {qid} for agent {answer_agent.species['name']}/{answer_agent.golden_pattern}")

    answer_data = await answer_agent.run_async(answer_payload, qid)
    raw_response = answer_data.get("result", "")

    # --- Direct String Comparison Logic ---
    logger.info(f"QID: {qid} - Raw Response: '{raw_response}' | Expected: '{expected}'")
    # Clean up both response and expected answer for robust comparison
    response_cleaned = raw_response.strip().upper()
    expected_cleaned = str(expected).strip().upper()

    # Simple comparison (adjust if more complex logic needed, e.g., handling "A." vs "A")
    # For single letters, direct comparison after cleaning should work.
    is_correct = (response_cleaned == expected_cleaned) and (len(response_cleaned) == 1) # Add length check for robustness

    evaluation_result = "Correct" if is_correct else "Incorrect"
    logger.info(f"QID: {qid} - Cleaned Response: '{response_cleaned}' | Cleaned Expected: '{expected_cleaned}' | Evaluation: {evaluation_result}")
    # --- End Direct Comparison Logic ---

    # --- Judge Agent Call REMOVED ---
    # judge_agent = EthicsAgent("Judges", "Agentic", reasoning_level=answer_agent.reasoning_level, data_dir=answer_agent.data_dir)
    # judge_payload = {
    #     "prompt": (
    #         f"Evaluate the following answer. \nQuestion: {question}\n"
    #         f"Expected Answer: {expected}\nResponse: {answer['result']}\n"
    #         f"Provide your verdict as a single word (e.g., Correct or Incorrect)."
    #     )
    # }
    # logger.info(f"Running evaluation for QID: {qid}")
    # evaluation = await judge_agent.run_async(judge_payload, qid)
    # evaluation_result = evaluation["result"] # Get result from judge agent
    # --- End Judge Agent Call REMOVED ---

    return {
        "question_id": qid,
        "question": question,
        "expected_answer": expected, # Keep original expected answer
        "response": raw_response, # Keep original raw response
        "evaluation": evaluation_result # Use result from direct comparison
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

    # Use the robust load_benchmarks function defined above
    benchmarks = load_benchmarks(args.bench_file)
    if not benchmarks:
        print(f"Error: No benchmark data loaded from {args.bench_file}. Exiting.")
        logger.error(f"No benchmark data loaded from {args.bench_file}. Exiting benchmark run.")
        return # Exit if no data

    # Create the agent that will answer the questions
    answer_agent = EthicsAgent(args.species, args.model, reasoning_level=args.reasoning_level, data_dir=args.data_dir)
    logger.info(f"Running benchmarks with agent: {args.species} - {args.model} - {args.reasoning_level}")

    # Run the benchmarks asynchronously
    results = asyncio.run(run_benchmarks_async(benchmarks, answer_agent))

    # Log and print results (optional, can be verbose)
    correct_count = 0
    for record in results:
        logger.debug(f"QID: {record['question_id']} | Expected: {record['expected_answer']} | Response: {record['response']} | Eval: {record['evaluation']}")
        # print(record) # Optionally print full record
        if record['evaluation'] == "Correct":
            correct_count += 1

    total_questions = len(results)
    accuracy = (correct_count / total_questions * 100) if total_questions > 0 else 0
    summary_msg = f"Benchmark Summary: {correct_count}/{total_questions} Correct ({accuracy:.2f}%)"
    print(summary_msg)
    logger.info(summary_msg)

    # Save results to file
    try:
        os.makedirs(args.results_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(args.results_dir,
                                   f"bench_{args.species.lower()}_{args.model.lower()}_{args.reasoning_level.lower()}_{timestamp}.json")
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"Benchmark results saved to {output_file}")
        print(f"Benchmark results saved to {output_file}") # Also print for CLI user
    except Exception as e:
        logger.error(f"Failed to save benchmark results: {e}")
        print(f"Error: Failed to save benchmark results: {e}")


if __name__ == "__main__":
    # Setup logger for CLI execution if needed (config should handle file logging)
    # logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    run_benchmarks()