#!/usr/bin/env python3
"""
EthicsEngine Main Entry Point

This script serves as the main entry point for the EthicsEngine application.
It handles command-line argument parsing to determine whether to launch the
interactive Textual UI dashboard or execute specific tasks via the command line,
such as running benchmark suites or scenario pipelines.

It also configures logging based on settings loaded from config/config.py
and command-line arguments.
"""
import argparse
import logging
import sys
import os
import asyncio
from reasoning_agent import EthicsAgent

# Ensure the project root is in the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- Configuration Loading ---
# Attempt to load configuration, including log settings
try:
    from config.config import settings, logger, LOG_FILE_PATH, semaphore
    log_level_setting = settings.get("log_level", "INFO")
    log_level = getattr(logging, log_level_setting.upper(), logging.INFO)
except ImportError as e:
    # Set defaults if config fails to load
    semaphore = None
    LOG_FILE_PATH = "app.log"
    log_level = logging.INFO
    logger = logging.getLogger()
    logger.warning(f"Could not import configuration from config.config: {e}. Using default log level INFO.")

# --- Logging Setup (Deferred) ---
# Logging is configured within main() after parsing arguments.

# --- Import Run Functions ---
# Import the potentially async entry points and semaphore monitor function
# --- Import Dashboard App ---
# Moved import to top level to potentially resolve startup issues
# Add more specific error logging during import
EthicsEngineApp = None # Initialize as None
try:
    from dashboard.interactive_dashboard import EthicsEngineApp
except ImportError as e_imp:
    # Log the specific ImportError
    logger.error(f"Failed to import EthicsEngineApp due to ImportError: {e_imp}. UI will not be available.", exc_info=True)
    print(f"ERROR: Failed to import EthicsEngineApp due to ImportError: {e_imp}", file=sys.stderr)
except Exception as e_other:
    # Catch any other exception during import
    logger.error(f"An unexpected error occurred during EthicsEngineApp import: {e_other}. UI will not be available.", exc_info=True)
    print(f"ERROR: An unexpected error occurred during EthicsEngineApp import: {e_other}", file=sys.stderr)
    # Ensure EthicsEngineApp remains None
    EthicsEngineApp = None

try:
    from dashboard.run_benchmarks import run_benchmarks_async, monitor_semaphore_cli
    from dashboard.run_scenario_pipelines import run_all_scenarios_async
except Exception as e: # Catch any exception during these imports
    # Log the error more generically, but still provide details
    logger.error(f"Failed during import of run functions from dashboard: {e}. CLI runs may not be available.", exc_info=True)
    print(f"ERROR: Failed during import of run functions: {e}", file=sys.stderr)
    # Define dummy async functions if import fails.
    async def run_benchmarks_async(*args, **kwargs): logger.error("run_benchmarks_async function not available due to import error.")
    async def monitor_semaphore_cli(*args, **kwargs): logger.error("monitor_semaphore_cli function not available due to import error.")
    async def run_all_scenarios_async(*args, **kwargs): logger.error("run_all_scenarios_async function not available due to import error.")

def main():
    parser = argparse.ArgumentParser(description="EthicsEngine: Run UI or Command-Line Tasks.")

    # Mode Selection (Mutually Exclusive)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--ui', action='store_true', help='Launch the interactive dashboard UI (default if no other mode selected).')
    mode_group.add_argument('--run-benchmarks', action='store_true', help='Run the full benchmark suite via CLI.')
    mode_group.add_argument('--run-scenarios', action='store_true', help='Run all scenario pipelines via CLI.')
    mode_group.add_argument('--run-single-benchmark', action='store_true', help='Run a single benchmark item by ID via CLI.')
    mode_group.add_argument('--run-single-scenario', action='store_true', help='Run a single scenario by ID via CLI.')

    # Common Run Arguments (used by multiple modes)
    parser.add_argument("--species", help="Species name (e.g., Jiminies)")
    parser.add_argument("--model", help="Reasoning model (e.g., Deontological)")
    parser.add_argument("--reasoning-level", type=str, choices=["low", "medium", "high"], help="Reasoning level")
    parser.add_argument("--data-dir", help="Path to the data directory (overrides default)")
    parser.add_argument("--results-dir", help="Directory to save results (overrides default)")

    # Specific Run Arguments
    parser.add_argument("--bench-file", help="Path to the benchmark JSON file (for --run-benchmarks or --run-single-benchmark)")
    parser.add_argument("--scenarios-file", help="Path to the scenarios JSON file (for --run-scenarios or --run-single-scenario)")
    parser.add_argument("--item-id", help="The ID of the benchmark/scenario item to run (required for --run-single-benchmark/--run-single-scenario)")
    parser.add_argument("-m", "--multiple-runs", type=int, default=1, help="Number of concurrent benchmark/scenario jobs to run (for --run-benchmarks/--run-scenarios)")

    args = parser.parse_args()

    # Determine Action based on CLI flags
    run_action = None
    if args.run_benchmarks:
        run_action = "benchmarks"
    elif args.run_scenarios:
         run_action = "scenarios"
    elif args.run_single_benchmark:
         run_action = "single_benchmark"
    elif args.run_single_scenario:
         run_action = "single_scenario"
    # UI is the default if no run action is specified

    # Configure File Logging
    # Use force=True to ensure reconfiguration if basicConfig was called implicitly elsewhere.
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        filename=LOG_FILE_PATH,
        filemode='a',
        force=True
    )
    logger.info(f"File logging configured to {LOG_FILE_PATH} with level {log_level_setting}")

    # Configure Console Logging Conditionally (only for CLI actions)
    if run_action:
        console_handler = logging.StreamHandler(sys.stderr)
        # formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s') # Optional formatter
        # console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        logger.info(f"Console logging enabled for CLI action: {run_action}")
    else:
        # Remove existing StreamHandlers if running in UI mode to avoid duplicates.
        for handler in logger.handlers[:]:
             if isinstance(handler, logging.StreamHandler):
                  logger.removeHandler(handler)

    # --- Execute Action ---
    if run_action == "benchmarks":
        logger.info("Executing benchmark run(s) via CLI...")
        try:
            # Prepare args namespace for run_benchmarks_async
            bench_args = argparse.Namespace(
                species=args.species,
                model=args.model,
                reasoning_level=args.reasoning_level,
                data_dir=args.data_dir,
                results_dir=args.results_dir,
                bench_file=args.bench_file
            )
            # multiple_runs is handled by the wrapper

            # Async Wrapper for Multiple Benchmark Runs
            async def run_multiple_benchmarks():
                """Handles concurrent execution and semaphore monitoring for benchmark runs."""
                num_runs = args.multiple_runs
                logger.info(f"Starting {num_runs} concurrent benchmark run(s)...")

                if semaphore is None or monitor_semaphore_cli is None:
                     logger.error("Semaphore or monitor function not available. Cannot run benchmarks concurrently.")
                     return

                # Agent creation is handled within run_benchmarks_async

                monitor_task = asyncio.create_task(monitor_semaphore_cli(semaphore))
                benchmark_tasks = [run_benchmarks_async(bench_args) for _ in range(num_runs)]

                all_run_results = []
                try:
                    all_run_results = await asyncio.gather(*benchmark_tasks, return_exceptions=True)
                finally:
                    # Ensure monitor task is cancelled and awaited
                    if monitor_task and not monitor_task.done():
                        monitor_task.cancel()
                        await asyncio.gather(monitor_task, return_exceptions=True)
                    logger.info("All benchmark runs gather completed.")

                # Log results/errors
                success_count = 0
                for i, result_or_exc in enumerate(all_run_results):
                    if isinstance(result_or_exc, Exception):
                        logger.error(f"Benchmark run {i+1}/{num_runs} failed with exception: {result_or_exc}", exc_info=result_or_exc)
                    elif result_or_exc is None:
                        logger.error(f"Benchmark run {i+1}/{num_runs} failed (returned None, check logs for details).")
                    else:
                        logger.info(f"Benchmark run {i+1}/{num_runs} completed successfully. Results saved to: {result_or_exc}")
                        success_count += 1
                logger.info(f"Finished executing {num_runs} benchmark runs. Successful: {success_count}, Failed: {num_runs - success_count}.")
            # --- End Async Wrapper ---

            # Execute the async wrapper function
            asyncio.run(run_multiple_benchmarks())

        except Exception as e:
            logger.error(f"Error during CLI benchmark run setup or execution: {e}", exc_info=True)
            print(f"Error during benchmark run: {e}", file=sys.stderr)
            sys.exit(1)

    elif run_action == "scenarios":
        logger.info("Executing scenario pipelines run via CLI...")
        try:
            # Prepare args namespace for run_all_scenarios_async
            scenario_args = argparse.Namespace(
                species=args.species,
                model=args.model,
                reasoning_level=args.reasoning_level,
                data_dir=args.data_dir,
                results_dir=args.results_dir,
                scenarios_file=args.scenarios_file
            )
            # multiple_runs is handled by the wrapper

            # Async Wrapper for Multiple Scenario Runs
            async def run_multiple_scenarios():
                """Handles concurrent execution and semaphore monitoring for scenario runs."""
                num_runs = args.multiple_runs
                logger.info(f"Starting {num_runs} concurrent scenario run(s)...")

                if semaphore is None or monitor_semaphore_cli is None:
                     logger.error("Semaphore or monitor function not available. Cannot run scenarios concurrently.")
                     return

                monitor_task = asyncio.create_task(monitor_semaphore_cli(semaphore))
                scenario_tasks = [run_all_scenarios_async(scenario_args) for _ in range(num_runs)]

                all_run_results = []
                try:
                    all_run_results = await asyncio.gather(*scenario_tasks, return_exceptions=True)
                finally:
                    # Ensure monitor task is cancelled and awaited
                    if monitor_task and not monitor_task.done():
                        monitor_task.cancel()
                        await asyncio.gather(monitor_task, return_exceptions=True)
                    logger.info("All scenario runs gather completed.")

                # Log results/errors
                success_count = 0
                for i, result_or_exc in enumerate(all_run_results):
                    if isinstance(result_or_exc, Exception):
                        logger.error(f"Scenario run {i+1}/{num_runs} failed with exception: {result_or_exc}", exc_info=result_or_exc)
                    elif result_or_exc is None:
                        logger.error(f"Scenario run {i+1}/{num_runs} failed (returned None, check logs for details).")
                    else:
                        logger.info(f"Scenario run {i+1}/{num_runs} completed successfully. Results saved to: {result_or_exc}")
                        success_count += 1
                logger.info(f"Finished executing {num_runs} scenario runs. Successful: {success_count}, Failed: {num_runs - success_count}.")
            # --- End Async Wrapper ---

            # Execute the async wrapper function
            asyncio.run(run_multiple_scenarios())

        except Exception as e:
            logger.error(f"Error during CLI scenario run setup or execution: {e}", exc_info=True)
            print(f"Error during scenario run: {e}", file=sys.stderr)
            sys.exit(1)

    elif run_action == "single_benchmark":
        logger.info("Executing single benchmark item run via CLI...")
        try:
            # Validate required args for this mode
            if not args.item_id:
                raise ValueError("--item-id is required when using --run-single-benchmark")
            # Warn if optional args are missing, but proceed as the called function handles defaults
            if not args.species:
                logger.warning("Missing --species argument, function will use its default.")
            if not args.model:
                logger.warning("Missing --model argument, function will use its default.")
            if not args.reasoning_level:
                logger.warning("Missing --reasoning-level argument, using default.")

            # Import necessary functions
            try:
                from dashboard.run_benchmarks import run_and_save_single_benchmark, load_benchmarks
            except ImportError as e:
                logger.error(f"Failed to import single benchmark run functions: {e}", exc_info=True)
                raise # Re-raise to exit if essential functions are missing

            # Prepare Args Namespace
            # Define defaults for paths if not provided via CLI
            default_data_dir = "data"
            default_results_dir = "results"
            default_bench_file = os.path.join(default_data_dir, "simple_bench_public.json")

            effective_data_dir = args.data_dir if args.data_dir else default_data_dir
            effective_results_dir = args.results_dir if args.results_dir else default_results_dir
            effective_bench_file = args.bench_file if args.bench_file else default_bench_file

            single_run_args = argparse.Namespace(
                species=args.species, # Pass None if not provided; function handles defaults
                model=args.model,
                reasoning_level=args.reasoning_level,
                data_dir=effective_data_dir,
                results_dir=effective_results_dir,
                bench_file=effective_bench_file
            )

            # Load benchmarks and find the target item
            logger.info(f"Loading benchmarks from: {effective_bench_file}")
            all_benchmarks = load_benchmarks(effective_bench_file)
            if not all_benchmarks:
                raise ValueError(f"No benchmarks loaded from {effective_bench_file}")

            # Find the specific benchmark item by its ID
            target_item = None
            for item in all_benchmarks:
                if isinstance(item, dict) and str(item.get("question_id")) == str(args.item_id):
                    target_item = item
                    break

            if target_item is None:
                raise ValueError(f"Benchmark item with ID '{args.item_id}' not found in {effective_bench_file}")

            logger.info(f"Found benchmark item ID: {args.item_id}. Starting run...")

            # Execute the single run
            # run_and_save_single_benchmark is async, so wrap with asyncio.run
            saved_file = asyncio.run(run_and_save_single_benchmark(target_item, single_run_args))

            if saved_file:
                logger.info(f"Single benchmark run completed. Results saved to: {saved_file}")
            else:
                logger.error(f"Single benchmark run for item ID {args.item_id} failed to save results.")

        except ValueError as e:
             logger.error(f"Configuration error for single benchmark run: {e}")
             print(f"Error: {e}", file=sys.stderr)
             sys.exit(1)
        except Exception as e:
            logger.error(f"Error during CLI single benchmark run: {e}", exc_info=True)
            print(f"Error during single benchmark run: {e}", file=sys.stderr)
            sys.exit(1)

    elif run_action == "single_scenario":
        logger.info("Executing single scenario run via CLI...")
        try:
            # Validate required args for this mode
            if not args.item_id:
                raise ValueError("--item-id is required when using --run-single-scenario")
            if not args.species:
                logger.warning("Missing --species argument, using default.")
            if not args.model:
                logger.warning("Missing --model argument, using default.")
            if not args.reasoning_level:
                logger.warning("Missing --reasoning-level argument, using default.")

            # Import necessary functions
            try:
                from dashboard.run_scenario_pipelines import run_and_save_single_scenario, load_scenarios
            except ImportError as e:
                logger.error(f"Failed to import single scenario run functions: {e}", exc_info=True)
                raise # Re-raise to exit

            # Prepare Args Namespace
            default_data_dir = "data"
            default_results_dir = "results"
            default_scenarios_file = os.path.join(default_data_dir, "scenarios.json")

            effective_data_dir = args.data_dir if args.data_dir else default_data_dir
            effective_results_dir = args.results_dir if args.results_dir else default_results_dir
            effective_scenarios_file = args.scenarios_file if args.scenarios_file else default_scenarios_file

            single_run_args = argparse.Namespace(
                species=args.species,
                model=args.model,
                reasoning_level=args.reasoning_level,
                data_dir=effective_data_dir,
                results_dir=effective_results_dir,
                scenarios_file=effective_scenarios_file
            )

            # Load scenarios and find the item
            logger.info(f"Loading scenarios from: {effective_scenarios_file}")
            all_scenarios = load_scenarios(effective_scenarios_file)
            if not all_scenarios:
                raise ValueError(f"No scenarios loaded from {effective_scenarios_file}")

            target_item = None
            for item in all_scenarios:
                # Assuming scenarios are dicts with an 'id' key
                if isinstance(item, dict) and str(item.get("id")) == str(args.item_id):
                    target_item = item
                    break

            if target_item is None:
                raise ValueError(f"Scenario item with ID '{args.item_id}' not found in {effective_scenarios_file}")

            logger.info(f"Found scenario item ID: {args.item_id}. Starting run...")

            # Execute the single run
            saved_file = asyncio.run(run_and_save_single_scenario(target_item, single_run_args))

            if saved_file:
                logger.info(f"Single scenario run completed. Results saved to: {saved_file}")
            else:
                logger.error(f"Single scenario run for item ID {args.item_id} failed to save results.")

        except ValueError as e:
            logger.error(f"Configuration error for single scenario run: {e}")
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            logger.error(f"Error during CLI single scenario run: {e}", exc_info=True)
            print(f"Error during single scenario run: {e}", file=sys.stderr)
            sys.exit(1)

    else: # Default to UI
        if EthicsEngineApp: # Check if import was successful at the top level
            try:
                EthicsEngineApp().run()
            except Exception as e:
                # Catch errors during instantiation or run()
                logger.error(f"An error occurred while instantiating or running the dashboard: {e}", exc_info=True)
                print(f"ERROR: An error occurred while running the dashboard: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            # This case should now be hit if the import failed at the top level
            print("Error: Could not start the dashboard UI because EthicsEngineApp failed to import. Check logs.", file=sys.stderr)
            sys.exit(1)
        # Removed the outer try/except Exception as it's now handled inside the 'if EthicsEngineApp' block

if __name__ == "__main__":
    main()
