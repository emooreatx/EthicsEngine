# dashboard/interactive_dashboard.py
"""
The main Textual application class for the EthicsEngine interactive dashboard.

Sets up the UI layout with tabs for different functions (Run Config, Data Mgmt,
Results Browser, Log Viewer, Configuration Editor), manages application state
(like selected parameters, task queue), handles user interactions (button presses,
select changes), and orchestrates the execution of backend tasks via the
TaskQueueManager.
"""
import sys
import os

# Prevent direct execution if run as a module (e.g., python -m dashboard.interactive_dashboard)
if __name__ == "__main__" and sys.argv[0].endswith('__main__.py'):
    print("Error: Please run the application using 'python ethicsengine.py' from the project root directory.")
    sys.exit(1)

# --- Standard Library Imports ---
import json
import asyncio
import traceback
from pathlib import Path
import functools
from datetime import datetime
import argparse # Needed to create the namespace object for run functions
import uuid # For generating unique task IDs

# --- Textual Imports ---
from textual.app import App, ComposeResult
from textual.containers import Container, VerticalScroll, Horizontal, Vertical
from textual.widgets import (
    Header, Footer, Button, Static, Select, Label, Markdown,
    LoadingIndicator, TabbedContent, TabPane, RadioSet, RadioButton,
    ListView, ListItem
)
from textual.binding import Binding
from textual.reactive import reactive
from textual.markup import escape # For safely displaying text in the UI

# --- Project Imports ---
# Import Views (UI components for each tab)
try:
    from dashboard.views import (
        RunConfigurationView,
        DataManagementView,
        ResultsBrowserView,
        LogView,
        ConfigEditorView,
    )
except ImportError as e:
     # Log fatal error if views cannot be imported
     print(f"Fatal Error: Could not import dashboard views: {e}")
     import logging; logging.basicConfig(level=logging.ERROR); logging.error(f"Fatal Error: Import views: {e}", exc_info=True); exit()

# Import Utilities and Constants
try:
    from dashboard.dashboard_utils import (
        load_json, save_json, SCENARIOS_FILE, GOLDEN_PATTERNS_FILE, SPECIES_FILE,
        BENCHMARKS_FILE, DATA_DIR, RESULTS_DIR, ArgsNamespace
    )
except ImportError as e:
     # Log fatal error if utils cannot be imported
     print(f"Fatal Error: Could not import dashboard utils: {e}")
     import logging; logging.basicConfig(level=logging.ERROR); logging.error(f"Fatal Error: Import utils: {e}", exc_info=True); exit()

# Import Configured Logger, Semaphore, and LLM Config
# These are expected to be available from the main entry point setup
from config.config import llm_config, logger as configured_logger, semaphore, SEMAPHORE_CAPACITY

# Import Backend Run Logic (Scenario and Benchmark execution)
try:
    from dashboard.run_scenario_pipelines import run_all_scenarios_async, run_and_save_single_scenario
    from dashboard.run_benchmarks import run_benchmarks_async, run_and_save_single_benchmark, load_benchmarks
except ImportError as e:
    # Log fatal error and define dummy functions if run logic fails to import
    configured_logger.error(f"FATAL: Failed to import run logic modules: {e}", exc_info=True)
    print(f"FATAL ERROR: Could not import run logic: {e}. Check logs and Python path.")
    # Dummy functions to prevent crashes if imports fail
    def run_all_scenarios_async(*args, **kwargs): print("ERROR: run_all_scenarios_async not available!"); return None
    def run_and_save_single_scenario(*args, **kwargs): print("ERROR: run_and_save_single_scenario not available!"); return None
    def run_benchmarks_async(*args, **kwargs): print("ERROR: run_benchmarks_async not available!"); return None
    def run_and_save_single_benchmark(*args, **kwargs): print("ERROR: run_and_save_single_benchmark not available!"); return None
    def load_benchmarks(*args, **kwargs): print("ERROR: load_benchmarks not available!"); return []

# Import the Task Queue Manager
from .task_queue_manager import TaskQueueManager
# Import load_settings function to reload config when saved
from config.config import load_settings as reload_app_settings
# Import the message type from the view and the 'on' decorator
from .views.config_editor_view import ConfigEditorView
from textual import on

# --- Constants ---
REASONING_DEPTH_OPTIONS = ["low", "medium", "high"] # Available reasoning levels
TASK_TYPE_OPTIONS = ["Ethical Scenarios", "Benchmarks"] # Available task types for single runs

# --- Main Application Class ---
class EthicsEngineApp(App):
    """The main Textual application for the Ethics Engine Dashboard."""

    CSS_PATH = "dashboard.tcss" # Path to the CSS file relative to this file's directory
    # Key bindings for quitting the application
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit (Ctrl+C)"),
    ]

    # --- Reactive Properties ---
    # These properties automatically trigger UI updates when their values change.
    run_status = reactive("Ready") # Overall status message displayed in the status bar
    semaphore_status = reactive(f"Concurrency: 0/{SEMAPHORE_CAPACITY}") # Display semaphore usage
    selected_species = reactive(None) # Currently selected species from dropdown
    selected_model = reactive(None) # Currently selected reasoning model
    selected_depth = reactive(REASONING_DEPTH_OPTIONS[0]) # Current reasoning depth
    selected_task_type = reactive(TASK_TYPE_OPTIONS[0]) # Current task type (Scenarios/Benchmarks)
    selected_task_item = reactive(None) # ID of the specific scenario/benchmark selected
    loading = reactive(False) # Tracks if the *queue* is running (controls loading indicator)
    task_queue = reactive(list[dict]) # The list of tasks waiting to be executed
    is_queue_processing = reactive(False) # Flag to prevent multiple queue runs concurrently

    def __init__(self):
        """Initializes the application, loads data, and sets up the task manager."""
        try:
            configured_logger.debug("App.__init__: START")
        except NameError: # Fallback if logger isn't imported yet
            print("App.__init__: START (Logger not ready)")
        super().__init__()
        configured_logger.debug("App.__init__: super().__init__() finished")
        # Instantiate the manager responsible for handling the task queue
        self.task_queue_manager = TaskQueueManager(self)
        configured_logger.debug("App.__init__: TaskQueueManager instantiated")

        # --- Load Initial Data & Settings ---
        # Load settings from config.py (which already loaded from file)
        # We need to access the 'settings' dictionary created in config.py
        # A cleaner way might be to have load_settings return the dict and store it here.
        # For now, let's assume config.settings holds the loaded dict.
        # NOTE: This relies on the import `from config.config import settings` if we want to access it directly.
        # Let's import it explicitly for clarity, although it might already be implicitly available via other imports.
        try:
            from config.config import settings as loaded_initial_settings
            self.app_settings = loaded_initial_settings # Store settings on the app instance
            configured_logger.info("Stored initial settings in self.app_settings")
        except ImportError:
            configured_logger.error("Could not import 'settings' from config.config to store on app instance!")
            self.app_settings = {} # Initialize as empty dict on error

        # Load scenarios, handling potential errors or incorrect formats
        configured_logger.debug("App.__init__: Loading scenarios...")
        self.scenarios = load_json(SCENARIOS_FILE, []) # Expect a list
        if isinstance(self.scenarios, dict) and "Error" in self.scenarios:
             configured_logger.error(f"Failed to load scenarios: {self.scenarios['Error']}")
             self.scenarios = [{"id": "LOAD_ERROR", "prompt": f"Error: {self.scenarios['Error']}"}] # Placeholder on error
        elif not isinstance(self.scenarios, list):
             configured_logger.error(f"Scenarios file {SCENARIOS_FILE} is not a list. Content: {self.scenarios}")
             self.scenarios = [{"id": "FORMAT_ERROR", "prompt": "Error: scenarios.json is not a list."}] # Placeholder on format error
        configured_logger.debug("App.__init__: Scenarios loaded.")

        # Load reasoning models (golden patterns)
        configured_logger.debug("App.__init__: Loading models...")
        self.models = load_json(GOLDEN_PATTERNS_FILE, {"Error": "Could not load models"})
        if "Error" in self.models: configured_logger.error(f"Failed to load models: {self.models['Error']}")
        configured_logger.debug("App.__init__: Models loaded.")

        # Load species data
        configured_logger.debug("App.__init__: Loading species...")
        self.species = load_json(SPECIES_FILE, {"Error": "Could not load species"})
        if "Error" in self.species: configured_logger.error(f"Failed to load species: {self.species['Error']}")
        configured_logger.debug("App.__init__: Species loaded.")

        # Load benchmark data structure
        configured_logger.debug("App.__init__: Loading benchmarks...")
        self.benchmarks_data_struct = load_json(BENCHMARKS_FILE, {"Error": "Could not load benchmarks"})
        if "Error" in self.benchmarks_data_struct: configured_logger.error(f"Failed to load benchmarks: {self.benchmarks_data_struct['Error']}")
        configured_logger.debug("App.__init__: Benchmarks loaded.")

        # --- Set Initial Selections ---
        # Set default species and model (e.g., "Neutral", "Agentic") if available
        configured_logger.debug("App.__init__: Setting initial selections...")
        if isinstance(self.species, dict) and "Error" not in self.species:
            self.selected_species = "Neutral" if "Neutral" in self.species else next(iter(self.species), None)
            configured_logger.info(f"Default species set to: {self.selected_species}")
        else:
            self.selected_species = None
            configured_logger.warning("Could not set default species due to load error or empty data.")

        if isinstance(self.models, dict) and "Error" not in self.models:
            self.selected_model = "Agentic" if "Agentic" in self.models else next(iter(self.models), None)
            configured_logger.info(f"Default model/pattern set to: {self.selected_model}")
        else:
            self.selected_model = None
            configured_logger.warning("Could not set default model/pattern due to load error or empty data.")

        # Set the initial task item based on the default task type
        configured_logger.debug("App.__init__: Calling _update_initial_task_item...")
        self._update_initial_task_item()

        # Update semaphore status display initially using the stored settings
        self.update_semaphore_status()

        configured_logger.debug("App.__init__: FINISHED")

    def _update_initial_task_item(self):
        """Sets the initial selected task item ID based on the current task type."""
        configured_logger.debug(f"_update_initial_task_item running for Task Type: '{self.selected_task_type}'")
        default_item_id = None
        # Determine the first available ID based on the selected task type
        if self.selected_task_type == "Ethical Scenarios":
            if isinstance(self.scenarios, list) and self.scenarios:
                 first_scenario = self.scenarios[0]
                 if isinstance(first_scenario, dict):
                      default_item_id = first_scenario.get("id")
                      configured_logger.debug(f"Found default scenario ID: {default_item_id}")
                 else: configured_logger.warning("First scenario item invalid format.")
            else: configured_logger.warning("Scenarios data not loaded, empty, or not a list.")
        elif self.selected_task_type == "Benchmarks":
            # Benchmarks are nested under 'eval_data' key
            if isinstance(self.benchmarks_data_struct, dict) and "eval_data" in self.benchmarks_data_struct:
                 eval_list = self.benchmarks_data_struct["eval_data"]
                 if isinstance(eval_list, list) and eval_list:
                      first_item = eval_list[0]
                      if isinstance(first_item, dict) and "question_id" in first_item:
                           default_item_id = str(first_item["question_id"]) # Use question_id for benchmarks
                           configured_logger.debug(f"Found default benchmark QID: {default_item_id}")
                      else: configured_logger.warning("First benchmark item invalid format.")
                 else: configured_logger.warning("Benchmark eval_data not a non-empty list.")
            else: configured_logger.warning("Benchmark data structure invalid or missing 'eval_data'.")

        # Update the reactive property for the selected task item
        self.selected_task_item = default_item_id
        configured_logger.info(f"Default Task Item ID set to: {self.selected_task_item} for Task Type: {self.selected_task_type}")

    def compose(self) -> ComposeResult:
        """Compose the application's UI structure."""
        yield Header(show_clock=True) # Standard Textual header

        # Status Bar at the top
        with Horizontal(id="status-bar"):
            yield Static("Status: Ready", id="run-status") # Displays current app status
            yield Static(f" Concurrency: 0/{SEMAPHORE_CAPACITY}", id="semaphore-status-display") # Shows semaphore usage
            yield LoadingIndicator(id="loading-indicator") # Shows when tasks are running

        # Main layout with tabs on the left
        with Horizontal(id="main-layout"):
            with Vertical(id="main-content"): # Container for the main tabbed content
                with TabbedContent(id="main-tabs", initial="tab-run"): # Start on the "Run" tab
                    # Define each tab pane and its content view
                    with TabPane("Agent Run", id="tab-run"):
                        # Pass necessary data and initial state to the RunConfigurationView
                        yield RunConfigurationView(
                            species=self.species, models=self.models,
                            depth_options=REASONING_DEPTH_OPTIONS, task_types=TASK_TYPE_OPTIONS,
                            scenarios=self.scenarios, benchmarks=self.benchmarks_data_struct,
                            current_species=self.selected_species, current_model=self.selected_model,
                            current_depth=self.selected_depth, current_task_type=self.selected_task_type,
                            current_task_item=self.selected_task_item,
                            id="run-configuration-view" # Assign ID for querying
                        )
                    with TabPane("Data Management", id="tab-data"):
                        yield DataManagementView(scenarios=self.scenarios, models=self.models, species_data=self.species, id="data-management-view")
                    with TabPane("Results Browser", id="tab-results-browser"):
                        yield ResultsBrowserView(id="results-browser-view")
                    with TabPane("Log Viewer", id="tab-log"):
                        yield LogView(id="log-view")
                    with TabPane("Configuration", id="tab-config"):
                        yield ConfigEditorView(id="config-editor-view")

            # Note: The Task Queue view is now part of RunConfigurationView's layout

        yield Footer() # Standard Textual footer with key bindings

    def on_mount(self) -> None:
        """Called after the app is mounted."""
        configured_logger.info("EthicsEngineApp Mounted")
        # Hide loading indicator initially
        self.query_one("#loading-indicator").display = False
        # Start polling semaphore status periodically
        self.set_interval(1.0, self.update_semaphore_status)
        configured_logger.info("Started UI semaphore status polling.")

    def update_semaphore_status(self) -> None:
        """Periodically checks the TrackedSemaphore status and updates the UI."""
        try:
             # Check if semaphore has the expected tracking attributes
             if hasattr(semaphore, 'active_count'):
                  active = semaphore.active_count
                  # Read capacity from the stored app_settings dictionary
                  capacity = self.app_settings.get("concurrency", 'N/A') # Use 'N/A' if key missing
                  # Update the reactive property, which triggers the watcher
                  self.semaphore_status = f" Concurrency: {active}/{capacity}"
             else:
                  # Handle cases where the semaphore might not be the tracked version
                 self.semaphore_status = " Concurrency: N/A (Error)"
                 configured_logger.warning("Global semaphore object is not a TrackedSemaphore instance.")
        except Exception as e:
                 # Log errors during status update
                 self.semaphore_status = " Concurrency: Error"
                 configured_logger.error(f"Error updating semaphore status: {e}", exc_info=True)

    # --- Watchers for Reactive Properties ---
    # These methods are automatically called when the corresponding reactive property changes.

    def watch_run_status(self, status: str) -> None:
        """Updates the status bar when run_status changes."""
        try:
            status_widget = self.query_one("#run-status", Static)
            status_widget.update(f"Status: {status}")
        except Exception as e:
            # Use self.log (available in App) for safer logging if widget query fails
            self.log.warning(f"Could not update #run-status widget in watch_run_status: {e}")

    def watch_semaphore_status(self, status: str) -> None:
        """Updates the status bar when semaphore_status changes."""
        try:
            sema_widget = self.query_one("#semaphore-status-display", Static)
            sema_widget.update(status)
        except Exception as e:
            self.log.warning(f"Could not update #semaphore-status-display widget in watch_semaphore_status: {e}")

    def watch_loading(self, loading: bool) -> None:
        """Shows/hides loading indicator and disables/enables run buttons."""
        # Update loading indicator visibility
        try:
            indicator = self.query_one("#loading-indicator")
            indicator.display = loading
        except Exception as e:
            self.log.warning(f"Could not update #loading-indicator in watch_loading: {e}")

        # Disable/enable various run/queue buttons based on loading state
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

        # Queue buttons also depend on queue content and processing state
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
        """Updates the queue ListView display when the task_queue reactive list changes."""
        try:
            # Find the ListView widget for the queue
            queue_list_view = self.query_one("#queue-list", ListView)
            current_index = queue_list_view.index # Preserve scroll position if possible
            queue_list_view.clear() # Clear existing items

            # Re-populate the list view based on the new queue content
            for i, task in enumerate(new_queue):
                # Create a descriptive label for the task item
                task_desc = f"[{i+1}/{len(new_queue)}] {task.get('type', 'Unknown')}: "
                task_type = task.get('task_type', '?') # Scenario or Benchmark for single runs
                item_id = task.get('item_id', '?')
                species = task.get('species', 'N/A')
                model = task.get('model', 'N/A')
                depth = task.get('depth', 'N/A')
                status = task.get('status', 'Pending') # Get task status

                # Format description based on task type
                if task.get('type') == 'single':
                    task_desc += f"{task_type} ID: {item_id}"
                elif task.get('type') == 'all_scenarios':
                    task_desc += "All Scenarios"
                elif task.get('type') == 'all_benchmarks':
                    task_desc += "All Benchmarks"
                else:
                    task_desc += "Invalid Task"

                task_desc += f" (S:{species}, M:{model}, D:{depth})"
                task_desc += f" - {status}" # Append status

                # Replace brackets before escaping to avoid potential MarkupError
                safe_task_desc = task_desc.replace('[', '(').replace(']', ')')
                # Create a ListItem containing a Static widget with the escaped description
                item = ListItem(Static(escape(safe_task_desc)))
                item.task_data = task # Store original task data on the item
                item.task_id = task.get('id') # Store unique task ID
                # Apply CSS classes based on status for styling
                if status == 'Running': item.set_classes("running")
                elif status == 'Completed': item.set_classes("completed")
                elif status == 'Error': item.set_classes("error")
                elif status == 'Warning': item.set_classes("warning")
                else: item.set_classes("pending") # Default/Pending

                queue_list_view.append(item)

            # Restore scroll position if valid
            if current_index is not None and current_index < len(new_queue):
                queue_list_view.index = current_index
            elif len(new_queue) > 0:
                 queue_list_view.index = 0 # Scroll to top if index invalid

            # Enable/disable Start Queue button based on queue content and processing state
            start_button = self.query_one("#start-queue-button", Button)
            start_button.disabled = not new_queue or self.is_queue_processing or self.loading

            self.log.debug("Queue ListView updated.")
        except Exception as e:
            # Use self.log for safer logging during potential UI updates
            self.log.error(f"Error updating #queue-list view in watch_task_queue: {e}", exc_info=True)


    # --- Event Handlers ---

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handles changes in any Select widget (Species, Model, Task Type, Task Item)."""
        select_id = event.select.id; new_value = event.value
        configured_logger.debug(f"on_select_changed triggered by '{select_id}' with value '{new_value}'")

        # Ignore blank selections (usually occurs temporarily when options change)
        if new_value is Select.BLANK:
             if select_id == "task-item-select": self.selected_task_item = None; configured_logger.info("Task item cleared.")
             return

        # Update corresponding reactive property based on the Select widget's ID
        if select_id == "species-select": self.selected_species = new_value; configured_logger.info(f"Species selection changed to: {new_value}")
        elif select_id == "model-select": self.selected_model = new_value; configured_logger.info(f"Model selection changed to: {new_value}")
        elif select_id == "task-type-select":
            configured_logger.debug(f"Processing task-type-select change to: '{new_value}'. Current type: '{self.selected_task_type}'")
            # If the task type actually changed...
            if self.selected_task_type != new_value:
                self.selected_task_type = new_value # Update the state
                configured_logger.info(f"Task type state updated to: {self.selected_task_type}")
                self._update_initial_task_item() # Update the default item ID for the new type
                # Update the options in the Task Item Select dropdown
                try:
                    config_view = self.query_one(RunConfigurationView) # Get the view containing the dropdown
                    task_item_select = config_view.query_one("#task-item-select", Select)
                    # Get new options based on the selected task type
                    new_options = config_view._get_task_item_options(self.selected_task_type)
                    configured_logger.debug(f"Generated new options for Task Item Select: {new_options}")
                    task_item_select.set_options(new_options) # Update dropdown options
                    # Set the dropdown value to the new default ID (or blank if none)
                    new_default_id = self.selected_task_item if self.selected_task_item is not None else Select.BLANK
                    task_item_select.value = new_default_id
                    configured_logger.info(f"Task item dropdown options updated for '{self.selected_task_type}'. Value set to: '{task_item_select.value}'")
                    task_item_select.refresh() # Ensure UI updates
                except Exception as e: configured_logger.error(f"Error updating task item select from app: {e}", exc_info=True)
            else: configured_logger.debug("Task type selected is the same as current type, no update needed.")
        elif select_id == "task-item-select":
             self.selected_task_item = new_value # Store the selected item ID
             configured_logger.info(f"Task item selection changed to ID: {new_value}")
        else: configured_logger.warning(f"Unhandled Select change event from ID: {select_id}")

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handles changes in the reasoning depth RadioSet."""
        if event.radio_set.id == "depth-radioset" and event.pressed is not None:
            # Update the selected depth based on the pressed radio button's label
            new_depth = event.pressed.label.plain; self.selected_depth = new_depth
            configured_logger.info(f"Depth selection changed to: {new_depth}")
        else: configured_logger.warning(f"Unhandled RadioSet change event from ID: {event.radio_set.id}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handles button presses - Adds tasks to the queue or controls the queue."""
        button_id = event.button.id

        # --- Queue Control Buttons ---
        if button_id == "start-queue-button":
            # Delegate starting the queue to the TaskQueueManager
            asyncio.create_task(self.task_queue_manager.action_start_queue())
            return
        if button_id == "clear-queue-button":
            # Delegate clearing the queue to the TaskQueueManager
            self.task_queue_manager.action_clear_queue()
            return

        # --- Task Adding Buttons ---
        # Common validation: Ensure species, model, and depth are selected
        if not self.selected_species or not self.selected_model or not self.selected_depth:
            self.notify("Please select Species, Model, and Depth before adding tasks.", severity="warning")
            return

        # Prepare base arguments object needed by the run functions
        args_obj = ArgsNamespace(
            data_dir=DATA_DIR, results_dir=RESULTS_DIR,
            species=self.selected_species, model=self.selected_model,
            reasoning_level=self.selected_depth,
            bench_file=BENCHMARKS_FILE, scenarios_file=SCENARIOS_FILE
        )
        task_id = str(uuid.uuid4()) # Generate a unique ID for the task

        # --- Add Single Task (Scenario or Benchmark) ---
        if button_id == "run-analysis-button":
            # Validate that task type and item are selected
            if not self.selected_task_type or self.selected_task_item is None:
                self.notify("Please select a Task Type and Task Item.", severity="warning")
                return

            # Find the dictionary for the selected item (scenario or benchmark)
            selected_item_dict = None
            item_id_to_find = self.selected_task_item
            current_task_type = self.selected_task_type

            try:
                if current_task_type == "Ethical Scenarios":
                    if isinstance(self.scenarios, list):
                        # Find the scenario dict in the list by its 'id'
                        selected_item_dict = next((item for item in self.scenarios if isinstance(item, dict) and item.get("id") == item_id_to_find), None)
                    if not selected_item_dict:
                        raise ValueError(f"Scenario ID '{item_id_to_find}' not found.")
                elif current_task_type == "Benchmarks":
                    # Load benchmark data and find the item by 'question_id'
                    benchmarks_data = load_benchmarks(args_obj.bench_file) # This is synchronous
                    target_benchmarks = benchmarks_data if isinstance(benchmarks_data, list) else []
                    if not target_benchmarks:
                        raise ValueError("No benchmark data found or loaded.")
                    selected_item_dict = next((item for item in target_benchmarks if isinstance(item, dict) and str(item.get("question_id")) == item_id_to_find), None)
                    if not selected_item_dict:
                        raise ValueError(f"Benchmark QID '{item_id_to_find}' not found.")
                else:
                    raise ValueError(f"Invalid task type selected: {current_task_type}")

                # Create the task dictionary to add to the queue
                task = {
                    "id": task_id,
                    "type": "single", # Indicates a single item run
                    "task_type": current_task_type, # "Ethical Scenarios" or "Benchmarks"
                    "item_id": item_id_to_find,
                    "species": self.selected_species,
                    "model": self.selected_model,
                    "depth": self.selected_depth,
                    "args": args_obj, # Pass the prepared arguments
                    "item_dict": selected_item_dict, # Pass the actual scenario/benchmark data
                    "status": "Pending" # Initial status
                }
                # Delegate adding the task to the manager
                self.task_queue_manager.add_task_to_queue(task)
                self.notify(f"Added '{current_task_type}' task (ID: {item_id_to_find}) to queue.", title="Task Queued")
                # Logging is handled within add_task_to_queue

            except ValueError as e: # Handle errors finding the item
                self.notify(f"Error preparing task: {e}", severity="error")
                configured_logger.error(f"Error preparing single task for queue: {e}")
            except Exception as e: # Catch unexpected errors
                 self.notify(f"Unexpected error preparing task: {e}", severity="error")
                 configured_logger.error(f"Unexpected error preparing single task: {e}", exc_info=True)


        # --- Add All Scenarios Task ---
        elif button_id == "run-scenarios-button":
            task = {
                "id": task_id,
                "type": "all_scenarios", # Indicates running all scenarios
                "species": self.selected_species,
                "model": self.selected_model,
                "depth": self.selected_depth,
                "args": args_obj,
                "item_dict": None, # Not applicable for bulk runs
                "status": "Pending"
            }
            self.task_queue_manager.add_task_to_queue(task)
            self.notify("Added 'Run All Scenarios' task to queue.", title="Task Queued")

        # --- Add All Benchmarks Task ---
        elif button_id == "run-benchmarks-button":
            task = {
                "id": task_id,
                "type": "all_benchmarks", # Indicates running all benchmarks
                "species": self.selected_species,
                "model": self.selected_model,
                "depth": self.selected_depth,
                "args": args_obj,
                "item_dict": None, # Not applicable for bulk runs
                "status": "Pending"
            }
            self.task_queue_manager.add_task_to_queue(task)
            self.notify("Added 'Run All Benchmarks' task to queue.", title="Task Queued")

    # --- Custom Message Handlers ---
    @on(ConfigEditorView.SettingsSaved)
    def handle_settings_saved(self, message: ConfigEditorView.SettingsSaved) -> None:
        """Handles the message sent when settings are saved in the ConfigEditorView."""
        configured_logger.info("Received SettingsSaved message. Reloading settings...")
        try:
            # Reload settings from the file using the imported function
            self.app_settings = reload_app_settings()
            configured_logger.info("Application settings reloaded into self.app_settings.")
            # Immediately update the status bar display
            self.update_semaphore_status()
            self.notify("Settings reloaded successfully.", title="Settings Updated")
            # TODO: Potentially apply other settings dynamically if needed (e.g., log level)
        except Exception as e:
            configured_logger.error(f"Failed to reload settings after save: {e}", exc_info=True)
            self.notify(f"Error reloading settings: {e}", severity="error", title="Update Failed")
