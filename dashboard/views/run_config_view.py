# EthicsEngine/dashboard/views/run_config_view.py
import json
import logging
from pathlib import Path
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import (
    Label,
    Button,
    Static,
    Select,
    RadioSet,
    RadioButton,
)
from textual.reactive import reactive
from textual.markup import escape

# Import helpers - use fallback if dashboard_utils isn't found
try:
    from ..dashboard_utils import load_json as load_json_util
except ImportError:
    logger = logging.getLogger("RunConfigView_Fallback")
    logger.warning("Could not import dashboard_utils. Using basic json loader.")
    def load_json_util(path, default=None):
        if default is None: default = {}
        try:
            with open(path, 'r') as f: return json.load(f)
        except Exception as e:
            logger.error(f"Fallback load_json failed for {path}: {e}")
            return {"Error": f"Fallback load failed: {e}", "_load_error": True}

# Assuming BENCHMARKS_FILE is defined appropriately
try:
    from ..dashboard_utils import BENCHMARKS_FILE
except ImportError:
    BENCHMARKS_FILE = Path("data") / "simple_bench_public.json"

class RunConfigurationView(Static):
    """View for configuring simulation runs."""

    log = logging.getLogger("RunConfigurationView")
    try:
        # Try to use the main app logger if available
        from config.config import logger as config_logger
        log = config_logger
    except ImportError: pass # Use basic logger defined above

    def __init__(self, species: dict, models: dict, depth_options: list, task_types: list, scenarios: list | dict, benchmarks: dict, current_species: str | None, current_model: str | None, current_depth: str, current_task_type: str, current_task_item: str | None, **kwargs):
        super().__init__(**kwargs)
        # Store data needed for options
        self.species_options = list(species.keys()) if isinstance(species, dict) and "Error" not in species else []
        self.model_options = list(models.keys()) if isinstance(models, dict) and "Error" not in models else []
        self.depth_options = depth_options
        self.task_types = task_types
        # Store scenarios (now expected as a list or error dict)
        self.scenarios = scenarios
        self.benchmarks_data_struct = benchmarks
        # Store initial values for composing widgets
        self._initial_species = current_species
        self._initial_model = current_model
        self._initial_depth = current_depth
        self._initial_task_type = current_task_type
        self._initial_task_item = current_task_item

    def compose(self) -> ComposeResult:
        with Vertical(id="run-config-vertical"):
            # --- Configuration Selectors ---
            yield Label("Species:")
            yield Select(options=[(s, s) for s in self.species_options], value=self._initial_species, id="species-select", allow_blank=False, prompt="Select Species" if not self._initial_species else None)
            yield Label("Reasoning Type (Model):")
            yield Select(options=[(m, m) for m in self.model_options], value=self._initial_model, id="model-select", allow_blank=False, prompt="Select Model" if not self._initial_model else None)
            yield Label("Reasoning Depth:")
            initial_depth_value = self._initial_depth if self._initial_depth in self.depth_options else self.depth_options[0]
            yield RadioSet(*[RadioButton(d, id=d, value=(d == initial_depth_value)) for d in self.depth_options], id="depth-radioset")
            yield Label("Task Type:")
            yield Select(options=[(t, t) for t in self.task_types], value=self._initial_task_type, id="task-type-select", allow_blank=False)
            yield Label("Task Item:")
            # Generate initial options based on the initial task type
            initial_options = self._get_task_item_options(self._initial_task_type)
            # Make sure initial_task_item is valid for initial_options
            valid_initial_item = self._initial_task_item if any(opt[1] == self._initial_task_item for opt in initial_options) else None
            yield Select(options=initial_options, value=valid_initial_item, id="task-item-select", allow_blank=False, prompt="Select Item" if not valid_initial_item else None)
            # --- End Configuration Selectors ---

            # --- Buttons ---
            with Horizontal(classes="button-group"):
                 yield Button("Run Single Item", id="run-analysis-button", variant="primary", classes="run-button")
                 yield Button("Run Scenarios", id="run-scenarios-button", variant="success", classes="run-button") # New
                 yield Button("Run Benchmarks", id="run-benchmarks-button", variant="success", classes="run-button") # New
                 yield Button("Run Full Set", id="run-full-set-button", variant="warning", classes="run-button")
            # --- End Buttons ---

            # --- Status Displays ---
            status_text = f"Status: Ready"
            # Check if app exists before accessing status, fallback if not
            if hasattr(self, 'app') and self.app: status_text = f"Status: {self.app.run_status}"
            yield Static(status_text, id="run-status")
            # Display semaphore status (updated by the main app)
            yield Static("Concurrency: N/A", id="semaphore-status-display", classes="text-muted")
            # --- End Status Displays ---

    def _truncate_prompt(self, text, length=40):
        # Helper to shorten long prompts for display
        text = str(text).replace('\n', ' ').strip()
        if len(text) > length: return text[:length] + "..."
        return text

    def _get_task_item_options(self, task_type_to_use):
        """Gets options for the Task Item dropdown based on the given Task Type."""
        self.log.debug(f"View._get_task_item_options called with task_type: '{task_type_to_use}'")
        # Use the scenarios list stored in the view instance
        scenarios_data = self.scenarios
        benchmarks_data = self.benchmarks_data_struct
        options = []

        if task_type_to_use == "Ethical Scenarios":
            self.log.debug(f"Generating options for Ethical Scenarios. Data type: {type(scenarios_data)}")
            # --- MODIFIED: Handle scenarios as a list of objects ---
            if isinstance(scenarios_data, list):
                if not scenarios_data:
                     self.log.warning("Scenarios list is empty.")
                     options = [("No Scenarios Found", "")]
                else:
                     temp_options = []
                     for index, item in enumerate(scenarios_data):
                          if isinstance(item, dict) and "id" in item:
                               scenario_id = item.get("id")
                               # Use ID for both label and value for simplicity, or add prompt snippet
                               # label = f"{scenario_id}: {self._truncate_prompt(item.get('prompt', ''))}"
                               label = str(scenario_id) # Keep label simple for now
                               value = str(scenario_id)
                               temp_options.append((label, value))
                          else:
                               self.log.warning(f"Skipping invalid scenario item format at index {index}: {item}")
                     options = temp_options if temp_options else [("No Valid Scenarios", "")]
            # --- END MODIFIED ---
            elif isinstance(scenarios_data, dict) and ("Error" in scenarios_data or "_load_error" in scenarios_data):
                 # Handle load error case
                 error_msg = scenarios_data.get("Error", "Load Error")
                 self.log.error(f"Error loading scenarios data: {error_msg}")
                 options = [(f"Error Loading Scenarios: {escape(error_msg)}", "")]
            else:
                 # Handle unexpected format
                 self.log.error(f"Invalid Scenario Data Format: Expected list, got {type(scenarios_data)}")
                 options = [("Invalid Scenario Data Format", "")]

        elif task_type_to_use == "Benchmarks":
            # Benchmark logic remains the same as it already expected a list within the structure
            self.log.debug(f"Generating options for Benchmarks. Data type: {type(benchmarks_data)}")
            if isinstance(benchmarks_data, dict) and "eval_data" in benchmarks_data and isinstance(benchmarks_data["eval_data"], list):
                benchmark_items = benchmarks_data["eval_data"]
                self.log.debug(f"Found {len(benchmark_items)} benchmark items in eval_data.")
                temp_options = []
                for index, item in enumerate(benchmark_items):
                     if isinstance(item, dict) and "question_id" in item and "prompt" in item:
                          qid = item["question_id"]; prompt_snippet = self._truncate_prompt(item["prompt"])
                          label = f"QID {qid}: {prompt_snippet}"; value = str(qid)
                          temp_options.append((label, value))
                     else: self.log.warning(f"Skipping invalid benchmark item format at index {index}: {item}")
                if not temp_options: self.log.warning("No valid benchmark items found."); options = [("No Valid Benchmarks Found", "")]
                else: options = temp_options
            else:
                error_msg = benchmarks_data.get("Error", "Unknown Benchmark Load Error") if isinstance(benchmarks_data, dict) else "Invalid Benchmark Data Structure"
                self.log.error(f"Error loading/parsing benchmark data structure: {error_msg}")
                options = [(f"Error: {error_msg}", "")]
        self.log.debug(f"View._get_task_item_options returning {len(options)} options.")
        return options
