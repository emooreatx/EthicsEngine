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

import uuid # Import uuid for unique task IDs
from textual.app import App, ComposeResult
from textual.containers import Container, VerticalScroll, Horizontal, Vertical
from textual.widgets import Header, Footer, Button, Static, Select, Label, Markdown, LoadingIndicator, TabbedContent, TabPane, RadioSet, RadioButton, ListView, ListItem
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import ListView, ListItem, Label
from textual.markup import escape # Import escape

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
    from dashboard.dashboard_utils import (load_json, save_json, SCENARIOS_FILE, GOLDEN_PATTERNS_FILE, SPECIES_FILE, BENCHMARKS_FILE, DATA_DIR, RESULTS_DIR, ArgsNamespace)
except ImportError as e:
     print(f"Fatal Error: Could not import dashboard utils: {e}")
     import logging; logging.basicConfig(level=logging.ERROR); logging.error(f"Fatal Error: Import utils: {e}", exc_info=True); exit()

# Import Backend Logic & Config FIRST to ensure logger is available for error handling below
# Import the configured logger instance directly
from config.config import llm_config, logger as configured_logger, semaphore, SEMAPHORE_CAPACITY

# Import Full Run Logic & Specific Run Functions (AFTER logger is imported)
try:
    # Use absolute imports assuming project root is in path
    # from dashboard.dashboard_full_run import run_full_set # Removed import
    from dashboard.run_scenario_pipelines import run_all_scenarios_async, run_and_save_single_scenario # Renamed import
    from dashboard.run_benchmarks import run_benchmarks_async, run_and_save_single_benchmark, load_benchmarks # Renamed import
except ImportError as e:
    # Log the error more visibly if imports fail
    configured_logger.error(f"FATAL: Failed to import run logic modules: {e}", exc_info=True)
    print(f"FATAL ERROR: Could not import run logic: {e}. Check logs and Python path.")
    # Define dummy functions if import fails to prevent crashes
    def run_full_set(*args, **kwargs): print("ERROR: run_full_set not available!"); return None, None
    def run_all_scenarios(*args, **kwargs): print("ERROR: run_all_scenarios not available!"); return None
    def run_and_save_single_scenario(*args, **kwargs): print("ERROR: run_and_save_single_scenario not available!"); return None
    def run_benchmarks(*args, **kwargs): print("ERROR: run_benchmarks not available!"); return None
    def run_and_save_single_benchmark(*args, **kwargs): print("ERROR: run_and_save_single_benchmark not available!"); return None
    def load_benchmarks(*args, **kwargs): print("ERROR: load_benchmarks not available!"); return []

# Import the Task Queue Manager
from .task_queue_manager import TaskQueueManager # Added import

# Constants and Helper Class
REASONING_DEPTH_OPTIONS = ["low", "medium", "high"]
TASK_TYPE_OPTIONS = ["Ethical Scenarios", "Benchmarks"]



class EthicsEngineApp(App):
    CSS_PATH = "dashboard.tcss"
    # Bind both 'q' and 'ctrl+c' to quit
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit (Ctrl+C)"),
    ]

    # Reactive Properties
    run_status = reactive("Ready")
    semaphore_status = reactive(f"Concurrency: 0/{SEMAPHORE_CAPACITY}")
    selected_species = reactive(None)
    selected_model = reactive(None)
    selected_depth = reactive(REASONING_DEPTH_OPTIONS[0])
    selected_task_type = reactive(TASK_TYPE_OPTIONS[0])
    selected_task_item = reactive(None) # Holds the ID of the selected scenario/benchmark
    loading = reactive(False) # Tracks if the *queue* is running
    task_queue = reactive(list[dict])
    is_queue_processing = reactive(False) # Flag to prevent multiple queue runs

    def __init__(self):
        # Ensure logger is available before using it
        try:
            configured_logger.debug("App.__init__: START")
        except NameError: # Fallback if logger isn't imported yet (shouldn't happen here)
            print("App.__init__: START (Logger not ready)")
        super().__init__()
        configured_logger.debug("App.__init__: super().__init__() finished")
        self.task_queue_manager = TaskQueueManager(self) # Instantiate the manager
        configured_logger.debug("App.__init__: TaskQueueManager instantiated")

        # Load initial data
        configured_logger.debug("App.__init__: Loading scenarios...")
        self.scenarios = load_json(SCENARIOS_FILE, [])
        if isinstance(self.scenarios, dict) and "Error" in self.scenarios:
             configured_logger.error(f"Failed to load scenarios: {self.scenarios['Error']}") # Use configured_logger
             self.scenarios = [{"id": "LOAD_ERROR", "prompt": f"Error: {self.scenarios['Error']}"}]
        elif not isinstance(self.scenarios, list):
             configured_logger.error(f"Scenarios file {SCENARIOS_FILE} is not a list. Content: {self.scenarios}") # Use configured_logger
             self.scenarios = [{"id": "FORMAT_ERROR", "prompt": "Error: scenarios.json is not a list."}]
        configured_logger.debug("App.__init__: Scenarios loaded.")

        configured_logger.debug("App.__init__: Loading models...")
        self.models = load_json(GOLDEN_PATTERNS_FILE, {"Error": "Could not load models"})
        if "Error" in self.models: configured_logger.error(f"Failed to load models: {self.models['Error']}") # Use configured_logger
        configured_logger.debug("App.__init__: Models loaded.")

        configured_logger.debug("App.__init__: Loading species...")
        self.species = load_json(SPECIES_FILE, {"Error": "Could not load species"})
        if "Error" in self.species: configured_logger.error(f"Failed to load species: {self.species['Error']}") # Use configured_logger
        configured_logger.debug("App.__init__: Species loaded.")

        configured_logger.debug("App.__init__: Loading benchmarks...")
        self.benchmarks_data_struct = load_json(BENCHMARKS_FILE, {"Error": "Could not load benchmarks"})
        if "Error" in self.benchmarks_data_struct: configured_logger.error(f"Failed to load benchmarks: {self.benchmarks_data_struct['Error']}") # Use configured_logger
        configured_logger.debug("App.__init__: Benchmarks loaded.")

        # Set initial selections (Neutral Species, Agentic Model)
        configured_logger.debug("App.__init__: Setting initial selections...")
        # Default Species to "Neutral" if available, else first
        if isinstance(self.species, dict) and "Error" not in self.species:
            self.selected_species = "Neutral" if "Neutral" in self.species else next(iter(self.species), None)
            configured_logger.info(f"Default species set to: {self.selected_species}")
        else:
            self.selected_species = None
            configured_logger.warning("Could not set default species due to load error or empty data.")

        # Default Model/Pattern to "Agentic" if available, else first
        if isinstance(self.models, dict) and "Error" not in self.models:
            self.selected_model = "Agentic" if "Agentic" in self.models else next(iter(self.models), None)
            configured_logger.info(f"Default model/pattern set to: {self.selected_model}")
        else:
            self.selected_model = None
            configured_logger.warning("Could not set default model/pattern due to load error or empty data.")

        configured_logger.debug("App.__init__: Calling _update_initial_task_item...")
        self._update_initial_task_item()
        configured_logger.debug("App.__init__: FINISHED")

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
        # Restore the intended layout structure with correct indentation (Attempt 3)
        yield Header(show_clock=True)
        with Container(id="loading-layer-container"): # Level 0
            # Level 1
            yield LoadingIndicator(id="loading-indicator")

        # Revert to layout using Horizontal/Vertical with explicit IDs
        with Horizontal(id="main-layout"): # Level 0 - Renamed ID
            # Level 1: Left side
            with Vertical(id="main-content"): # Restore Vertical wrapper - Renamed ID
                # Level 2
                with TabbedContent(id="main-tabs", initial="tab-run"):
                    # Level 3
                    with TabPane("Agent Run", id="tab-run"):
                        # Level 4
                        yield RunConfigurationView(
                            species=self.species, models=self.models,
                            depth_options=REASONING_DEPTH_OPTIONS, task_types=TASK_TYPE_OPTIONS,
                            scenarios=self.scenarios, benchmarks=self.benchmarks_data_struct,
                            current_species=self.selected_species, current_model=self.selected_model, # Removed duplicate arguments from the next line
                            current_depth=self.selected_depth, current_task_type=self.selected_task_type,
                            current_task_item=self.selected_task_item,
                            id="run-configuration-view"
                        )
                    with TabPane("Data Management", id="tab-data"): # Level 3
                        yield DataManagementView(scenarios=self.scenarios, models=self.models, species_data=self.species, id="data-management-view") # Level 4
                    with TabPane("Results Browser", id="tab-results-browser"): # Level 3
                        yield ResultsBrowserView(id="results-browser-view") # Level 4
                    with TabPane("Log Viewer", id="tab-log"): # Level 3
                        yield LogView(id="log-view") # Level 4
                    with TabPane("Configuration", id="tab-config"): # Level 3
                        yield ConfigEditorView(id="config-editor-view") # Level 4

            # Level 1: Right side Queue Pane REMOVED from here.
            # It will be placed inside RunConfigurationView instead.

        # Level 0
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
        # self.loading = ("Running" in status or "Processing" in status) # REMOVED - Loading state managed explicitly
        # Make widget query safer
        try:
            status_widget = self.query_one("#run-status", Static)
            status_widget.update(f"Status: {status}")
        except Exception as e:
            # Use self.log, widget might not exist yet/anymore
            self.log.warning(f"Could not update #run-status widget in watch_run_status: {e}")

    def watch_semaphore_status(self, status: str) -> None:
        """Updates the UI when the semaphore_status reactive variable changes."""
        # Make widget query safer
        try:
            sema_widget = self.query_one("#semaphore-status-display", Static)
            sema_widget.update(status)
        except Exception as e:
            # Use self.log, widget might not exist yet/anymore
            self.log.warning(f"Could not update #semaphore-status-display widget in watch_semaphore_status: {e}")

    def watch_loading(self, loading: bool) -> None:
        # Make widget queries safer with individual try-except blocks
        try:
            indicator = self.query_one("#loading-indicator")
            indicator.display = loading
        except Exception as e:
            self.log.warning(f"Could not update #loading-indicator in watch_loading: {e}")

        try:
            run_button = self.query_one("#run-analysis-button", Button)
            run_button.disabled = loading
        except Exception as e:
            self.log.warning(f"Could not update #run-analysis-button in watch_loading: {e}")

        try:
            scenarios_button = self.query_one("#run-scenarios-button", Button)
            scenarios_button.disabled = loading
        except Exception as e:
            self.log.warning(f"Could not update #run-scenarios-button in watch_loading: {e}")

        try:
            benchmarks_button = self.query_one("#run-benchmarks-button", Button)
            benchmarks_button.disabled = loading
        except Exception as e:
            self.log.warning(f"Could not update #run-benchmarks-button in watch_loading: {e}")

        try:
            start_button = self.query_one("#start-queue-button", Button)
            start_button.disabled = not self.task_queue or loading or self.is_queue_processing
        except Exception as e:
            self.log.warning(f"Could not update #start-queue-button in watch_loading: {e}")

        try:
            clear_button = self.query_one("#clear-queue-button", Button)
            clear_button.disabled = loading or self.is_queue_processing
        except Exception as e:
            self.log.warning(f"Could not update #clear-queue-button in watch_loading: {e}")


    def watch_task_queue(self, old_queue: list, new_queue: list) -> None:
        """Updates the queue ListView when the task_queue reactive changes."""
        # Add robust error handling in case the widget isn't ready
        try:
            # Make widget query safer
            queue_list_view = self.query_one("#queue-list", ListView)
            current_index = queue_list_view.index # Preserve scroll position if possible
            queue_list_view.clear() # Clear existing items
            for i, task in enumerate(new_queue):
                # Create a descriptive label for the task
                task_desc = f"[{i+1}/{len(new_queue)}] {task.get('type', 'Unknown')}: "
                task_type = task.get('task_type', '?') # Scenario or Benchmark for single runs
                item_id = task.get('item_id', '?')
                species = task.get('species', 'N/A')
                model = task.get('model', 'N/A')
                depth = task.get('depth', 'N/A')
                status = task.get('status', 'Pending')

                if task.get('type') == 'single':
                    task_desc += f"{task_type} ID: {item_id}"
                elif task.get('type') == 'all_scenarios':
                    task_desc += "All Scenarios"
                elif task.get('type') == 'all_benchmarks':
                    task_desc += "All Benchmarks"
                else:
                    task_desc += "Invalid Task"

                task_desc += f" (S:{species}, M:{model}, D:{depth})"
                # Add status
                task_desc += f" - {status}"

                # Replace brackets before escaping to avoid MarkupError during layout
                safe_task_desc = task_desc.replace('[', '(').replace(']', ')')
                item = ListItem(Static(escape(safe_task_desc)))
                item.task_data = task # Store original data
                item.task_id = task.get('id') # Store unique ID
                # Apply styling based on status
                if status == 'Running': item.set_classes("running")
                elif status == 'Completed': item.set_classes("completed")
                elif status == 'Error': item.set_classes("error")
                elif status == 'Warning': item.set_classes("warning") # Added warning class
                else: item.set_classes("pending") # Default/Pending

                queue_list_view.append(item)

            # Restore scroll position if valid
            if current_index is not None and current_index < len(new_queue):
                queue_list_view.index = current_index
            elif len(new_queue) > 0:
                 queue_list_view.index = 0 # Scroll to top if index invalid

            # Enable/disable Start button based on queue content and processing state
            start_button = self.query_one("#start-queue-button", Button)
            start_button.disabled = not new_queue or self.is_queue_processing or self.loading

            self.log.debug("Queue ListView updated.") # Use self.log
        except Exception as e:
            # Use self.log which is safer during startup/shutdown
            self.log.error(f"Error updating #queue-list view in watch_task_queue: {e}", exc_info=True)


    # --- Event Handlers ---
    def on_select_changed(self, event: Select.Changed) -> None: # Corrected indentation within this method
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

    def on_button_pressed(self, event: Button.Pressed) -> None: # Corrected indentation and removed await
        """Handles button presses - Now adds tasks to the queue."""
        button_id = event.button.id

        # --- Queue Control Buttons ---
        if button_id == "start-queue-button":
            # Delegate to the manager
            asyncio.create_task(self.task_queue_manager.action_start_queue())
            return
        if button_id == "clear-queue-button":
            # Delegate to the manager
            self.task_queue_manager.action_clear_queue()
            return

        # --- Task Adding Buttons (Delegate task creation to manager) ---
        # Common validation for adding tasks
        if not self.selected_species or not self.selected_model or not self.selected_depth:
            self.notify("Please select Species, Model, and Depth before adding tasks.", severity="warning")
            return

        # Prepare base arguments
        args_obj = ArgsNamespace(
            data_dir=DATA_DIR, results_dir=RESULTS_DIR,
            species=self.selected_species, model=self.selected_model,
            reasoning_level=self.selected_depth,
            bench_file=BENCHMARKS_FILE, scenarios_file=SCENARIOS_FILE
        )
        task_id = str(uuid.uuid4()) # Generate unique ID for the task

        # --- Add Single Task ---
        if button_id == "run-analysis-button":
            if not self.selected_task_type or self.selected_task_item is None:
                self.notify("Please select a Task Type and Task Item.", severity="warning")
                return

            # Find the selected item dictionary (similar logic to original action_run_analysis)
            selected_item_dict = None
            item_id_to_find = self.selected_task_item
            current_task_type = self.selected_task_type

            try:
                if current_task_type == "Ethical Scenarios":
                    if isinstance(self.scenarios, list):
                        selected_item_dict = next((item for item in self.scenarios if isinstance(item, dict) and item.get("id") == item_id_to_find), None)
                    if not selected_item_dict:
                        raise ValueError(f"Scenario ID '{item_id_to_find}' not found.")
                elif current_task_type == "Benchmarks":
                    # Re-verified again: Removed await from load_benchmarks (it's synchronous)
                    benchmarks_data = load_benchmarks(args_obj.bench_file)
                    target_benchmarks = benchmarks_data if isinstance(benchmarks_data, list) else []
                    if not target_benchmarks:
                        raise ValueError("No benchmark data found or loaded.")
                    selected_item_dict = next((item for item in target_benchmarks if isinstance(item, dict) and str(item.get("question_id")) == item_id_to_find), None)
                    if not selected_item_dict:
                        raise ValueError(f"Benchmark QID '{item_id_to_find}' not found.")
                else:
                    raise ValueError(f"Invalid task type selected: {current_task_type}")

                # Create task dictionary
                task = {
                    "id": task_id,
                    "type": "single",
                    "task_type": current_task_type, # "Ethical Scenarios" or "Benchmarks"
                    "item_id": item_id_to_find,
                    "species": self.selected_species,
                    "model": self.selected_model,
                    "depth": self.selected_depth,
                    "args": args_obj,
                    "item_dict": selected_item_dict, # The actual scenario/benchmark data
                    "status": "Pending"
                }
                # Delegate adding to the manager
                self.task_queue_manager.add_task_to_queue(task)
                self.notify(f"Added '{current_task_type}' task (ID: {item_id_to_find}) to queue.", title="Task Queued")
                # Logging is handled within add_task_to_queue

            except ValueError as e:
                self.notify(f"Error preparing task: {e}", severity="error")
                configured_logger.error(f"Error preparing single task for queue: {e}")
            except Exception as e:
                 self.notify(f"Unexpected error preparing task: {e}", severity="error")
                 configured_logger.error(f"Unexpected error preparing single task: {e}", exc_info=True)


        # --- Add All Scenarios Task ---
        elif button_id == "run-scenarios-button":
            task = {
                "id": task_id,
                "type": "all_scenarios",
                "species": self.selected_species,
                "model": self.selected_model,
                "depth": self.selected_depth,
                "args": args_obj,
                "item_dict": None, # Not applicable for bulk runs
                "status": "Pending"
            }
            # Delegate adding to the manager
            self.task_queue_manager.add_task_to_queue(task)
            self.notify("Added 'Run All Scenarios' task to queue.", title="Task Queued")
            # Logging is handled within add_task_to_queue

        # --- Add All Benchmarks Task ---
        elif button_id == "run-benchmarks-button":
            task = {
                "id": task_id,
                "type": "all_benchmarks",
                "species": self.selected_species,
                "model": self.selected_model,
                "depth": self.selected_depth,
                "args": args_obj,
                "item_dict": None, # Not applicable for bulk runs
                "status": "Pending"
            }
            # Delegate adding to the manager
            self.task_queue_manager.add_task_to_queue(task)
            self.notify("Added 'Run All Benchmarks' task to queue.", title="Task Queued")
            # Logging is handled within add_task_to_queue

    # --- End Event Handlers ---
