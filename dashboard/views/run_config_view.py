# EthicsEngine/dashboard/views/run_config_view.py
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

class RunConfigurationView(Static):
    """View for configuring simulation runs."""

    # Data is passed from the app via __init__
    def __init__(self, species: dict, models: dict, depth_options: list, task_types: list, scenarios: dict, benchmarks: dict, current_species: str | None, current_model: str | None, current_depth: str, current_task_type: str, current_task_item: str | None, **kwargs):
        super().__init__(**kwargs)
        self.species_options = list(species.keys()) if isinstance(species, dict) and "Error" not in species else []
        self.model_options = list(models.keys()) if isinstance(models, dict) and "Error" not in models else []
        self.depth_options = depth_options
        self.task_types = task_types
        # Store data needed for populating dropdowns
        self.scenarios = scenarios if isinstance(scenarios, dict) and "Error" not in scenarios else {}
        self.benchmarks = benchmarks # Keep for _get_task_item_options if needed
        # Store initial values passed from app for composing widgets
        self._initial_species = current_species
        self._initial_model = current_model
        self._initial_depth = current_depth
        self._initial_task_type = current_task_type
        self._initial_task_item = current_task_item

    def compose(self) -> ComposeResult:
        with Vertical(id="run-config-vertical"):
            # --- Configuration Selectors ---
            # Use initial values for widgets
            yield Label("Species:")
            yield Select(options=[(s, s) for s in self.species_options], value=self._initial_species, id="species-select", allow_blank=False, prompt="Select Species" if not self._initial_species else None)
            yield Label("Reasoning Type (Model):")
            yield Select(options=[(m, m) for m in self.model_options], value=self._initial_model, id="model-select", allow_blank=False, prompt="Select Model" if not self._initial_model else None)
            yield Label("Reasoning Depth:")
            yield RadioSet(*[RadioButton(d, id=d, value=(d == self._initial_depth)) for d in self.depth_options], id="depth-radioset")
            yield Label("Task Type:")
            yield Select(options=[(t, t) for t in self.task_types], value=self._initial_task_type, id="task-type-select", allow_blank=False)
            yield Label("Task Item:")
            # Get options based on the initial task type passed in
            initial_options = self._get_task_item_options(self._initial_task_type)
            yield Select(options=initial_options, value=self._initial_task_item, id="task-item-select", allow_blank=False, prompt="Select Item" if not self._initial_task_item else None)

            # --- Action Buttons ---
            with Horizontal(classes="button-group"):
                 yield Button("Run Analysis", id="run-analysis-button", variant="primary", classes="run-button")
                 yield Button("Run Full Set", id="run-full-set-button", variant="warning", classes="run-button")

            # --- Status Display ---
            status_text = f"Status: {self.app.run_status}" if hasattr(self, 'app') else "Status: Initializing"
            yield Static(status_text, id="run-status")

    # Modify _get_task_item_options to accept task_type as argument
    def _get_task_item_options(self, task_type_to_use):
        """Gets options for the Task Item dropdown based on the given Task Type."""
        scenarios_data = self.scenarios if hasattr(self, 'scenarios') else {}

        if task_type_to_use == "Ethical Scenarios":
             if isinstance(scenarios_data, dict):
                  # Ensure scenarios_data is not the error dict
                  if "Error" not in scenarios_data and "_load_error" not in scenarios_data:
                      return [(s_id, s_id) for s_id in scenarios_data.keys()]
                  else:
                      return [("Error Loading Scenarios", "")] # Indicate error
        elif task_type_to_use == "Benchmarks":
            return [("All Benchmarks", "All")]
        return [] # Return empty list for unknown type or error state


    def on_select_changed(self, event: Select.Changed) -> None:
        """Called by the parent App when a Select widget changes."""
        if not hasattr(self, 'app'): return
        app = self.app
        select_id = event.select.id
        new_value = event.value
        if new_value is Select.BLANK: return

        if select_id == "species-select": app.handle_species_change(new_value)
        elif select_id == "model-select": app.handle_model_change(new_value)
        elif select_id == "task-type-select":
            app.handle_task_type_change(new_value) # App handles state and UI updates
        elif select_id == "task-item-select": app.handle_task_item_change(new_value)

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Called by the parent App when a RadioSet changes."""
        if not hasattr(self, 'app'): return
        if event.radio_set.id == "depth-radioset" and event.pressed is not None:
             new_depth = event.pressed.label.plain
             self.app.handle_depth_change(new_depth)