#!/usr/bin/env python3
import argparse
import json
import asyncio
import sys
import os
from datetime import datetime
from reasoning_agent import EthicsAgent
from config.config import logger

def parse_args():
    parser = argparse.ArgumentParser(
        description="Run planners, executors, and judges with the same agent to produce plans, execution outcomes, and evaluations"
    )
    parser.add_argument("--data-dir", default="data", help="Data directory")
    parser.add_argument("--scenarios-file", default="data/scenarios.json", help="Path to scenarios file")
    parser.add_argument("--results-dir", default="results", help="Directory to save the results")
    parser.add_argument("--species", default="Jiminies", help="Species name")
    parser.add_argument("--model", default="Deontological", help="Reasoning model")
    parser.add_argument("--reasoning-level", default="low", help="Reasoning level (low, medium, high)")
    return parser.parse_args()

def load_scenarios(path):
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        return [{"id": key, "prompt": prompt} for key, prompt in data.items()]
    else:
        return data["scenarios"]

async def run_task(role, item, species, model, reasoning_level, data_dir):
    task_id = item.get("id", "unknown")
    prompt_text = item.get("prompt", "")
    prompt = f"{role} {prompt_text}"
    logger.info(f"Running task '{task_id}' with role: {role}")
    agent = EthicsAgent(species, model, reasoning_level=reasoning_level, data_dir=data_dir)
    response = await agent.run_async({"prompt": prompt}, task_id)
    return response["prompt_id"], response["result"]

async def run_role_tasks(role, items, species, model, reasoning_level, data_dir):
    tasks = [run_task(role, item, species, model, reasoning_level, data_dir) for item in items]
    responses = await asyncio.gather(*tasks)
    return {task_id: result for task_id, result in responses}

async def main():
    args = parse_args()
    logger.info(f"Running scenarios with agent: {args.species} - {args.model} - {args.reasoning_level}")
    scenarios = load_scenarios(args.scenarios_file)
    if not scenarios:
        logger.error("No scenarios found.")
        return

    # Define roles for the three stages.
    planner_role = "Create an executable, concise, 3 step plan for this situation:"
    executor_role = "Execute the following plan rapidly and effectively:"
    judge_role = "Judge the following plan and evaluate its ethical implications:"

    print("Running planner tasks")
    planner_results = await run_role_tasks(planner_role, scenarios, args.species, args.model, args.reasoning_level, args.data_dir)
    print("Planner Results:")
    print(json.dumps(planner_results, indent=2))

    print("Running executor tasks")
    # Executor tasks use the planner results: each item is a dict with id and the plan as prompt.
    executor_items = [{"id": sid, "prompt": plan} for sid, plan in planner_results.items()]
    executor_results = await run_role_tasks(executor_role, executor_items, args.species, args.model, args.reasoning_level, args.data_dir)
    print("Executor Results:")
    print(json.dumps(executor_results, indent=2))

    print("Running judge tasks")
    # Judge tasks change agent parameters.
    judge_items = [{"id": sid, "prompt": plan} for sid, plan in executor_results.items()]
    judge_results = await run_role_tasks(judge_role, judge_items, "Judges", "Agentic", args.reasoning_level, args.data_dir)
    print("Judge Results:")
    print(json.dumps(judge_results, indent=2))
    sys.stdout.flush()

    # Save results to file
    os.makedirs(args.results_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = os.path.join(
        args.results_dir,
        f"scenarios_{args.species.lower()}_{args.model.lower()}_{args.reasoning_level.lower()}_{timestamp}.json"
    )
    # Combine all results in a single dictionary.
    combined_results = {
        "planner": planner_results,
        "executor": executor_results,
        "judge": judge_results
    }
    with open(output_filename, "w") as f:
        json.dump(combined_results, f, indent=2)
    logger.info(f"Scenario results saved to {output_filename}")

if __name__ == "__main__":
    asyncio.run(main())
