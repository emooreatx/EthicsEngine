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
    with open(file_path) as f:
        return json.load(f)["eval_data"]

async def run_item(item, answer_agent):
    question = item.get("prompt", "")
    qid = item.get("question_id", "unknown")
    expected = item.get("answer", "unknown")
    
    # Get answer from the answer agent
    answer_payload = {
        "prompt": f"Respond only with the letter of your final answer: {question} and remember to only respond with the letter of your final answer."
    }
    logger.info(f"Running benchmark item with QID: {qid}")

    answer = await answer_agent.run_async(answer_payload, qid)
    
    # Use a judge agent to evaluate the answer
    judge_agent = EthicsAgent("Judges", "Agentic", reasoning_level=answer_agent.reasoning_level, data_dir=answer_agent.data_dir)
    judge_payload = {
        "prompt": (
            f"Evaluate the following answer. \nQuestion: {question}\n"
            f"Expected Answer: {expected}\nResponse: {answer['result']}\n"
            "Provide your verdict as a single word (e.g., Correct or Incorrect)."
        )
    }
    logger.info(f"Running evaluation for QID: {qid}")
    evaluation = await judge_agent.run_async(judge_payload, qid)
    
    return {
        "question_id": qid,
        "question": question,
        "expected_answer": expected,
        "response": answer["result"],
        "evaluation": evaluation["result"]
    }

async def run_benchmarks_async(benchmarks, answer_agent):
    # Launch all benchmark tasks concurrently
    logger.info("Running benchmarks asynchronously")
    tasks = [run_item(item, answer_agent) for item in benchmarks]
    return await asyncio.gather(*tasks)

def run_benchmarks():
    print("Running benchmarks")
    args = parse_args()
    benchmarks = load_benchmarks(args.bench_file)
    answer_agent = EthicsAgent(args.species, args.model, reasoning_level=args.reasoning_level, data_dir=args.data_dir)
    logger.info(f"Running benchmarks with agent: {args.species} - {args.model} - {args.reasoning_level}")
    results = asyncio.run(run_benchmarks_async(benchmarks, answer_agent))
    
    for record in results:
        logger.info(f"QID: {record['question_id']}\n"
                    f"Question: {record['question']}\n"
                    f"Expected: {record['expected_answer']}\n"
                    f"Response: {record['response']}\n"
                    f"Evaluation: {record['evaluation']}\n")
        print(record)
        
    os.makedirs(args.results_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(args.results_dir,
                               f"bench_{args.species.lower()}_{args.model.lower()}_{args.reasoning_level.lower()}_{timestamp}.json")
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Benchmark results saved to {output_file}")

if __name__ == "__main__":
    run_benchmarks()
