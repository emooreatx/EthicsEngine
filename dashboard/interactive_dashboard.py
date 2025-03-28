# dashboard/interactive_dashboard.py
import os
import json
import asyncio
import traceback # Import traceback for better error reporting
from pathlib import Path
import functools # Import functools for passing arguments to thread

from textual.app import App, ComposeResult
# Added Container back for RunViewContainer
from textual.containers import Container, VerticalScroll, Horizontal, Vertical
from textual.widgets import Header, Footer, Button, Static, Select, Label, Markdown, LoadingIndicator, TabbedContent, TabPane # Added TabbedContent, TabPane
from textual.binding import Binding
from textual.reactive import reactive

# Import views and utils
# Ensure these files exist and are in the Python path
try:
    from dashboard.dashboard_views import (
        RunConfigurationView,
        ResultsView,
        DataManagementView,
        ResultsBrowserView,
        ConfigurationView,
    )
    from dashboard.dashboard_utils import (
        load_json,
        SCENARIOS_FILE,
        GOLDEN_PATTERNS_FILE,
        SPECIES_FILE,
        BENCHMARKS_FILE,
        DATA_DIR,
        RESULTS_DIR
    )
except ImportError as e:
     print(f"Fatal Error: Could not import dashboard components: {e}")
     print("Ensure dashboard_utils.py and dashboard_views.py exist and are correct.")
     exit()


# Constants
REASONING_DEPTH_OPTIONS = ["low", "medium", "high"]
TASK_TYPE_OPTIONS = ["Ethical Scenarios", "Benchmarks"]

# --- Container for the Run View ---
class RunViewContainer(Container):
    """Container holding RunConfiguration and Results for the 'Agent Run' tab."""

    DEFAULT_CSS = """
    RunViewContainer { height: auto; width: 100%; }
    #run-results-container { margin-top: 1; border: round $accent 50%; min-height: 5; height: auto; max-height: 25; overflow-y: auto; padding: 1;}
    #run-results-container ResultsView { height: auto; }
    #run-results-container DataTable { height: auto; max-height: 20; }
    """

    def compose(self) -> ComposeResult:
        app = self.app
        yield RunConfigurationView(
            species=app.species, models=app.models, depth_options=REASONING_DEPTH_OPTIONS,
            task_types=TASK_TYPE_OPTIONS, scenarios=app.scenarios, benchmarks=app.benchmarks,
            current_species=app.selected_species, current_model=app.selected_model,
            current_depth=app.selected_depth, current_task_type=app.selected_task_type,
            current_task_item=app.selected_task_item, id="run-configuration-view"
        )
        yield Container(Static("Run analysis to see results.", classes="text-muted"), id="run-results-container")

    def update_results(self, results_data):
        """Updates the results container with the ResultsView."""
        # print(f"DEBUG: RunViewContainer.update_results called with data: {results_data is not None}") # Optional Debug
        try:
            results_container = self.query_one("#run-results-container")
            results_container.remove_children()
            if results_data:
                # print("DEBUG: Mounting ResultsView...") # Optional Debug
                results_container.mount(ResultsView(results_data=results_data, id="results-view"))
                # print("DEBUG: ResultsView mounted.") # Optional Debug
            else:
                 results_container.mount(Static("Run analysis to see results.", classes="text-muted"))
        except Exception as e:
            print(f"ERROR in RunViewContainer.update_results: {e}")

# --- Main App ---
class EthicsEngineApp(App):
    CSS_PATH = "dashboard.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
    ]

    # Reactive variables
    run_status = reactive("Ready")
    current_run_results_data = reactive(None)
    selected_species = reactive(None)
    selected_model = reactive(None)
    selected_depth = reactive(REASONING_DEPTH_OPTIONS[0])
    selected_task_type = reactive(TASK_TYPE_OPTIONS[0])
    selected_task_item = reactive(None)
    loading = reactive(False)

    def __init__(self):
        super().__init__()
        self.scenarios = load_json(SCENARIOS_FILE, {"Error": "Could not load scenarios"})
        self.models = load_json(GOLDEN_PATTERNS_FILE, {"Error": "Could not load models"})
        self.species = load_json(SPECIES_FILE, {"Error": "Could not load species"})
        self.benchmarks = load_json(BENCHMARKS_FILE, {"Error": "Could not load benchmarks"})
        if isinstance(self.species, dict) and "Error" not in self.species:
             self.selected_species = next(iter(self.species), None)
        if isinstance(self.models, dict) and "Error" not in self.models:
             self.selected_model = next(iter(self.models), None)
        if self.selected_task_type == "Ethical Scenarios":
            if isinstance(self.scenarios, dict) and "Error" not in self.scenarios:
                self.selected_task_item = next(iter(self.scenarios), None)
        elif self.selected_task_type == "Benchmarks":
             self.selected_task_item = "All"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="main-tabs", initial="tab-run"): # Start on run tab
            with TabPane("Agent Run", id="tab-run"):
                 yield RunViewContainer(id="run-view-container")
            with TabPane("Data Management", id="tab-data"):
                 yield DataManagementView(scenarios=self.scenarios, models=self.models, species_data=self.species)
            with TabPane("Results Browser", id="tab-results-browser"):
                 yield ResultsBrowserView(id="results-browser-view")
            with TabPane("Configuration", id="tab-config"):
                 yield ConfigurationView(id="configuration-view")
        yield LoadingIndicator(id="loading-indicator")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#loading-indicator").display = False

    # --- Watchers ---
    def watch_run_status(self, status: str) -> None:
        self.loading = (status == "Running...")
        try:
            status_widget = self.query_one("#run-status", Static)
            status_widget.update(f"Status: {status}")
        except Exception: pass

    def watch_current_run_results_data(self, results: dict | None) -> None:
        # print(f"DEBUG: watch_current_run_results_data triggered. Results exist: {results is not None}") # Optional Debug
        try:
            run_view = self.query_one("#run-view-container", RunViewContainer)
            # Use call_later to ensure update happens smoothly after state change
            self.call_later(run_view.update_results, results)
            # print(f"DEBUG: Called run_view.update_results via call_later.") # Optional Debug
        except Exception as e:
            print(f"DEBUG: Error finding RunViewContainer in watcher (maybe inactive tab?): {e}")

    def watch_loading(self, loading: bool) -> None:
        try:
            self.query_one("#loading-indicator").display = loading
            # Disable/Enable run button based on loading state
            run_button = self.query_one("#run-analysis-button", Button)
            run_button.disabled = loading
        except Exception: pass

    # --- Actions ---
    # REMOVED action_toggle_data_management

    async def action_run_analysis(self):
        """Runs the analysis in a separate thread to avoid blocking the UI."""
        if self.loading:
             self.notify("Analysis already running.", severity="warning")
             return

        self.current_run_results_data = None
        await asyncio.sleep(0.01)
        self.run_status = "Running..."

        try:
            # --- Prepare arguments ---
            class DummyArgs: pass
            args_obj = DummyArgs()
            args_obj.data_dir = str(DATA_DIR)
            args_obj.results_dir = str(RESULTS_DIR)
            args_obj.species = self.selected_species
            args_obj.model = self.selected_model
            args_obj.reasoning_level = self.selected_depth

            if not args_obj.species or not args_obj.model or not args_obj.reasoning_level:
                 raise ValueError("Species, Model, and Depth must be selected.")

            results = None

            # --- Define blocking function calls ---
            if self.selected_task_type == "Ethical Scenarios":
                 from run_scenario_pipelines import run_pipeline_for_scenario # Defer import
                 if not self.selected_task_item or not isinstance(self.scenarios, dict) or self.selected_task_item not in self.scenarios:
                      raise ValueError("Please select a valid scenario.")
                 scenario = {"id": self.selected_task_item, "prompt": self.scenarios.get(self.selected_task_item, "")}

                 # Need to run an async function in a thread
                 # Define a sync wrapper
                 def run_scenario_sync():
                      return asyncio.run(run_pipeline_for_scenario(scenario, args_obj))

                 # Run the sync wrapper in a thread
                 result_data = await asyncio.to_thread(run_scenario_sync)
                 results = {"type": "scenario", "data": [result_data] if result_data else []}

            elif self.selected_task_type == "Benchmarks":
                 from run_benchmarks import run_benchmarks_async, load_benchmarks # Defer import
                 from reasoning_agent import EthicsAgent # Defer import

                 # Load benchmarks synchronously first
                 benchmarks_data = load_benchmarks(BENCHMARKS_FILE)
                 target_benchmarks = benchmarks_data
                 if not target_benchmarks:
                      raise ValueError("No benchmark data found or loaded.")

                 # Prepare agent synchronously
                 answer_agent = EthicsAgent(args_obj.species, args_obj.model, reasoning_level=args_obj.reasoning_level, data_dir=args_obj.data_dir)

                 # Define a sync wrapper for the async benchmark runner
                 def run_bench_sync():
                      return asyncio.run(run_benchmarks_async(target_benchmarks, answer_agent))

                 # Run the sync wrapper in a thread
                 result_data = await asyncio.to_thread(run_bench_sync)
                 results = {"type": "benchmark", "data": result_data}
            else:
                 raise ValueError("Invalid task type selected")

            # --- Update state after thread completes ---
            self.run_status = "Completed"
            self.current_run_results_data = results # Watcher handles UI
            self.notify("Analysis complete.", title="Success")

        except ImportError as e:
             self.run_status = f"Error: Import failed ({e})"
             self.current_run_results_data = None
             self.notify(f"Import Error: {e}", severity="error", title="Run Failed")
        except ValueError as e:
             self.run_status = f"Error: Configuration Issue ({e})"
             self.current_run_results_data = None
             self.notify(f"Configuration Error: {e}", severity="error", title="Run Failed")
        except Exception as e:
             traceback.print_exc()
             self.run_status = f"Error: {e}"
             self.current_run_results_data = None
             self.notify(f"Runtime Error: {e}", severity="error", title="Run Failed")


    # --- Event Handlers ---
    def handle_species_change(self, new_species: str): self.selected_species = new_species
    def handle_model_change(self, new_model: str): self.selected_model = new_model
    def handle_depth_change(self, new_depth: str): self.selected_depth = new_depth
    def handle_task_type_change(self, new_task_type: str):
         if self.selected_task_type != new_task_type:
             self.selected_task_type = new_task_type
             if new_task_type == "Ethical Scenarios":
                  self.selected_task_item = next(iter(self.scenarios), None) if isinstance(self.scenarios, dict) else None
             elif new_task_type == "Benchmarks":
                  self.selected_task_item = "All"
             # Update config view's task item selector
             try:
                 config_view = self.query_one("#run-configuration-view", RunConfigurationView)
                 task_item_select = config_view.query_one("#task-item-select", Select)
                 new_options = config_view._get_task_item_options()
                 task_item_select.set_options(new_options)
                 new_item_value = new_options[0][1] if new_options else None
                 if new_item_value is not Select.BLANK: task_item_select.value = new_item_value
                 else: task_item_select.value = Select.BLANK
                 self.selected_task_item = new_item_value # Ensure app state matches
             except Exception as e:
                 print(f"Error updating task item select from app: {e}")

    def handle_task_item_change(self, new_task_item: str | None): self.selected_task_item = new_task_item

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-analysis-button":
             asyncio.create_task(self.action_run_analysis())

# --- Main execution ---
if __name__ == "__main__":
    all_files_exist = all([ SCENARIOS_FILE.exists(), GOLDEN_PATTERNS_FILE.exists(), SPECIES_FILE.exists(), BENCHMARKS_FILE.exists() ])
    if not all_files_exist:
        print(f"Warning: One or more data files expected in '{DATA_DIR}/' not found.")
    EthicsEngineApp().run()