# dashboard/interactive_dashboard.py
import sys
import os

# Prevent direct execution
if __name__ == "__main__" and sys.argv[0].endswith('__main__.py'): # Check if run via python -m
    print("Error: Please run the application using 'python ethicsengine.py' from the project root directory.")
    sys.exit(1)

import json
import asyncio
import traceback
from pathlib import Path
import functools
from datetime import datetime
import argparse # Need argparse to create the namespace object

from textual.app import App, ComposeResult
from textual.containers import Container, VerticalScroll, Horizontal, Vertical
from textual.widgets import Header, Footer, Button, Static, Select, Label, Markdown, LoadingIndicator, TabbedContent, TabPane, RadioSet, RadioButton
from textual.binding import Binding
from textual.reactive import reactive
# Message import removed

# Import Views
try:
    from dashboard.views import (
        RunConfigurationView,
        DataManagementView,
        ResultsBrowserView,
        LogView,
        ConfigEditorView,
    )
except ImportError as e:
     print(f"Fatal Error: Could not import dashboard views: {e}")
     import logging; logging.basicConfig(level=logging.ERROR); logging.error(f"Fatal Error: Import views: {e}", exc_info=True); exit()

# Import Utils
try:
    from dashboard.dashboard_utils import (load_json, save_json, SCENARIOS_FILE, GOLDEN_PATTERNS_FILE, SPECIES_FILE, BENCHMARKS_FILE, DATA_DIR, RESULTS_DIR)
except ImportError as e:
     print(f"Fatal Error: Could not import dashboard utils: {e}")
     import logging; logging.basicConfig(level=logging.ERROR); logging.error(f"Fatal Error: Import utils: {e}", exc_info=True); exit()

# Import Full Run Logic & Specific Run Functions
try:
    from dashboard.dashboard_full_run import run_full_set
    # Import the specific run functions needed for delegation
    from .run_scenario_pipelines import run_all_scenarios, run_and_save_single_scenario
    from .run_benchmarks import run_benchmarks, run_and_save_single_benchmark, load_benchmarks # Keep load_benchmarks for single item lookup
except ImportError as e:
    print(f"Warning: Could not import run logic: {e}")
    # Define dummy functions if import fails to prevent crashes
    def run_full_set(*args, **kwargs): print("ERROR: run_full_set not available!"); return None, None
    def run_all_scenarios(*args, **kwargs): print("ERROR: run_all_scenarios not available!"); return None
    def run_and_save_single_scenario(*args, **kwargs): print("ERROR: run_and_save_single_scenario not available!"); return None
    def run_benchmarks(*args, **kwargs): print("ERROR: run_benchmarks not available!"); return None
    def run_and_save_single_benchmark(*args, **kwargs): print("ERROR: run_and_save_single_benchmark not available!"); return None
    def load_benchmarks(*args, **kwargs): print("ERROR: load_benchmarks not available!"); return []


# Import Backend Logic & Config
# Import the configured logger instance directly
from config.config import llm_config, logger as configured_logger, semaphore, SEMAPHORE_CAPACITY

# Constants and Helper Class
REASONING_DEPTH_OPTIONS = ["low", "medium", "high"]
TASK_TYPE_OPTIONS = ["Ethical Scenarios", "Benchmarks"]

class ArgsNamespace(argparse.Namespace): # Inherit from argparse.Namespace for compatibility
    # Helper class to mimic argparse Namespace
    def __init__(self, data_dir, results_dir, species, model, reasoning_level, bench_file=None, scenarios_file=None):
        super().__init__() # Initialize base class
        self.data_dir = str(data_dir); self.results_dir = str(results_dir); self.species = species; self.model = model; self.reasoning_level = reasoning_level; self.bench_file = str(bench_file) if bench_file else None; self.scenarios_file = str(scenarios_file) if scenarios_file else None


class EthicsEngineApp(App):
    CSS_PATH = "dashboard.tcss"
    BINDINGS = [ Binding("q", "quit", "Quit"), ]

    # Reactive Properties
    run_status = reactive("Ready")
    semaphore_status = reactive(f"Concurrency: 0/{SEMAPHORE_CAPACITY}")
    selected_species = reactive(None)
    selected_model = reactive(None)
    selected_depth = reactive(REASONING_DEPTH_OPTIONS[0])
    selected_task_type = reactive(TASK_TYPE_OPTIONS[0])
    selected_task_item = reactive(None) # Holds the ID of the selected scenario/benchmark
    loading = reactive(False)

    def __init__(self):
        super().__init__()
        # --- Logger is imported as configured_logger ---

        # Load initial data
        self.scenarios = load_json(SCENARIOS_FILE, [])
        if isinstance(self.scenarios, dict) and "Error" in self.scenarios:
             configured_logger.error(f"Failed to load scenarios: {self.scenarios['Error']}") # Use configured_logger
             self.scenarios = [{"id": "LOAD_ERROR", "prompt": f"Error: {self.scenarios['Error']}"}]
        elif not isinstance(self.scenarios, list):
             configured_logger.error(f"Scenarios file {SCENARIOS_FILE} is not a list. Content: {self.scenarios}") # Use configured_logger
             self.scenarios = [{"id": "FORMAT_ERROR", "prompt": "Error: scenarios.json is not a list."}]

        self.models = load_json(GOLDEN_PATTERNS_FILE, {"Error": "Could not load models"})
        if "Error" in self.models: configured_logger.error(f"Failed to load models: {self.models['Error']}") # Use configured_logger
        self.species = load_json(SPECIES_FILE, {"Error": "Could not load species"})
        if "Error" in self.species: configured_logger.error(f"Failed to load species: {self.species['Error']}") # Use configured_logger
        self.benchmarks_data_struct = load_json(BENCHMARKS_FILE, {"Error": "Could not load benchmarks"})
        if "Error" in self.benchmarks_data_struct: configured_logger.error(f"Failed to load benchmarks: {self.benchmarks_data_struct['Error']}") # Use configured_logger

        # Set initial selections
        if isinstance(self.species, dict) and "Error" not in self.species: self.selected_species = next(iter(self.species), None)
        if isinstance(self.models, dict) and "Error" not in self.models: self.selected_model = next(iter(self.models), None)
        self._update_initial_task_item()

    def _update_initial_task_item(self):
        """Sets the initial selected task item ID based on the current task type."""
        configured_logger.debug(f"_update_initial_task_item running for Task Type: '{self.selected_task_type}'") # Use configured_logger
        default_item_id = None
        if self.selected_task_type == "Ethical Scenarios":
            if isinstance(self.scenarios, list) and self.scenarios:
                 first_scenario = self.scenarios[0]
                 if isinstance(first_scenario, dict):
                      default_item_id = first_scenario.get("id")
                      configured_logger.debug(f"Found default scenario ID: {default_item_id}") # Use configured_logger
                 else: configured_logger.warning("First scenario item invalid format.") # Use configured_logger
            else: configured_logger.warning("Scenarios data not loaded, empty, or not a list.") # Use configured_logger
        elif self.selected_task_type == "Benchmarks":
            if isinstance(self.benchmarks_data_struct, dict) and "eval_data" in self.benchmarks_data_struct:
                 eval_list = self.benchmarks_data_struct["eval_data"]
                 if isinstance(eval_list, list) and eval_list:
                      first_item = eval_list[0]
                      if isinstance(first_item, dict) and "question_id" in first_item:
                           default_item_id = str(first_item["question_id"])
                           configured_logger.debug(f"Found default benchmark QID: {default_item_id}") # Use configured_logger
                      else: configured_logger.warning("First benchmark item invalid format.") # Use configured_logger
                 else: configured_logger.warning("Benchmark eval_data not a non-empty list.") # Use configured_logger
            else: configured_logger.warning("Benchmark data structure invalid.") # Use configured_logger

        self.selected_task_item = default_item_id
        configured_logger.info(f"Default Task Item ID set to: {self.selected_task_item} for Task Type: {self.selected_task_type}") # Use configured_logger

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="loading-layer-container"): yield LoadingIndicator(id="loading-indicator")
        with TabbedContent(id="main-tabs", initial="tab-run"):
            with TabPane("Agent Run", id="tab-run"):
                 yield RunConfigurationView(
                     species=self.species, models=self.models,
                     depth_options=REASONING_DEPTH_OPTIONS, task_types=TASK_TYPE_OPTIONS,
                     scenarios=self.scenarios, benchmarks=self.benchmarks_data_struct,
                     current_species=self.selected_species, current_model=self.selected_model,
                     current_depth=self.selected_depth, current_task_type=self.selected_task_type,
                     current_task_item=self.selected_task_item,
                     id="run-configuration-view"
                 )
            with TabPane("Data Management", id="tab-data"): yield DataManagementView(scenarios=self.scenarios, models=self.models, species_data=self.species, id="data-management-view")
            with TabPane("Results Browser", id="tab-results-browser"): yield ResultsBrowserView(id="results-browser-view")
            with TabPane("Log Viewer", id="tab-log"): yield LogView(id="log-view")
            with TabPane("Configuration", id="tab-config"): yield ConfigEditorView(id="config-editor-view")
        yield Footer()

    def on_mount(self) -> None:
        configured_logger.info("EthicsEngineApp Mounted") # Use configured_logger
        self.query_one("#loading-indicator").display = False
        self.set_interval(1.0, self.update_semaphore_status)
        configured_logger.info("Started UI semaphore status polling.") # Use configured_logger

    def update_semaphore_status(self) -> None:
        """Periodically checks the semaphore status and updates the reactive variable."""
        try:
            if hasattr(semaphore, 'active_count') and hasattr(semaphore, 'capacity'):
                 active = semaphore.active_count
                 capacity = semaphore.capacity
                 self.semaphore_status = f"Concurrency: {active}/{capacity}"
            else:
                 self.semaphore_status = "Concurrency: N/A (Error)"
                 configured_logger.warning("Global semaphore object is not a TrackedSemaphore instance.") # Use configured_logger
        except Exception as e:
             self.semaphore_status = "Concurrency: Error"
             configured_logger.error(f"Error updating semaphore status: {e}", exc_info=True) # Use configured_logger

    # --- Watchers ---
    def watch_run_status(self, status: str) -> None:
        self.loading = ("Running" in status)
        try:
            config_view = self.query_one(RunConfigurationView)
            status_widget = config_view.query_one("#run-status", Static)
            status_widget.update(f"Status: {status}")
        except Exception as e:
            configured_logger.warning(f"Could not find #run-status widget: {e}") # Use configured_logger

    def watch_semaphore_status(self, status: str) -> None:
        """Updates the UI when the semaphore_status reactive variable changes."""
        try:
            config_view = self.query_one(RunConfigurationView)
            sema_widget = config_view.query_one("#semaphore-status-display", Static)
            sema_widget.update(status)
        except Exception as e:
            configured_logger.warning(f"Could not find #semaphore-status-display widget: {e}") # Use configured_logger

    def watch_loading(self, loading: bool) -> None:
        try:
            indicator = self.query_one("#loading-indicator"); indicator.display = loading
            config_view = self.query_one(RunConfigurationView)
            run_button = config_view.query_one("#run-analysis-button", Button)
            scenarios_button = config_view.query_one("#run-scenarios-button", Button)
            benchmarks_button = config_view.query_one("#run-benchmarks-button", Button)
            full_run_button = config_view.query_one("#run-full-set-button", Button)
            # Disable all run buttons when loading
            run_button.disabled = loading
            scenarios_button.disabled = loading
            benchmarks_button.disabled = loading
            full_run_button.disabled = loading
        except Exception as e:
            configured_logger.warning(f"Could not update loading indicator/buttons: {e}") # Use configured_logger

    # --- Refactored Actions ---
    async def action_run_analysis(self):
        """Runs analysis for a single selected task item by delegating to specific run/save functions."""
        if self.loading: self.notify("Analysis already running.", severity="warning"); return
        await asyncio.sleep(0.01); self.run_status = "Running Single Item..."
        saved_output_file = None # Will store the filename returned by the delegated function
        try:
            # Create args object from UI state
            args_obj = ArgsNamespace(
                data_dir=DATA_DIR,
                results_dir=RESULTS_DIR,
                species=self.selected_species,
                model=self.selected_model,
                reasoning_level=self.selected_depth,
                bench_file=BENCHMARKS_FILE, # Pass even if not used by scenarios
                scenarios_file=SCENARIOS_FILE # Pass even if not used by benchmarks
            )
            if not all([args_obj.species, args_obj.model, args_obj.reasoning_level]):
                raise ValueError("Species, Model, and Depth must be selected.")
            if not self.selected_task_type or self.selected_task_item is None:
                raise ValueError("Task Type and Task Item must be selected.")

            # Find the selected item dictionary
            selected_item_dict = None
            if self.selected_task_type == "Ethical Scenarios":
                 scenario_id_to_find = self.selected_task_item
                 if isinstance(self.scenarios, list):
                      for item in self.scenarios:
                           if isinstance(item, dict) and item.get("id") == scenario_id_to_find:
                                selected_item_dict = item
                                configured_logger.info(f"Found scenario object for ID: {scenario_id_to_find}") # Use configured_logger
                                break
                 if not selected_item_dict:
                      configured_logger.error(f"Could not find scenario with ID '{scenario_id_to_find}' in the loaded list.") # Use configured_logger
                      raise ValueError(f"Scenario ID '{scenario_id_to_find}' not found.")

                 # Delegate to the specific run/save function in a thread
                 configured_logger.info(f"Delegating single scenario run for ID {scenario_id_to_find} to thread...") # Use configured_logger
                 # Need to run the async function run_and_save_single_scenario in a sync context
                 def run_sync_wrapper(): return asyncio.run(run_and_save_single_scenario(selected_item_dict, args_obj))
                 saved_output_file = await asyncio.to_thread(run_sync_wrapper)
                 configured_logger.info(f"Threaded single scenario run completed. Saved file: {saved_output_file}") # Use configured_logger

            elif self.selected_task_type == "Benchmarks":
                 selected_qid_str = self.selected_task_item
                 # Need to load benchmarks to find the item dict
                 benchmarks_data = load_benchmarks(args_obj.bench_file) # Use imported load_benchmarks
                 target_benchmarks = benchmarks_data if isinstance(benchmarks_data, list) else []
                 if not target_benchmarks: raise ValueError("No benchmark data found or loaded.")

                 for item in target_benchmarks:
                      if isinstance(item, dict) and str(item.get("question_id")) == selected_qid_str:
                           selected_item_dict = item
                           configured_logger.info(f"Found benchmark object for QID: {selected_qid_str}") # Use configured_logger
                           break
                 if not selected_item_dict:
                      raise ValueError(f"Could not find benchmark data for QID: {selected_qid_str}")

                 # Delegate to the specific run/save function in a thread
                 configured_logger.info(f"Delegating single benchmark run for QID {selected_qid_str} to thread...") # Use configured_logger
                 # Need to run the async function run_and_save_single_benchmark in a sync context
                 def run_sync_wrapper(): return asyncio.run(run_and_save_single_benchmark(selected_item_dict, args_obj))
                 saved_output_file = await asyncio.to_thread(run_sync_wrapper)
                 configured_logger.info(f"Threaded single benchmark run completed. Saved file: {saved_output_file}") # Use configured_logger

            else:
                 raise ValueError("Invalid task type selected")

            # --- Update UI based on result ---
            if saved_output_file:
                 self.run_status = "Completed"
                 self.notify(f"Run complete. Results saved to {os.path.basename(saved_output_file)}.\nSee Results Browser tab.", title="Success", timeout=8)
                 # Refresh results browser
                 try:
                      browser_view = self.query_one(ResultsBrowserView)
                      browser_view._populate_file_list()
                 except Exception as browse_e:
                      self.log.warning(f"Could not refresh browser list: {browse_e}") # Use self.log
            else:
                 self.run_status = "Completed with Errors"
                 self.notify("Run finished, but failed to save results. Check logs.", title="Error Saving", severity="error", timeout=8)

        except ImportError as e:
             self.run_status = f"Error: Import failed ({e})"
             self.notify(f"Import Error: {e}", severity="error")
             configured_logger.error(f"Import Error: {e}\n{traceback.format_exc()}") # Use configured_logger
        except ValueError as e:
             self.run_status = f"Error: Config ({e})"
             self.notify(f"Config Error: {e}", severity="error")
             configured_logger.error(f"Config Error: {e}") # Use configured_logger
        except Exception as e:
             self.run_status = f"Error: {e}"
             self.notify(f"Runtime Error: {e}", severity="error")
             configured_logger.error(f"Runtime Error in action_run_analysis: {e}\n{traceback.format_exc()}") # Use configured_logger


    async def action_run_full_set(self):
        """Runs the full set of benchmarks and scenarios by delegating to dashboard_full_run."""
        if self.loading: return
        self.run_status = "Running Full Set..."
        try:
            # Create args object from UI state
            args_obj = ArgsNamespace(
                data_dir=DATA_DIR,
                results_dir=RESULTS_DIR,
                species=self.selected_species,
                model=self.selected_model,
                reasoning_level=self.selected_depth,
                bench_file=BENCHMARKS_FILE,
                scenarios_file=SCENARIOS_FILE
            )
            if not all([args_obj.species, args_obj.model, args_obj.reasoning_level]):
                raise ValueError("Species, Model, and Depth must be selected.")

            configured_logger.info(f"Delegating full set run for {args_obj.species}, {args_obj.model}, {args_obj.reasoning_level} to thread...") # Use configured_logger

            # Run the backend function in a thread, passing the args object
            # run_full_set is expected to be synchronous and handle its own async internally if needed
            saved_files = await asyncio.to_thread(
                run_full_set,
                species=args_obj.species,
                model=args_obj.model,
                reasoning_level=args_obj.reasoning_level,
                data_dir=args_obj.data_dir,
                results_dir=args_obj.results_dir,
                bench_file=args_obj.bench_file,
                scenarios_file=args_obj.scenarios_file
            )

            self.run_status = "Full Run Completed"
            if saved_files and len(saved_files) == 2 and all(saved_files):
                 bench_out, scenario_out = saved_files
                 self.notify(f"Full run finished.\nBenchmarks: {os.path.basename(bench_out)}\nScenarios: {os.path.basename(scenario_out)}\nSee Results Browser tab.", title="Success", timeout=10)
            else:
                 # Log the actual saved_files content for debugging if it failed
                 configured_logger.warning(f"Full run completed, but issues saving files. saved_files: {saved_files}") # Use configured_logger
                 self.notify("Full run completed, but issues saving files. Check logs.", severity="warning", title="Completed with Issues", timeout=10)

            # Refresh results browser regardless of save success
            try:
                 browser_view = self.query_one(ResultsBrowserView)
                 browser_view._populate_file_list()
                 configured_logger.info("Results browser list refreshed after full run.") # Use configured_logger
            except Exception as browse_e:
                 configured_logger.warning(f"Could not refresh results browser list after full run: {browse_e}") # Use configured_logger

        except ValueError as e:
             self.run_status = f"Error: Config ({e})"
             self.notify(f"Config Error: {e}", severity="error")
             configured_logger.error(f"Config Error in action_run_full_set: {e}") # Use configured_logger
        except Exception as e:
             self.run_status = f"Error: {e}"
             self.notify(f"Runtime Error: {e}", severity="error")
             configured_logger.error(f"Runtime Error in action_run_full_set: {e}\n{traceback.format_exc()}") # Use configured_logger


    async def action_run_scenarios(self):
        """Runs analysis for all scenarios by delegating to run_all_scenarios."""
        if self.loading: self.notify("Analysis already running.", severity="warning"); return
        await asyncio.sleep(0.01); self.run_status = "Running All Scenarios..."
        try:
            # Create args object from UI state
            args_obj = ArgsNamespace(
                data_dir=DATA_DIR,
                results_dir=RESULTS_DIR,
                species=self.selected_species,
                model=self.selected_model,
                reasoning_level=self.selected_depth,
                scenarios_file=SCENARIOS_FILE
                # bench_file is not needed by run_all_scenarios
            )
            if not all([args_obj.species, args_obj.model, args_obj.reasoning_level]):
                raise ValueError("Species, Model, and Depth must be selected.")

            configured_logger.info(f"Delegating 'run all scenarios' for {args_obj.species}, {args_obj.model}, {args_obj.reasoning_level} to thread...") # Use configured_logger

            # Run the backend function in a thread
            # run_all_scenarios is synchronous but runs async logic internally
            saved_output_file = await asyncio.to_thread(run_all_scenarios, cli_args=args_obj)

            self.run_status = "Completed Scenarios Run"
            if saved_output_file:
                 self.notify(f"All Scenarios run complete.\nResults saved to {os.path.basename(saved_output_file)}.\nSee Results Browser.", title="Success", timeout=8)
            else:
                 self.notify("Scenarios run finished, but failed to save results. Check logs.", title="Warning", severity="warning", timeout=8)

            # Refresh results browser
            try:
                 browser_view = self.query_one(ResultsBrowserView)
                 browser_view._populate_file_list()
            except Exception as browse_e:
                 self.log.warning(f"Could not refresh browser list after running scenarios: {browse_e}") # Use self.log

        except ImportError as e:
             self.run_status = f"Error: Import failed ({e})"
             self.notify(f"Import Error: {e}", severity="error")
             configured_logger.error(f"Import Error in action_run_scenarios: {e}\n{traceback.format_exc()}") # Use configured_logger
        except ValueError as e:
             self.run_status = f"Error: Config ({e})"
             self.notify(f"Config Error: {e}", severity="error")
             configured_logger.error(f"Config Error in action_run_scenarios: {e}") # Use configured_logger
        except Exception as e:
             self.run_status = f"Error: {e}"
             self.notify(f"Runtime Error: {e}", severity="error")
             configured_logger.error(f"Runtime Error in action_run_scenarios: {e}\n{traceback.format_exc()}") # Use configured_logger


    async def action_run_benchmarks(self):
        """Runs analysis for all benchmarks by delegating to run_benchmarks."""
        if self.loading: self.notify("Analysis already running.", severity="warning"); return
        await asyncio.sleep(0.01); self.run_status = "Running All Benchmarks..."
        try:
            # Create args object from UI state
            args_obj = ArgsNamespace(
                data_dir=DATA_DIR,
                results_dir=RESULTS_DIR,
                species=self.selected_species,
                model=self.selected_model,
                reasoning_level=self.selected_depth,
                bench_file=BENCHMARKS_FILE
                # scenarios_file is not needed by run_benchmarks
            )
            if not all([args_obj.species, args_obj.model, args_obj.reasoning_level]):
                raise ValueError("Species, Model, and Depth must be selected.")

            configured_logger.info(f"Delegating 'run all benchmarks' for {args_obj.species}, {args_obj.model}, {args_obj.reasoning_level} to thread...") # Use configured_logger

            # Run the backend function in a thread
            # run_benchmarks is synchronous but runs async logic internally
            saved_output_file = await asyncio.to_thread(run_benchmarks, cli_args=args_obj)

            self.run_status = "Completed Benchmarks Run"
            if saved_output_file:
                 self.notify(f"All Benchmarks run complete.\nResults saved to {os.path.basename(saved_output_file)}.\nSee Results Browser.", title="Success", timeout=8)
            else:
                 self.notify("Benchmarks run finished, but failed to save results. Check logs.", title="Warning", severity="warning", timeout=8)

            # Refresh results browser
            try:
                 browser_view = self.query_one(ResultsBrowserView)
                 browser_view._populate_file_list()
            except Exception as browse_e:
                 self.log.warning(f"Could not refresh browser list after running benchmarks: {browse_e}") # Use self.log

        except ImportError as e:
             self.run_status = f"Error: Import failed ({e})"
             self.notify(f"Import Error: {e}", severity="error")
             configured_logger.error(f"Import Error in action_run_benchmarks: {e}\n{traceback.format_exc()}") # Use configured_logger
        except ValueError as e:
             self.run_status = f"Error: Config ({e})"
             self.notify(f"Config Error: {e}", severity="error")
             configured_logger.error(f"Config Error in action_run_benchmarks: {e}") # Use configured_logger
        except Exception as e:
             self.run_status = f"Error: {e}"
             self.notify(f"Runtime Error: {e}", severity="error")
             configured_logger.error(f"Runtime Error in action_run_benchmarks: {e}\n{traceback.format_exc()}") # Use configured_logger
    # --- End Refactored Actions ---


    # --- Event Handlers ---
    def on_select_changed(self, event: Select.Changed) -> None:
        """Handles changes in any Select widget."""
        select_id = event.select.id; new_value = event.value
        configured_logger.debug(f"on_select_changed triggered by '{select_id}' with value '{new_value}'") # Use configured_logger
        if new_value is Select.BLANK:
             if select_id == "task-item-select": self.selected_task_item = None; configured_logger.info("Task item cleared.") # Use configured_logger
             return # Ignore blank selections otherwise

        if select_id == "species-select": self.selected_species = new_value; configured_logger.info(f"Species selection changed to: {new_value}") # Use configured_logger
        elif select_id == "model-select": self.selected_model = new_value; configured_logger.info(f"Model selection changed to: {new_value}") # Use configured_logger
        elif select_id == "task-type-select":
            configured_logger.debug(f"Processing task-type-select change to: '{new_value}'. Current type: '{self.selected_task_type}'") # Use configured_logger
            if self.selected_task_type != new_value:
                self.selected_task_type = new_value; configured_logger.info(f"Task type state updated to: {self.selected_task_type}") # Use configured_logger
                self._update_initial_task_item() # Update default item ID
                # Update the options in the Task Item Select widget
                try:
                    config_view = self.query_one(RunConfigurationView)
                    task_item_select = config_view.query_one("#task-item-select", Select)
                    new_options = config_view._get_task_item_options(self.selected_task_type)
                    configured_logger.debug(f"Generated new options for Task Item Select: {new_options}") # Use configured_logger
                    task_item_select.set_options(new_options)
                    new_default_id = self.selected_task_item if self.selected_task_item is not None else Select.BLANK
                    task_item_select.value = new_default_id
                    configured_logger.info(f"Task item dropdown options updated for '{self.selected_task_type}'. Value set to: '{task_item_select.value}'") # Use configured_logger
                    task_item_select.refresh()
                except Exception as e: configured_logger.error(f"Error updating task item select from app: {e}", exc_info=True) # Use configured_logger
            else: configured_logger.debug("Task type selected is the same as current type, no update needed.") # Use configured_logger
        elif select_id == "task-item-select":
             self.selected_task_item = new_value # Store the ID
             configured_logger.info(f"Task item selection changed to ID: {new_value}") # Use configured_logger
        else: configured_logger.warning(f"Unhandled Select change event from ID: {select_id}") # Use configured_logger

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handles changes in the reasoning depth RadioSet."""
        if event.radio_set.id == "depth-radioset" and event.pressed is not None:
            new_depth = event.pressed.label.plain; self.selected_depth = new_depth
            configured_logger.info(f"Depth selection changed to: {new_depth}") # Use configured_logger
        else: configured_logger.warning(f"Unhandled RadioSet change event from ID: {event.radio_set.id}") # Use configured_logger

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handles button presses."""
        if event.button.id == "run-analysis-button":
            if not self.selected_species or not self.selected_model or not self.selected_depth: self.notify("Please select Species, Model, and Depth.", severity="warning"); return
            if not self.selected_task_item: self.notify("Please select a Task Item.", severity="warning"); return
            asyncio.create_task(self.action_run_analysis())
        elif event.button.id == "run-scenarios-button":
             if not self.selected_species or not self.selected_model or not self.selected_depth: self.notify("Please select Species, Model, and Depth.", severity="warning"); return
             asyncio.create_task(self.action_run_scenarios())
        elif event.button.id == "run-benchmarks-button":
             if not self.selected_species or not self.selected_model or not self.selected_depth: self.notify("Please select Species, Model, and Depth.", severity="warning"); return
             asyncio.create_task(self.action_run_benchmarks())
        elif event.button.id == "run-full-set-button":
             if not self.selected_species or not self.selected_model or not self.selected_depth: self.notify("Please select Species, Model, and Depth.", severity="warning"); return
             asyncio.create_task(self.action_run_full_set())
    # --- End Event Handlers ---


# Main execution guard
if __name__ == "__main__":
    # Basic check for essential data files
    essential_files = [SCENARIOS_FILE, GOLDEN_PATTERNS_FILE, SPECIES_FILE, BENCHMARKS_FILE]
    missing_files = [f for f in essential_files if not f.exists()]
    if missing_files: print(f"Warning: Essential data files missing in '{DATA_DIR}/': {[f.name for f in missing_files]}")
    # Ensure results directory exists
    try: RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e: print(f"Error creating results directory {RESULTS_DIR}: {e}")

    EthicsEngineApp().run()
