# EthicsEngine/dashboard/dashboard_full_run.py
import asyncio
import os
import json
from datetime import datetime
from pathlib import Path
import argparse # Keep for standalone execution if needed

# --- Import necessary components from the project ---
try:
    # Use the load_benchmarks from run_benchmarks which already extracts 'eval_data'
    from run_benchmarks import load_benchmarks, run_benchmarks_async
    from run_scenario_pipelines import load_scenarios, run_pipeline_for_scenario
    from reasoning_agent import EthicsAgent
    # Import AG2_REASONING_SPECS from config now
    from config.config import logger, llm_config, AG2_REASONING_SPECS
    from dashboard.dashboard_utils import save_json, load_json, SPECIES_FILE, GOLDEN_PATTERNS_FILE # Use dashboard's utils and constants
    # Define project base path relative to this script if needed, or assume execution from root
    _project_root = Path(__file__).parent.parent # Assumes this file is in dashboard/
    # Define default paths relative to project root
    DEFAULT_DATA_DIR = _project_root / "data"
    DEFAULT_RESULTS_DIR = _project_root / "results"
    DEFAULT_BENCHMARKS_FILE = DEFAULT_DATA_DIR / "simple_bench_public.json"
    DEFAULT_SCENARIOS_FILE = DEFAULT_DATA_DIR / "scenarios.json"

except ImportError as e:
    print(f"ImportError: {e}. Make sure this script is run within the EthicsEngine project structure, "
          "or that the necessary modules (run_benchmarks, run_scenario_pipelines, etc.) are in the Python path.")
    # Define dummy functions/classes if imports fail, to prevent immediate crash
    logger = None
    def load_benchmarks(f): return []
    def run_benchmarks_async(b, a): return []
    def load_scenarios(f): return []
    def run_pipeline_for_scenario(s, a): return {}
    class EthicsAgent: pass
    def save_json(f, d): pass
    # Dummy specs if needed
    AG2_REASONING_SPECS = {"low": {}, "medium": {}, "high": {}}
    # Dummy paths
    DEFAULT_DATA_DIR = Path("data")
    DEFAULT_RESULTS_DIR = Path("results")
    DEFAULT_BENCHMARKS_FILE = DEFAULT_DATA_DIR / "simple_bench_public.json"
    DEFAULT_SCENARIOS_FILE = DEFAULT_DATA_DIR / "scenarios.json"
    SPECIES_FILE = DEFAULT_DATA_DIR / "species.json"
    GOLDEN_PATTERNS_FILE = DEFAULT_DATA_DIR / "golden_patterns.json"
    # Simple logger fallback
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("dashboard_full_run_fallback")


# --- Helper Functions (Internal to this script) ---

async def _run_all_benchmarks_async(args):
    """Internal async function to run all benchmarks and save with metadata."""
    if not logger: print("Logger not available.")
    else: logger.info(f"Starting full benchmark run with: {args.species}, {args.model}, {args.reasoning_level}")

    target_benchmarks = load_benchmarks(args.bench_file)
    if not target_benchmarks or not isinstance(target_benchmarks, list):
        msg = f"No valid benchmark data found or loaded from {args.bench_file}."
        if logger: logger.error(msg)
        else: print(f"Error: {msg}")
        raise ValueError(msg)

    try:
        answer_agent = EthicsAgent(args.species, args.model, reasoning_level=args.reasoning_level, data_dir=args.data_dir)
    except Exception as e:
         msg = f"Failed to create EthicsAgent: {e}"
         if logger: logger.error(msg, exc_info=True)
         else: print(f"Error: {msg}")
         raise RuntimeError(msg) from e

    # Run the async benchmark execution
    results_list = await run_benchmarks_async(target_benchmarks, answer_agent)

    # --- ADDED: Construct metadata and full output dictionary ---
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    reason_config_spec = AG2_REASONING_SPECS.get(args.reasoning_level, {})
    agent_reason_config = { "method": "beam_search", "max_depth": reason_config_spec.get("max_depth", 2), "beam_size": 3, "answer_approach": "pool" }

    # Load species/model descriptions for metadata
    species_full_data = load_json(SPECIES_FILE, {})
    models_full_data = load_json(GOLDEN_PATTERNS_FILE, {})
    species_traits_raw = species_full_data.get(args.species, f"Unknown species '{args.species}'")
    species_traits = species_traits_raw.split(', ') if isinstance(species_traits_raw, str) else species_traits_raw
    if not isinstance(species_traits, list): species_traits = [str(species_traits)]
    model_description = models_full_data.get(args.model, f"Unknown model '{args.model}'")

    # Process LLM Config for Metadata
    safe_llm_config = []
    try:
        config_list = getattr(llm_config, 'config_list', [])
        if config_list:
            for config_item in config_list:
                 model_name = config_item.get('model') if isinstance(config_item, dict) else getattr(config_item, 'model', None)
                 if model_name:
                     temp = reason_config_spec.get("temperature", "N/A")
                     safe_llm_config.append({"model": model_name, "temperature": temp})
    except Exception as e:
        if logger: logger.error(f"Error processing llm_config for benchmark metadata: {e}")

    metadata = {
        "run_timestamp": run_timestamp, "run_type": "benchmark", "species_name": args.species,
        "species_traits": species_traits, "reasoning_model": args.model, "model_description": model_description,
        "reasoning_level": args.reasoning_level, "agent_reasoning_config": agent_reason_config,
        "llm_config": safe_llm_config, "tags": [],
        "evaluation_criteria": { "positive": ["BENCHMARK_CORRECT"], "negative": ["BENCHMARK_INCORRECT", "BENCHMARK_ERROR"] }
    }
    output_data = {"metadata": metadata, "results": results_list}
    # --- END ADDED SECTION ---

    # Save the results (now saving the full output_data dictionary)
    os.makedirs(args.results_dir, exist_ok=True)
    output_file = Path(args.results_dir) / f"bench_{args.species.lower()}_{args.model.lower()}_{args.reasoning_level.lower()}_{run_timestamp}.json"
    # --- MODIFIED: Save output_data instead of just results_list ---
    save_json(output_file, output_data)
    # --- END MODIFIED ---

    if logger: logger.info(f"Full benchmark results saved to {output_file}")
    else: print(f"Full benchmark results saved to {output_file}")

    return str(output_file) # Return the path as a string

async def _run_all_scenarios_async(args):
    """Internal async function to run all scenario pipelines and save with metadata."""
    # This function already saves the correct {"metadata": ..., "results": ...} structure
    # via run_scenario_pipelines.py logic, so no changes needed here assuming that script is correct.
    if not logger: print("Logger not available.")
    else: logger.info(f"Starting full scenario pipelines run with: {args.species}, {args.model}, {args.reasoning_level}")

    scenarios = load_scenarios(args.scenarios_file)
    if not scenarios:
        msg = f"No valid scenarios found or loaded from {args.scenarios_file}."
        if logger: logger.error(msg)
        else: print(f"Error: {msg}")
        raise ValueError(msg)

    # Run pipelines concurrently
    pipeline_tasks = [run_pipeline_for_scenario(scenario, args) for scenario in scenarios]
    results_list = await asyncio.gather(*pipeline_tasks)

    # --- ADDED: Construct metadata and full output dictionary ---
    # (Copied logic similar to _run_all_benchmarks_async and run_scenario_pipelines.py main)
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    reason_config_spec = AG2_REASONING_SPECS.get(args.reasoning_level, {})
    agent_reason_config = { "method": "beam_search", "max_depth": reason_config_spec.get("max_depth", 2), "beam_size": 3, "answer_approach": "pool" }

    species_full_data = load_json(SPECIES_FILE, {})
    models_full_data = load_json(GOLDEN_PATTERNS_FILE, {})
    species_traits_raw = species_full_data.get(args.species, f"Unknown species '{args.species}'")
    species_traits = species_traits_raw.split(', ') if isinstance(species_traits_raw, str) else species_traits_raw
    if not isinstance(species_traits, list): species_traits = [str(species_traits)]
    model_description = models_full_data.get(args.model, f"Unknown model '{args.model}'")

    safe_llm_config = []
    try:
        config_list = getattr(llm_config, 'config_list', [])
        if config_list:
            for config_item in config_list:
                 model_name = config_item.get('model') if isinstance(config_item, dict) else getattr(config_item, 'model', None)
                 if model_name:
                     temp = reason_config_spec.get("temperature", "N/A")
                     safe_llm_config.append({"model": model_name, "temperature": temp})
    except Exception as e:
        if logger: logger.error(f"Error processing llm_config for scenario metadata: {e}")

    metadata = {
        "run_timestamp": run_timestamp, "run_type": "scenario_pipeline", "species_name": args.species,
        "species_traits": species_traits, "reasoning_model": args.model, "model_description": model_description,
        "reasoning_level": args.reasoning_level, "agent_reasoning_config": agent_reason_config,
        "llm_config": safe_llm_config, "tags": [], "evaluation_criteria": {}
    }
    output_data = {"metadata": metadata, "results": results_list}
    # --- END ADDED SECTION ---


    # Save the results
    os.makedirs(args.results_dir, exist_ok=True)
    output_filename = Path(args.results_dir) / f"scenarios_pipeline_{args.species.lower()}_{args.model.lower()}_{args.reasoning_level.lower()}_{run_timestamp}.json"
    # --- MODIFIED: Save output_data instead of just results_list ---
    save_json(output_filename, output_data)
    # --- END MODIFIED ---

    if logger: logger.info(f"Full scenario pipeline results saved to {output_filename}")
    else: print(f"Full scenario pipeline results saved to {output_filename}")

    return str(output_filename) # Return the path as a string

# --- Main Function to be Called from Dashboard ---

def run_full_set(species: str, model: str, reasoning_level: str, data_dir=None, results_dir=None, bench_file=None, scenarios_file=None):
    """
    Runs the full set of benchmarks and scenario pipelines sequentially.
    Uses default paths if specific ones are not provided.
    """
    # Use provided paths or defaults
    data_dir_path = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    results_dir_path = Path(results_dir) if results_dir else DEFAULT_RESULTS_DIR
    bench_file_path = Path(bench_file) if bench_file else DEFAULT_BENCHMARKS_FILE
    scenarios_file_path = Path(scenarios_file) if scenarios_file else DEFAULT_SCENARIOS_FILE

    # Simple namespace class for compatibility
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
        # Run benchmarks
        benchmark_output_file = asyncio.run(_run_all_benchmarks_async(args))

        # Run scenarios
        scenario_output_file = asyncio.run(_run_all_scenarios_async(args))

        return benchmark_output_file, scenario_output_file

    except Exception as e:
        error_msg = f"Error during full run: {e}"
        if logger: logger.exception(error_msg)
        else: print(error_msg)
        raise # Re-raise the exception


# --- Standalone Execution Block ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run full set of EthicsEngine benchmarks and scenario pipelines.")
    parser.add_argument("--species", default="Jiminies", help="Species name")
    parser.add_argument("--model", default="Utilitarian", help="Reasoning model")
    parser.add_argument("--reasoning-level", default="low", choices=["low", "medium", "high"], help="Reasoning level")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Data directory")
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR), help="Results directory")
    parser.add_argument("--bench-file", default=str(DEFAULT_BENCHMARKS_FILE), help="Benchmark JSON file path")
    parser.add_argument("--scenarios-file", default=str(DEFAULT_SCENARIOS_FILE), help="Scenarios JSON file path")

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
        print("\nFull run completed successfully.")
        if bench_out: print(f"Benchmark results: {bench_out}")
        if scenario_out: print(f"Scenario results: {scenario_out}")

    except Exception as e:
        print(f"\nAn error occurred during the full run: {e}")
