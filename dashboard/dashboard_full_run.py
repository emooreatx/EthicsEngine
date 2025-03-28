# EthicsEngine/dashboard/dashboard_full_run.py
import asyncio
import os
import json
from datetime import datetime
from pathlib import Path
import argparse # Add argparse for potential standalone execution

# --- Import necessary components from the project ---
# Encapsulate imports in try-except to guide user if run standalone in wrong context
try:
    # Use the load_benchmarks from run_benchmarks which already extracts 'eval_data'
    from run_benchmarks import load_benchmarks, run_benchmarks_async
    from run_scenario_pipelines import load_scenarios, run_pipeline_for_scenario
    from reasoning_agent import EthicsAgent
    from dashboard.dashboard_utils import save_json, load_json # Use dashboard's utils
    from config.config import logger # Use logger from config
    # Define project base path relative to this script if needed, or assume execution from root
    _project_root = Path(__file__).parent.parent # Assumes this file is in dashboard/
    DATA_DIR = _project_root / "data"
    RESULTS_DIR = _project_root / "results"
    BENCHMARKS_FILE = DATA_DIR / "simple_bench_public.json"
    SCENARIOS_FILE = DATA_DIR / "scenarios.json"

except ImportError as e:
    print(f"ImportError: {e}. Make sure this script is run within the EthicsEngine project structure, "
          "or that the necessary modules (run_benchmarks, run_scenario_pipelines, etc.) are in the Python path.")
    # Define dummy functions/classes if imports fail, to prevent immediate crash
    logger = None
    def load_benchmarks(f): return [] # Return empty list as fallback now
    def run_benchmarks_async(b, a): return []
    def load_scenarios(f): return []
    def run_pipeline_for_scenario(s, a): return {}
    class EthicsAgent: pass
    def save_json(f, d): pass
    DATA_DIR = Path("data")
    RESULTS_DIR = Path("results")
    BENCHMARKS_FILE = DATA_DIR / "simple_bench_public.json"
    SCENARIOS_FILE = DATA_DIR / "scenarios.json"
    # Simple logger fallback
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("dashboard_full_run_fallback")


# --- Helper Functions (Internal to this script) ---

async def _run_all_benchmarks_async(args):
    """Internal async function to run all benchmarks."""
    if not logger: print("Logger not available.")
    else: logger.info(f"Starting full benchmark run with: {args.species}, {args.model}, {args.reasoning_level}")

    # --- CORRECTED DATA HANDLING ---
    # load_benchmarks already returns the list from "eval_data"
    target_benchmarks = load_benchmarks(args.bench_file)

    # Check if the loaded list is empty or invalid
    if not target_benchmarks or not isinstance(target_benchmarks, list):
        msg = "No valid benchmark data found or loaded."
        if logger: logger.error(msg)
        else: print(f"Error: {msg}")
        raise ValueError(msg) # Raise error with informative message
    # --- END CORRECTION ---

    answer_agent = EthicsAgent(args.species, args.model, reasoning_level=args.reasoning_level, data_dir=args.data_dir)

    # Run the async benchmark execution
    results = await run_benchmarks_async(target_benchmarks, answer_agent)

    # Save the results
    os.makedirs(args.results_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = Path(args.results_dir) / f"bench_{args.species.lower()}_{args.model.lower()}_{args.reasoning_level.lower()}_{timestamp}.json"
    save_json(output_file, results) # Use save_json from utils

    if logger: logger.info(f"Full benchmark results saved to {output_file}")
    else: print(f"Full benchmark results saved to {output_file}")

    return str(output_file) # Return the path as a string

async def _run_all_scenarios_async(args):
    """Internal async function to run all scenario pipelines."""
    if not logger: print("Logger not available.")
    else: logger.info(f"Starting full scenario pipelines run with: {args.species}, {args.model}, {args.reasoning_level}")

    scenarios = load_scenarios(args.scenarios_file)
    if not scenarios:
        if logger: logger.error("No scenarios found.")
        else: print("Error: No scenarios found.")
        raise ValueError("No scenarios found.")

    # Run pipelines concurrently
    pipeline_tasks = [run_pipeline_for_scenario(scenario, args) for scenario in scenarios]
    results = await asyncio.gather(*pipeline_tasks)

    # Save the results
    os.makedirs(args.results_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = Path(args.results_dir) / f"scenarios_pipeline_{args.species.lower()}_{args.model.lower()}_{args.reasoning_level.lower()}_{timestamp}.json"
    save_json(output_filename, results) # Use save_json from utils

    if logger: logger.info(f"Full scenario pipeline results saved to {output_filename}")
    else: print(f"Full scenario pipeline results saved to {output_filename}")

    return str(output_filename) # Return the path as a string

# --- Main Function to be Called from Dashboard ---

def run_full_set(species: str, model: str, reasoning_level: str, data_dir=None, results_dir=None, bench_file=None, scenarios_file=None):
    """
    Runs the full set of benchmarks and scenario pipelines sequentially.

    Args:
        species (str): The species name.
        model (str): The reasoning model name.
        reasoning_level (str): The reasoning level ('low', 'medium', 'high').
        data_dir (str | Path, optional): Path to the data directory. Defaults to DATA_DIR.
        results_dir (str | Path, optional): Path to the results directory. Defaults to RESULTS_DIR.
        bench_file (str | Path, optional): Path to the benchmark file. Defaults to BENCHMARKS_FILE.
        scenarios_file (str | Path, optional): Path to the scenarios file. Defaults to SCENARIOS_FILE.

    Returns:
        tuple[str | None, str | None]: Paths to the saved benchmark and scenario results files.
                                       Returns (None, None) if a critical error occurs.
    Raises:
        ValueError: If required arguments are missing or data loading fails.
        Exception: If unexpected errors occur during execution.
    """
    # Use provided paths or defaults
    data_dir_path = Path(data_dir) if data_dir else DATA_DIR
    results_dir_path = Path(results_dir) if results_dir else RESULTS_DIR
    bench_file_path = Path(bench_file) if bench_file else BENCHMARKS_FILE
    scenarios_file_path = Path(scenarios_file) if scenarios_file else SCENARIOS_FILE

    # --- Create args object ---
    # Simple namespace class for compatibility with backend functions expecting argparse obj
    class ArgsNamespace:
         pass
    args = ArgsNamespace()
    args.species = species
    args.model = model
    args.reasoning_level = reasoning_level
    args.data_dir = str(data_dir_path)
    args.results_dir = str(results_dir_path)
    args.bench_file = str(bench_file_path)
    args.scenarios_file = str(scenarios_file_path)

    if not all([species, model, reasoning_level]):
        msg = "Species, Model, and Reasoning Level are required."
        if logger: logger.error(msg)
        else: print(f"Error: {msg}")
        raise ValueError(msg)

    benchmark_output_file = None
    scenario_output_file = None
    try:
        # Run benchmarks - Let exceptions propagate up
        benchmark_output_file = asyncio.run(_run_all_benchmarks_async(args))

        # Run scenarios - Let exceptions propagate up
        scenario_output_file = asyncio.run(_run_all_scenarios_async(args))

        return benchmark_output_file, scenario_output_file

    except Exception as e:
        # Log the exception details, but re-raise to be handled by the caller (dashboard)
        error_msg = f"Error during full run: {e}"
        if logger: logger.exception(error_msg) # Log exception details including traceback
        else: print(error_msg)
        raise # Re-raise the exception to be caught in the dashboard action


# --- Standalone Execution Block ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run full set of EthicsEngine benchmarks and scenario pipelines.")
    parser.add_argument("--species", default="Jiminies", help="Species name")
    parser.add_argument("--model", default="Utilitarian", help="Reasoning model")
    parser.add_argument("--reasoning-level", default="low", choices=["low", "medium", "high"], help="Reasoning level")
    parser.add_argument("--data-dir", default=str(DATA_DIR), help="Data directory")
    parser.add_argument("--results-dir", default=str(RESULTS_DIR), help="Results directory")
    parser.add_argument("--bench-file", default=str(BENCHMARKS_FILE), help="Benchmark JSON file path")
    parser.add_argument("--scenarios-file", default=str(SCENARIOS_FILE), help="Scenarios JSON file path")

    cli_args = parser.parse_args()

    print(f"Running full set via command line with:")
    print(f"  Species: {cli_args.species}")
    print(f"  Model: {cli_args.model}")
    print(f"  Level: {cli_args.reasoning_level}")
    print(f"  Data Dir: {cli_args.data_dir}")
    print(f"  Results Dir: {cli_args.results_dir}")

    try:
        bench_out, scenario_out = run_full_set(
            species=cli_args.species,
            model=cli_args.model,
            reasoning_level=cli_args.reasoning_level,
            data_dir=cli_args.data_dir,
            results_dir=cli_args.results_dir,
            bench_file=cli_args.bench_file,
            scenarios_file=cli_args.scenarios_file
        )
        # run_full_set now raises exceptions on failure
        print("\nFull run completed successfully.")
        print(f"Benchmark results: {bench_out}")
        print(f"Scenario results: {scenario_out}")

    except Exception as e:
        print(f"\nAn error occurred during the full run: {e}")
        # Optionally exit with non-zero status
        # exit(1)