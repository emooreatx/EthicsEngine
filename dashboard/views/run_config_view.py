 # EthicsEngine/dashboard/views/run_config_view.py
"""
Provides the main view for configuring and initiating agent runs in the dashboard.

Includes dropdowns for selecting species, model, task type, and specific task items,
radio buttons for reasoning depth, buttons to queue single items or batch runs,
and displays the task queue itself.
"""
import json
import logging
from pathlib import Path
# --- Textual Imports ---
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal, VerticalScroll
from textual.widgets import (
    Label, Button, Static, Select, RadioSet, RadioButton, ListView
)
from textual.reactive import reactive
from textual.markup import escape

# --- Project Imports ---
# Import helpers - use fallback if dashboard_utils isn't found
try:
    from ..dashboard_utils import load_json as load_json_util
except ImportError:
    # Fallback logger and dummy function if utils are unavailable
    logger = logging.getLogger("RunConfigView_Fallback")
    logger.warning("Could not import dashboard_utils. Using basic json loader.")
    def load_json_util(path, default=None):
        if default is None: default = {}
        try:
            with open(path, 'r') as f: return json.load(f)
        except Exception as e:
            logger.error(f"Fallback load_json failed for {path}: {e}")
            return {"Error": f"Fallback load failed: {e}", "_load_error": True}

# Import benchmark file path constant (or fallback)
try:
    from ..dashboard_utils import BENCHMARKS_FILE
except ImportError:
    BENCHMARKS_FILE = Path("data") / "simple_bench_public.json"

# --- View Class ---
class RunConfigurationView(Static):
    """
    A Textual view widget for configuring agent run parameters and managing the task queue.

    Displays controls for selecting species, reasoning model, depth, task type, and
    specific task items. Provides buttons to queue single or batch runs. Also includes
    the task queue display and controls (Start/Clear).
    """

    # Use the application's configured logger if available
    log = logging.getLogger("RunConfigurationView")
    try:
        from config.config import logger as config_logger
        log = config_logger
    except ImportError: pass # Use basic logger defined above if config fails

    def __init__(self, species: dict, models: dict, depth_options: list, task_types: list, scenarios: list | dict, benchmarks: dict, current_species: str | None, current_model: str | None, current_depth: str, current_task_type: str, current_task_item: str | None, **kwargs):
        """
        Initializes the RunConfigurationView.

        Args:
            species: Dictionary of available species.
            models: Dictionary of available reasoning models (golden patterns).
            depth_options: List of available reasoning depth strings.
            task_types: List of available task type strings (e.g., "Ethical Scenarios").
            scenarios: List or error dict containing scenario data.
            benchmarks: Dictionary containing benchmark data structure.
            current_species: The initially selected species.
            current_model: The initially selected model.
            current_depth: The initially selected reasoning depth.
            current_task_type: The initially selected task type.
            current_task_item: The initially selected task item ID.
            **kwargs: Additional arguments for the Static widget.
        """
        super().__init__(**kwargs)
        # Store data needed for select options
        self.species_options = list(species.keys()) if isinstance(species, dict) and "Error" not in species else []
        self.model_options = list(models.keys()) if isinstance(models, dict) and "Error" not in models else []
        self.depth_options = depth_options
        self.task_types = task_types
        # Store full data structures for populating the task item dropdown
        self.scenarios = scenarios
        self.benchmarks_data_struct = benchmarks
        # Store initial values passed from the app to set widget defaults
        self._initial_species = current_species
        self._initial_model = current_model
        self._initial_depth = current_depth
        self._initial_task_type = current_task_type
        self._initial_task_item = current_task_item

    def compose(self) -> ComposeResult:
        """Compose the UI elements for the run configuration and queue view."""
        # Main horizontal layout: Config on left, Queue on right
        with Horizontal(id="run-config-horizontal"):
            # --- Main Config Area (Left Side) ---
            with Vertical(id="main-config-area"):
                # --- Configuration Selectors ---
                yield Label("Species:")
                yield Select(options=[(s, s) for s in self.species_options], value=self._initial_species, id="species-select", allow_blank=False, prompt="Select Species" if not self._initial_species else None)

                yield Label("Reasoning Type (Model):")
                yield Select(options=[(m, m) for m in self.model_options], value=self._initial_model, id="model-select", allow_blank=False, prompt="Select Model" if not self._initial_model else None)

                yield Label("Reasoning Depth:")
                # Ensure initial depth is valid, otherwise default to first option
                initial_depth_value = self._initial_depth if self._initial_depth in self.depth_options else self.depth_options[0]
                yield RadioSet(*[RadioButton(d, id=d, value=(d == initial_depth_value)) for d in self.depth_options], id="depth-radioset")

                yield Label("Task Type:")
                yield Select(options=[(t, t) for t in self.task_types], value=self._initial_task_type, id="task-type-select", allow_blank=False)

                yield Label("Task Item:")
                # Generate initial options for the task item dropdown based on the initial task type
                initial_options = self._get_task_item_options(self._initial_task_type)
                # Ensure the initial item ID is valid for the generated options
                valid_initial_item = self._initial_task_item if any(opt[1] == self._initial_task_item for opt in initial_options) else None
                yield Select(options=initial_options, value=valid_initial_item, id="task-item-select", allow_blank=False, prompt="Select Item" if not valid_initial_item else None)
                # --- End Configuration Selectors ---

                # --- Action Buttons ---
                with Horizontal(classes="button-group"):
                    yield Button("Queue Single Item", id="run-analysis-button", variant="primary", classes="run-button")
                    yield Button("Queue Scenarios", id="run-scenarios-button", variant="success", classes="run-button")
                    yield Button("Queue Benchmarks", id="run-benchmarks-button", variant="success", classes="run-button")
                # --- End Buttons ---

            # --- Task Queue Area (Right Side) ---
            with VerticalScroll(id="run-queue-frame"):
                yield Label("Task Queue", id="queue-title")
                yield ListView(id="queue-list") # Displays the list of queued tasks
                yield Button("Start Queue", id="start-queue-button", variant="success", disabled=True) # Initially disabled
                yield Button("Clear Queue", id="clear-queue-button", variant="error", disabled=False)
            # --- End Queue Frame ---
        # --- End Horizontal Layout ---

    def _truncate_prompt(self, text: str, length: int = 40) -> str:
        """Helper to shorten long strings (like prompts) for display in dropdowns."""
        text = str(text).replace('\n', ' ').strip() # Remove newlines and strip whitespace
        if len(text) > length:
            return text[:length] + "..." # Add ellipsis if truncated
        return text

    def _get_task_item_options(self, task_type_to_use: str) -> list[tuple[str, str]]:
        """
        Generates the list of options for the 'Task Item' Select widget
        based on the currently selected 'Task Type'.

        Args:
            task_type_to_use: The currently selected task type string
                              (e.g., "Ethical Scenarios", "Benchmarks").

        Returns:
            A list of tuples, where each tuple is (display_label, item_id_value).
        """
        self.log.debug(f"View._get_task_item_options called with task_type: '{task_type_to_use}'")
        scenarios_data = self.scenarios
        benchmarks_data = self.benchmarks_data_struct
        options = [] # Initialize empty options list

        if task_type_to_use == "Ethical Scenarios":
            self.log.debug(f"Generating options for Ethical Scenarios. Data type: {type(scenarios_data)}")
            # Handle scenarios (expected to be a list of dicts)
            if isinstance(scenarios_data, list):
                if not scenarios_data:
                     self.log.warning("Scenarios list is empty.")
                     options = [("No Scenarios Found", "")] # Placeholder if empty
                else:
                     temp_options = []
                     # Create options from the list of scenario dicts
                     for index, item in enumerate(scenarios_data):
                          if isinstance(item, dict) and "id" in item:
                               scenario_id = item.get("id")
                               # Use ID as both label and value for simplicity
                               label = str(scenario_id)
                               value = str(scenario_id)
                               temp_options.append((label, value))
                          else:
                               # Log warning for items with unexpected format
                               self.log.warning(f"Skipping invalid scenario item format at index {index}: {item}")
                     options = temp_options if temp_options else [("No Valid Scenarios", "")]
            elif isinstance(scenarios_data, dict) and ("Error" in scenarios_data or "_load_error" in scenarios_data):
                 # Handle case where initial loading failed
                 error_msg = scenarios_data.get("Error", "Load Error")
                 self.log.error(f"Error loading scenarios data: {error_msg}")
                 options = [(f"Error Loading Scenarios: {escape(error_msg)}", "")]
            else:
                 # Handle unexpected data format
                 self.log.error(f"Invalid Scenario Data Format: Expected list, got {type(scenarios_data)}")
                 options = [("Invalid Scenario Data Format", "")]

        elif task_type_to_use == "Benchmarks":
            self.log.debug(f"Generating options for Benchmarks. Data type: {type(benchmarks_data)}")
            # Handle benchmarks (expected structure: dict with 'eval_data' list)
            if isinstance(benchmarks_data, dict) and "eval_data" in benchmarks_data and isinstance(benchmarks_data["eval_data"], list):
                benchmark_items = benchmarks_data["eval_data"]
                self.log.debug(f"Found {len(benchmark_items)} benchmark items in eval_data.")
                temp_options = []
                # Create options from the list of benchmark dicts
                for index, item in enumerate(benchmark_items):
                     if isinstance(item, dict) and "question_id" in item and "prompt" in item:
                          qid = item["question_id"]
                          prompt_snippet = self._truncate_prompt(item["prompt"])
                          # Use QID and prompt snippet for label, QID for value
                          label = f"QID {qid}: {prompt_snippet}"
                          value = str(qid)
                          temp_options.append((label, value))
                     else:
                          # Log warning for items with unexpected format
                          self.log.warning(f"Skipping invalid benchmark item format at index {index}: {item}")
                if not temp_options:
                    self.log.warning("No valid benchmark items found.")
                    options = [("No Valid Benchmarks Found", "")]
                else:
                    options = temp_options
            else:
                # Handle benchmark load errors or incorrect structure
                error_msg = benchmarks_data.get("Error", "Unknown Benchmark Load Error") if isinstance(benchmarks_data, dict) else "Invalid Benchmark Data Structure"
                self.log.error(f"Error loading/parsing benchmark data structure: {error_msg}")
                options = [(f"Error: {escape(error_msg)}", "")]

        self.log.debug(f"View._get_task_item_options returning {len(options)} options.")
        return options
