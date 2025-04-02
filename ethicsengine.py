#!/usr/bin/env python3
import argparse
import logging
import sys
import os

# Ensure the project root is in the Python path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- Configuration Loading ---
# Attempt to load configuration, including log settings
try:
    # Import LOG_FILE_PATH as well
    from config.config import settings, logger, LOG_FILE_PATH
    log_level_setting = settings.get("log_level", "INFO")
    log_level = getattr(logging, log_level_setting.upper(), logging.INFO)
except ImportError as e:
    # Set defaults if config fails to load
    LOG_FILE_PATH = "app.log" # Default log path if config fails
    # Set defaults if config fails to load
    log_level = logging.INFO
    # Get the root logger directly if config import fails
    logger = logging.getLogger() # Get root logger
    logger.warning(f"Could not import configuration from config.config: {e}. Using default log level INFO.")

# --- Logging Setup will be done in main() after args are parsed ---

# --- Import Run Functions ---
# Import the synchronous entry points from the refactored scripts (now in dashboard)
try:
    from dashboard.run_benchmarks import run_benchmarks
    from dashboard.run_scenario_pipelines import run_all_scenarios
except ImportError as e:
    # Use the configured logger
    logger.error(f"Failed to import run functions from dashboard: {e}. CLI runs will not be available.", exc_info=True)
    # Define dummy functions if import fails
    def run_benchmarks(*args, **kwargs): logger.error("run_benchmarks function not available due to import error.")
    def run_all_scenarios(*args, **kwargs): logger.error("run_all_scenarios function not available due to import error.")


# --- Argument Parsing ---
def main():
    parser = argparse.ArgumentParser(description="EthicsEngine: Run UI or Command-Line Tasks.")

    # --- Mode Selection (Mutually Exclusive) ---
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--ui', action='store_true', help='Launch the interactive dashboard UI (default if no other mode selected).')
    mode_group.add_argument('--run-benchmarks', action='store_true', help='Run the full benchmark suite via CLI.')
    mode_group.add_argument('--run-scenarios', action='store_true', help='Run all scenario pipelines via CLI.')

    # --- Common Run Arguments ---
    # Arguments used by both benchmark and scenario runs
    parser.add_argument("--species", help="Species name (e.g., Jiminies)")
    parser.add_argument("--model", help="Reasoning model (e.g., Deontological)")
    parser.add_argument("--reasoning-level", type=str, choices=["low", "medium", "high"], help="Reasoning level") # Added type=str
    parser.add_argument("--data-dir", help="Path to the data directory (overrides default)")
    parser.add_argument("--results-dir", help="Directory to save results (overrides default)")

    # --- Specific Run Arguments ---
    parser.add_argument("--bench-file", help="Path to the benchmark JSON file (for --run-benchmarks)")
    parser.add_argument("--scenarios-file", help="Path to the scenarios JSON file (for --run-scenarios)")

    args = parser.parse_args()

    # --- Determine Action ---
    run_action = None
    if args.run_benchmarks:
        run_action = "benchmarks"
    elif args.run_scenarios:
         run_action = "scenarios"
    # UI is the default if no run action is specified

    # --- Configure File Logging ---
    # Set up basic file logging here, after config is loaded and args parsed.
    # This ensures the file logger is active for both UI and CLI modes.
    # Use force=True to ensure reconfiguration even if basicConfig was called implicitly
    # or by another library before this point.
    logging.basicConfig(
        level=log_level, # Use level determined from config or default
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        filename=LOG_FILE_PATH, # Use path determined from config or default
        filemode='a', # Append mode
        force=True # Force reconfiguration
    )
    # Log confirmation using the configured logger instance
    logger.info(f"File logging configured to {LOG_FILE_PATH} with level {log_level_setting}")

    # --- Configure Console Logging Conditionally ---
    console_handler = None
    if run_action: # Only add console handler if a CLI action is specified
        console_handler = logging.StreamHandler(sys.stderr)
        # Optional: Add a formatter if desired
        # formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s')
        # console_handler.setFormatter(formatter)
        logger.addHandler(console_handler) # Add handler to the logger obtained from config or root
        logger.info(f"Console logging enabled for CLI action: {run_action}")
    else:
        # Ensure no handlers are attached if running UI (or remove existing ones if necessary)
        # This might be overly aggressive if config.py is supposed to add handlers.
        # For now, assume we only want the console handler for CLI runs.
        for handler in logger.handlers[:]: # Iterate over a copy
             if isinstance(handler, logging.StreamHandler):
                  logger.removeHandler(handler)
        logger.info("Console logging disabled for UI mode.")


    # --- Execute Action ---
    # console_handler = None # Initialize handler variable outside try blocks # Moved up
    if run_action == "benchmarks":
        logger.info("Executing benchmark run via CLI...")
        try:
            # --- Console handler is already added above if needed ---

            # Prepare args for run_benchmarks, using defaults from its own parser if not provided
            bench_args = argparse.Namespace()
            # Populate from CLI args or let the function use its internal defaults
            bench_args.species = args.species # Will be None if not provided, run_benchmarks handles default
            bench_args.model = args.model
            bench_args.reasoning_level = args.reasoning_level
            bench_args.data_dir = args.data_dir
            bench_args.results_dir = args.results_dir
            bench_args.bench_file = args.bench_file

            # run_benchmarks is synchronous and handles its own defaults/asyncio.run
            run_benchmarks(bench_args)
            logger.info("Benchmark run completed.")

        except Exception as e:
            logger.error(f"Error during CLI benchmark run: {e}", exc_info=True)
            print(f"Error during benchmark run: {e}", file=sys.stderr)
            sys.exit(1) # Exit on error
        # finally: # Removed finally block for handler removal
            # --- Console handler removal is handled at the end or not needed ---

    elif run_action == "scenarios":
        logger.info("Executing scenario pipelines run via CLI...")
        try:
            # --- Console handler is already added above if needed ---

            # Prepare args for run_all_scenarios
            scenario_args = argparse.Namespace()
            scenario_args.species = args.species
            scenario_args.model = args.model
            scenario_args.reasoning_level = args.reasoning_level
            scenario_args.data_dir = args.data_dir
            scenario_args.results_dir = args.results_dir
            scenario_args.scenarios_file = args.scenarios_file

            # run_all_scenarios is the synchronous wrapper
            run_all_scenarios(scenario_args)
            logger.info("Scenario pipelines run completed.")

        except Exception as e:
            logger.error(f"Error during CLI scenario run: {e}", exc_info=True)
            print(f"Error during scenario run: {e}", file=sys.stderr)
            sys.exit(1) # Exit on error
        # finally: # Removed finally block for handler removal
            # --- Console handler removal is handled at the end or not needed ---

    else: # Default to UI
        # logger.info("Launching Interactive Dashboard...") # Keep this silent for UI mode
        try:
            # Import the App class and run it (ensure textual is installed)
            from dashboard.interactive_dashboard import EthicsEngineApp
            EthicsEngineApp().run() # Instantiate and run the app
        except ImportError:
            # logger.error("Could not import EthicsEngineApp from dashboard.interactive_dashboard. Make sure the file exists and is runnable.") # Removed logger call
            sys.exit(1) # Exit silently on import error
        except Exception as e:
             # logger.error(f"An error occurred while running the dashboard: {e}", exc_info=True) # Removed logger call
             # Optionally log to file logger if it was successfully configured before the error
             try:
                 logger.error(f"An error occurred while running the dashboard: {e}", exc_info=True)
             except NameError: # logger might not be defined if config import failed
                 pass
             sys.exit(1) # Exit silently on runtime error

    # elif args.run_scenario:
    #     # logger.info(f"Running scenario: {args.run_scenario}") # Removed logger call
    #     # Import and call scenario running logic
    #     # from run_scenario_pipelines import run_single_scenario # Example
    #     # run_single_scenario(args.run_scenario)
    #     # print("Scenario running logic not yet implemented in ethicsengine.py") # Removed print

    # elif args.run_benchmarks:
    #     # logger.info("Running benchmarks...") # Removed logger call
    #     # Import and call benchmark running logic
    #     # from run_benchmarks import run_all_benchmarks # Example
    #     # run_all_benchmarks()
    #     # print("Benchmark running logic not yet implemented in ethicsengine.py") # Removed print

    # The old 'else' block is removed as the UI is now the default.
    # If specific CLI actions are added later, they should be handled in the
    # 'elif' blocks above.

if __name__ == "__main__":
    main()
