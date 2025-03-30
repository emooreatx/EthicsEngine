# dashboard/interactive_dashboard.py
import os
import json
import asyncio
import traceback
from pathlib import Path
import functools
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Container, VerticalScroll, Horizontal, Vertical
from textual.widgets import Header, Footer, Button, Static, Select, Label, Markdown, LoadingIndicator, TabbedContent, TabPane, RadioSet, RadioButton
from textual.binding import Binding
from textual.reactive import reactive
from textual.message import Message

# --- Import Views ---
try:
    from dashboard.views import (
        RunConfigurationView,
        DataManagementView,
        ResultsBrowserView,
        LogView,
    )
except ImportError as e:
     print(f"Fatal Error: Could not import dashboard views: {e}")
     import logging; logging.basicConfig(level=logging.ERROR); logging.error(f"Fatal Error: Import views: {e}", exc_info=True); exit()

# --- Import Utils ---
try:
    from dashboard.dashboard_utils import (load_json, save_json, SCENARIOS_FILE, GOLDEN_PATTERNS_FILE, SPECIES_FILE, BENCHMARKS_FILE, DATA_DIR, RESULTS_DIR)
except ImportError as e:
     print(f"Fatal Error: Could not import dashboard utils: {e}")
     import logging; logging.basicConfig(level=logging.ERROR); logging.error(f"Fatal Error: Import utils: {e}", exc_info=True); exit()

# --- Import Full Run Logic ---
try:
    from dashboard.dashboard_full_run import run_full_set
except ImportError as e:
    print(f"Warning: Could not import full run logic: {e}")
    def run_full_set(*args, **kwargs):
        print("ERROR: run_full_set function not available!")
        return None, None

# --- Import Backend Logic & Config ---
# Import semaphore for UI status updates
from config.config import llm_config, logger as file_logger, semaphore, SEMAPHORE_CAPACITY
# --- END ADDED ---

# Constants and Helper Class
REASONING_DEPTH_OPTIONS = ["low", "medium", "high"]
TASK_TYPE_OPTIONS = ["Ethical Scenarios", "Benchmarks"]

class ArgsNamespace:
    # Helper class to mimic argparse Namespace for backend functions
    def __init__(self, data_dir, results_dir, species, model, reasoning_level, bench_file=None, scenarios_file=None):
        self.data_dir = str(data_dir); self.results_dir = str(results_dir); self.species = species; self.model = model; self.reasoning_level = reasoning_level; self.bench_file = str(bench_file) if bench_file else None; self.scenarios_file = str(scenarios_file) if scenarios_file else None

# --- Main App ---
class EthicsEngineApp(App):
    CSS_PATH = "dashboard.tcss"
    BINDINGS = [ Binding("q", "quit", "Quit"), ]

    # --- Reactive Properties ---
    run_status = reactive("Ready")
    semaphore_status = reactive(f"Concurrency: 0/{SEMAPHORE_CAPACITY}")
    selected_species = reactive(None)
    selected_model = reactive(None)
    selected_depth = reactive(REASONING_DEPTH_OPTIONS[0])
    selected_task_type = reactive(TASK_TYPE_OPTIONS[0])
    selected_task_item = reactive(None) # This will hold the ID of the selected item
    loading = reactive(False)
    # --- End Reactive Properties ---

    def __init__(self):
        super().__init__()
        # Load initial data (scenarios should now be a list)
        self.scenarios = load_json(SCENARIOS_FILE, []) # Default to empty list
        if isinstance(self.scenarios, dict) and "Error" in self.scenarios:
             file_logger.error(f"Failed to load scenarios: {self.scenarios['Error']}")
             self.scenarios = [{"id": "LOAD_ERROR", "prompt": f"Error: {self.scenarios['Error']}"}] # Provide dummy for UI
        elif not isinstance(self.scenarios, list):
             file_logger.error(f"Scenarios file {SCENARIOS_FILE} is not a list. Content: {self.scenarios}")
             self.scenarios = [{"id": "FORMAT_ERROR", "prompt": "Error: scenarios.json is not a list."}] # Provide dummy

        self.models = load_json(GOLDEN_PATTERNS_FILE, {"Error": "Could not load models"})
        if "Error" in self.models: file_logger.error(f"Failed to load models: {self.models['Error']}")
        self.species = load_json(SPECIES_FILE, {"Error": "Could not load species"})
        if "Error" in self.species: file_logger.error(f"Failed to load species: {self.species['Error']}")
        self.benchmarks_data_struct = load_json(BENCHMARKS_FILE, {"Error": "Could not load benchmarks"})
        if "Error" in self.benchmarks_data_struct: file_logger.error(f"Failed to load benchmarks: {self.benchmarks_data_struct['Error']}")

        # Set initial selections
        if isinstance(self.species, dict) and "Error" not in self.species: self.selected_species = next(iter(self.species), None)
        if isinstance(self.models, dict) and "Error" not in self.models: self.selected_model = next(iter(self.models), None)
        self._update_initial_task_item() # Set initial task item based on type

    def _update_initial_task_item(self):
        """Sets the initial selected task item ID based on the current task type."""
        self.log.debug(f"_update_initial_task_item running for Task Type: '{self.selected_task_type}'")
        default_item_id = None
        if self.selected_task_type == "Ethical Scenarios":
            # --- MODIFIED: Get ID from first item in list ---
            if isinstance(self.scenarios, list) and self.scenarios:
                 first_scenario = self.scenarios[0]
                 if isinstance(first_scenario, dict):
                      default_item_id = first_scenario.get("id")
                      self.log.debug(f"Found default scenario ID: {default_item_id}")
                 else: self.log.warning("First scenario item invalid format.")
            else: self.log.warning("Scenarios data not loaded, empty, or not a list.")
            # --- END MODIFIED ---
        elif self.selected_task_type == "Benchmarks":
            # Benchmark logic remains the same
            if isinstance(self.benchmarks_data_struct, dict) and "eval_data" in self.benchmarks_data_struct:
                 eval_list = self.benchmarks_data_struct["eval_data"]
                 if isinstance(eval_list, list) and eval_list:
                      first_item = eval_list[0]
                      if isinstance(first_item, dict) and "question_id" in first_item:
                           default_item_id = str(first_item["question_id"])
                           self.log.debug(f"Found default benchmark QID: {default_item_id}")
                      else: self.log.warning("First benchmark item invalid format.")
                 else: self.log.warning("Benchmark eval_data not a non-empty list.")
            else: self.log.warning("Benchmark data structure invalid.")

        self.selected_task_item = default_item_id # Store the ID
        self.log.info(f"Default Task Item ID set to: {self.selected_task_item} for Task Type: {self.selected_task_type}")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="loading-layer-container"): yield LoadingIndicator(id="loading-indicator")
        with TabbedContent(id="main-tabs", initial="tab-run"):
            with TabPane("Agent Run", id="tab-run"):
                 # Pass initial state and data (including scenario list) to the view
                 yield RunConfigurationView(
                     species=self.species, models=self.models,
                     depth_options=REASONING_DEPTH_OPTIONS, task_types=TASK_TYPE_OPTIONS,
                     scenarios=self.scenarios, benchmarks=self.benchmarks_data_struct,
                     current_species=self.selected_species, current_model=self.selected_model,
                     current_depth=self.selected_depth, current_task_type=self.selected_task_type,
                     current_task_item=self.selected_task_item, # Pass the selected ID
                     id="run-configuration-view"
                 )
            # Pass scenario list to DataManagementView as well
            with TabPane("Data Management", id="tab-data"): yield DataManagementView(scenarios=self.scenarios, models=self.models, species_data=self.species, id="data-management-view")
            with TabPane("Results Browser", id="tab-results-browser"): yield ResultsBrowserView(id="results-browser-view")
            with TabPane("Log Viewer", id="tab-log"): yield LogView(id="log-view")
        yield Footer()

    def on_mount(self) -> None:
        self.log("EthicsEngineApp Mounted")
        self.query_one("#loading-indicator").display = False
        # Start semaphore status polling
        self.set_interval(1.0, self.update_semaphore_status)
        self.log.info("Started UI semaphore status polling.")

    def update_semaphore_status(self) -> None:
        """Periodically checks the semaphore status and updates the reactive variable."""
        try:
            if hasattr(semaphore, 'active_count') and hasattr(semaphore, 'capacity'):
                 active = semaphore.active_count
                 capacity = semaphore.capacity
                 self.semaphore_status = f"Concurrency: {active}/{capacity}"
            else:
                 self.semaphore_status = "Concurrency: N/A (Error)"
                 self.log.warning("Global semaphore object is not a TrackedSemaphore instance.")
        except Exception as e:
             self.semaphore_status = "Concurrency: Error"
             self.log.error(f"Error updating semaphore status: {e}", exc_info=True)

    # --- Watchers for Reactive Variables ---
    def watch_run_status(self, status: str) -> None:
        self.loading = ("Running" in status)
        try:
            config_view = self.query_one(RunConfigurationView)
            status_widget = config_view.query_one("#run-status", Static)
            status_widget.update(f"Status: {status}")
        except Exception as e:
            self.log.warning(f"Could not find #run-status widget: {e}")

    def watch_semaphore_status(self, status: str) -> None:
        """Updates the UI when the semaphore_status reactive variable changes."""
        try:
            config_view = self.query_one(RunConfigurationView)
            sema_widget = config_view.query_one("#semaphore-status-display", Static)
            sema_widget.update(status)
        except Exception as e:
            self.log.warning(f"Could not find #semaphore-status-display widget: {e}")

    def watch_loading(self, loading: bool) -> None:
        try:
            indicator = self.query_one("#loading-indicator"); indicator.display = loading
            config_view = self.query_one(RunConfigurationView)
            run_button = config_view.query_one("#run-analysis-button", Button); full_run_button = config_view.query_one("#run-full-set-button", Button)
            run_button.disabled = loading; full_run_button.disabled = loading
        except Exception as e:
            self.log.warning(f"Could not update loading indicator/buttons: {e}")
    # --- End Watchers ---


    # --- Actions ---
    async def action_run_analysis(self):
        """Runs analysis for a single selected task item."""
        if self.loading: self.notify("Analysis already running.", severity="warning"); return
        await asyncio.sleep(0.01); self.run_status = "Running Single Item..."
        saved_output_file = None
        try:
            # Import backend functions dynamically
            from run_scenario_pipelines import run_pipeline_for_scenario
            from run_benchmarks import run_benchmarks_async, load_benchmarks, run_item
            from reasoning_agent import EthicsAgent

            # Validate selections
            args_obj = ArgsNamespace(data_dir=DATA_DIR, results_dir=RESULTS_DIR, species=self.selected_species, model=self.selected_model, reasoning_level=self.selected_depth, bench_file=BENCHMARKS_FILE, scenarios_file=SCENARIOS_FILE)
            if not all([args_obj.species, args_obj.model, args_obj.reasoning_level]): raise ValueError("Species, Model, and Depth must be selected.")
            if not self.selected_task_type or self.selected_task_item is None: raise ValueError("Task Type and Task Item must be selected.")

            results_list_for_file = None; run_type = "unknown"
            species_full_data = load_json(SPECIES_FILE, {}); models_full_data = load_json(GOLDEN_PATTERNS_FILE, {})
            run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            if self.selected_task_type == "Ethical Scenarios":
                 run_type = "scenario_pipeline";
                 # --- MODIFIED: Find the scenario object by ID ---
                 selected_scenario_dict = None
                 scenario_id_to_find = self.selected_task_item # This holds the ID
                 if isinstance(self.scenarios, list):
                      for scenario in self.scenarios:
                           if isinstance(scenario, dict) and scenario.get("id") == scenario_id_to_find:
                                selected_scenario_dict = scenario
                                self.log.info(f"Found scenario object for ID: {scenario_id_to_find}")
                                break
                 if not selected_scenario_dict:
                      self.log.error(f"Could not find scenario with ID '{scenario_id_to_find}' in the loaded list.")
                      raise ValueError(f"Scenario ID '{scenario_id_to_find}' not found.")
                 # --- END MODIFIED ---

                 # Run the single scenario pipeline in a thread, passing the found dict
                 def run_scenario_sync_wrapper(): return asyncio.run(run_pipeline_for_scenario(selected_scenario_dict, args_obj))
                 single_result_data = await asyncio.to_thread(run_scenario_sync_wrapper)
                 results_list_for_file = [single_result_data] if single_result_data else []

            elif self.selected_task_type == "Benchmarks":
                 # Benchmark logic remains the same
                 run_type = "benchmark";
                 selected_qid_str = self.selected_task_item # This holds the QID string
                 file_logger.info(f"Running single benchmark: QID {selected_qid_str}")
                 benchmarks_data = load_benchmarks(args_obj.bench_file) # load_benchmarks returns the list
                 target_benchmarks = benchmarks_data if isinstance(benchmarks_data, list) else []
                 if not target_benchmarks: raise ValueError("No benchmark data found or loaded.")
                 selected_item_dict = None
                 for item in target_benchmarks:
                      if isinstance(item, dict) and str(item.get("question_id")) == selected_qid_str: selected_item_dict = item; break
                 if not selected_item_dict: raise ValueError(f"Could not find benchmark data for QID: {selected_qid_str}")

                 # Create agent and run the single benchmark item in a thread
                 answer_agent = EthicsAgent(args_obj.species, args_obj.model, args_obj.reasoning_level, args_obj.data_dir)
                 def run_single_bench_sync_wrapper(): return asyncio.run(run_item(selected_item_dict, answer_agent))
                 single_result_data = await asyncio.to_thread(run_single_bench_sync_wrapper)
                 results_list_for_file = [single_result_data] if single_result_data else []
            else: raise ValueError("Invalid task type selected")

            # --- Metadata Generation (Simplified) ---
            species_traits_raw = species_full_data.get(args_obj.species, f"Unknown: {args_obj.species}")
            species_traits = species_traits_raw.split(', ') if isinstance(species_traits_raw, str) else species_traits_raw
            if not isinstance(species_traits, list): species_traits = [str(species_traits)] # Ensure list
            model_description = models_full_data.get(args_obj.model, f"Unknown: {args_obj.model}")
            safe_llm_config = [{"model": cfg.get("model", "N/A")} for cfg in getattr(llm_config, 'config_list', []) if isinstance(cfg, dict)]

            metadata = { "run_timestamp": run_timestamp, "run_type": run_type, "species_name": args_obj.species, "species_traits": species_traits, "reasoning_model": args_obj.model, "model_description": model_description, "reasoning_level": args_obj.reasoning_level, "llm_config": safe_llm_config, "tags": [], "evaluation_criteria": {} }
            # --- End Metadata Generation ---

            output_data_to_save = {"metadata": metadata, "results": results_list_for_file if results_list_for_file is not None else []}

            # --- Save Results ---
            try:
                 results_dir_path = Path(args_obj.results_dir); results_dir_path.mkdir(parents=True, exist_ok=True)
                 # Use the selected item ID (scenario ID or QID) in the filename
                 item_id_suffix = f"_{self.selected_task_item}" if self.selected_task_item else ""
                 # Sanitize item_id_suffix for filename (replace spaces, etc.)
                 safe_item_id_suffix = item_id_suffix.replace(" ", "_").replace("/", "-")
                 file_prefix = "bench_single" if run_type == "benchmark" else "scenario_single"
                 output_file = results_dir_path / f"{file_prefix}{safe_item_id_suffix}_{args_obj.species.lower()}_{args_obj.model.lower()}_{args_obj.reasoning_level.lower()}_{run_timestamp}.json"
                 save_json(output_file, output_data_to_save)
                 saved_output_file = output_file
                 file_logger.info(f"Analysis results saved to {output_file}")
                 # Refresh results browser
                 try: browser_view = self.query_one(ResultsBrowserView); browser_view._populate_file_list()
                 except Exception as browse_e: file_logger.warning(f"Could not refresh browser list: {browse_e}")
            except Exception as save_e: file_logger.error(f"Failed to save analysis results: {save_e}"); self.notify(f"Error saving results: {save_e}", severity="error")
            # --- End Save Results ---

            self.run_status = "Completed";
            if saved_output_file: self.notify(f"Run complete. Results saved.\nSee Results Browser tab.", title="Success", timeout=8)
            else: self.notify("Run finished, but failed to save results.", title="Warning", severity="warning", timeout=8)
        except ImportError as e: self.run_status = f"Error: Import failed ({e})"; self.notify(f"Import Error: {e}", severity="error"); self.log.error(f"Import Error: {e}\n{traceback.format_exc()}")
        except ValueError as e: self.run_status = f"Error: Config ({e})"; self.notify(f"Config Error: {e}", severity="error"); self.log.error(f"Config Error: {e}")
        except Exception as e: self.run_status = f"Error: {e}"; self.notify(f"Runtime Error: {e}", severity="error"); self.log.error(f"Runtime Error: {e}\n{traceback.format_exc()}")


    async def action_run_full_set(self):
        """Runs the full set of benchmarks and scenarios."""
        if self.loading: return
        self.run_status = "Running Full Set..."
        try:
            species=self.selected_species; model=self.selected_model; level=self.selected_depth
            if not all([species, model, level]): raise ValueError("Species, Model, and Depth must be selected.")
            self.log.info(f"Running full set for {species}, {model}, {level} in thread...")
            # Run the backend function in a thread
            saved_files = await asyncio.to_thread(run_full_set, species=species, model=model, reasoning_level=level, data_dir=DATA_DIR, results_dir=RESULTS_DIR, bench_file=BENCHMARKS_FILE, scenarios_file=SCENARIOS_FILE)
            self.run_status = "Full Run Completed"
            if saved_files and len(saved_files) == 2 and all(saved_files):
                 bench_out, scenario_out = saved_files
                 self.notify(f"Full run finished.\nBenchmarks: {os.path.basename(bench_out)}\nScenarios: {os.path.basename(scenario_out)}\nSee Results Browser tab.", title="Success", timeout=10)
            else: self.notify("Full run completed, but issues saving files. Check logs.", severity="warning", title="Completed with Issues", timeout=10)
            # Refresh results browser
            try: browser_view = self.query_one(ResultsBrowserView); browser_view._populate_file_list(); file_logger.info("Results browser list refreshed.")
            except Exception: file_logger.warning("Could not refresh results browser list.")
        except ValueError as e: self.run_status = f"Error: Config ({e})"; self.notify(f"Config Error: {e}", severity="error"); self.log.error(f"Config Error: {e}")
        except Exception as e: self.run_status = f"Error: {e}"; self.notify(f"Runtime Error: {e}", severity="error"); self.log.error(f"Runtime Error: {e}\n{traceback.format_exc()}")
    # --- End Actions ---


    # --- Event Handlers ---
    def on_select_changed(self, event: Select.Changed) -> None:
        """Handles changes in any Select widget."""
        select_id = event.select.id; new_value = event.value
        self.log.debug(f"on_select_changed triggered by '{select_id}' with value '{new_value}'")
        if new_value is Select.BLANK:
             if select_id == "task-item-select": self.selected_task_item = None; self.log.info("Task item cleared.")
             return # Ignore blank selections otherwise

        if select_id == "species-select": self.selected_species = new_value; self.log.info(f"Species selection changed to: {new_value}")
        elif select_id == "model-select": self.selected_model = new_value; self.log.info(f"Model selection changed to: {new_value}")
        elif select_id == "task-type-select":
            self.log.debug(f"Processing task-type-select change to: '{new_value}'. Current type: '{self.selected_task_type}'")
            if self.selected_task_type != new_value:
                self.selected_task_type = new_value; self.log.info(f"Task type state updated to: {self.selected_task_type}")
                self._update_initial_task_item() # Update default item ID for new type
                # Update the options in the Task Item Select widget
                try:
                    config_view = self.query_one(RunConfigurationView)
                    task_item_select = config_view.query_one("#task-item-select", Select)
                    # Get new options using the view's helper method
                    new_options = config_view._get_task_item_options(self.selected_task_type)
                    self.log.debug(f"Generated new options for Task Item Select: {new_options}")
                    task_item_select.set_options(new_options)
                    # Set the value to the new default ID or blank
                    new_default_id = self.selected_task_item if self.selected_task_item is not None else Select.BLANK
                    task_item_select.value = new_default_id
                    self.log.info(f"Task item dropdown options updated for '{self.selected_task_type}'. Value set to: '{task_item_select.value}'")
                    task_item_select.refresh()
                except Exception as e: self.log.error(f"Error updating task item select from app: {e}", exc_info=True)
            else: self.log.debug("Task type selected is the same as current type, no update needed.")
        elif select_id == "task-item-select":
             # The value selected is the scenario ID or benchmark QID
             self.selected_task_item = new_value
             self.log.info(f"Task item selection changed to ID: {new_value}")
        else: self.log.warning(f"Unhandled Select change event from ID: {select_id}")

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handles changes in the reasoning depth RadioSet."""
        if event.radio_set.id == "depth-radioset" and event.pressed is not None:
            new_depth = event.pressed.label.plain; self.selected_depth = new_depth
            self.log.info(f"Depth selection changed to: {new_depth}")
        else: self.log.warning(f"Unhandled RadioSet change event from ID: {event.radio_set.id}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handles button presses."""
        if event.button.id == "run-analysis-button":
            # Basic validation before running
            if not self.selected_species or not self.selected_model or not self.selected_depth: self.notify("Please select Species, Model, and Depth.", severity="warning"); return
            if not self.selected_task_item: self.notify("Please select a Task Item.", severity="warning"); return
            asyncio.create_task(self.action_run_analysis())
        elif event.button.id == "run-full-set-button":
             if not self.selected_species or not self.selected_model or not self.selected_depth: self.notify("Please select Species, Model, and Depth.", severity="warning"); return
             asyncio.create_task(self.action_run_full_set())
    # --- End Event Handlers ---

# --- Main execution guard ---
if __name__ == "__main__":
    # Basic check for essential data files
    essential_files = [SCENARIOS_FILE, GOLDEN_PATTERNS_FILE, SPECIES_FILE, BENCHMARKS_FILE]
    missing_files = [f for f in essential_files if not f.exists()]
    if missing_files: print(f"Warning: Essential data files missing in '{DATA_DIR}/': {[f.name for f in missing_files]}")
    # Ensure results directory exists
    try: RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e: print(f"Error creating results directory {RESULTS_DIR}: {e}")

    EthicsEngineApp().run()
