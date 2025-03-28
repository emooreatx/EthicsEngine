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
from textual.widgets import Header, Footer, Button, Static, Select, Label, Markdown, LoadingIndicator, TabbedContent, TabPane
from textual.binding import Binding
from textual.reactive import reactive

# --- Import Views ---
try:
    from dashboard.views import (
        RunConfigurationView,
        ResultsView,
        DataManagementView,
        ResultsBrowserView,
        ConfigurationView,
    )
except ImportError as e:
     print(f"Fatal Error: Could not import dashboard views: {e}")
     exit()

# --- Import Utils ---
try:
    from dashboard.dashboard_utils import (
        load_json,
        save_json,
        SCENARIOS_FILE,
        GOLDEN_PATTERNS_FILE,
        SPECIES_FILE,
        BENCHMARKS_FILE,
        DATA_DIR,
        RESULTS_DIR
    )
except ImportError as e:
     print(f"Fatal Error: Could not import dashboard utils: {e}")
     exit()

# --- Import the NEW Full Run Logic ---
try:
    from dashboard.dashboard_full_run import run_full_set
except ImportError as e:
    print(f"Fatal Error: Could not import full run logic: {e}")
    # Define a dummy function if import fails
    def run_full_set(*args, **kwargs):
        print("ERROR: run_full_set function not available!")
        return None, None


# Constants and Helper Class (keep as before)
REASONING_DEPTH_OPTIONS = ["low", "medium", "high"]
TASK_TYPE_OPTIONS = ["Ethical Scenarios", "Benchmarks"]

class ArgsNamespace:
    """Helper class to mimic argparse namespace."""
    def __init__(self, data_dir, results_dir, species, model, reasoning_level, bench_file=None, scenarios_file=None):
        self.data_dir = str(data_dir)
        self.results_dir = str(results_dir)
        self.species = species
        self.model = model
        self.reasoning_level = reasoning_level
        self.bench_file = str(bench_file) if bench_file else None
        self.scenarios_file = str(scenarios_file) if scenarios_file else None

# --- RunViewContainer (Keep as before) ---
class RunViewContainer(Container):
    DEFAULT_CSS = """
    RunViewContainer { height: auto; width: 100%; }
    #run-results-container { margin-top: 1; border: round $accent 50%; min-height: 5; height: auto; max-height: 25; overflow-y: auto; padding: 1;}
    #run-results-container ResultsView { height: auto; }
    #run-results-container DataTable { height: auto; max-height: 20; }
    .button-group { height: auto; }
    .button-group Button { margin-right: 1; }
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
        try:
            results_container = self.query_one("#run-results-container")
            results_container.remove_children()
            if results_data:
                results_container.mount(ResultsView(results_data=results_data, id="results-view"))
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

    # Reactive variables (keep as before)
    run_status = reactive("Ready")
    current_run_results_data = reactive(None)
    selected_species = reactive(None)
    selected_model = reactive(None)
    selected_depth = reactive(REASONING_DEPTH_OPTIONS[0])
    selected_task_type = reactive(TASK_TYPE_OPTIONS[0])
    selected_task_item = reactive(None)
    loading = reactive(False)

    # Initialization (keep as before)
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

    # Compose (keep as before)
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="main-tabs", initial="tab-run"): # Start on run tab
            with TabPane("Agent Run", id="tab-run"):
                 yield RunViewContainer(id="run-view-container")
            with TabPane("Data Management", id="tab-data"):
                 yield DataManagementView(scenarios=self.scenarios, models=self.models, species_data=self.species, id="data-management-view")
            with TabPane("Results Browser", id="tab-results-browser"):
                 yield ResultsBrowserView(id="results-browser-view")
            with TabPane("Configuration", id="tab-config"):
                 yield ConfigurationView(id="configuration-view")
        yield LoadingIndicator(id="loading-indicator")
        yield Footer()

    # On Mount (keep as before)
    def on_mount(self) -> None:
        self.query_one("#loading-indicator").display = False

    # Watchers (keep as before)
    def watch_run_status(self, status: str) -> None:
        self.loading = ("Running" in status)
        try:
            config_view = self.query_one("#run-configuration-view", RunConfigurationView)
            status_widget = config_view.query_one("#run-status", Static)
            status_widget.update(f"Status: {status}")
        except Exception:
             self.log.warning("Could not find #run-status widget to update.")

    def watch_current_run_results_data(self, results: dict | None) -> None:
        try:
            run_view_container = self.query_one("#run-view-container", RunViewContainer)
            self.call_later(run_view_container.update_results, results)
        except Exception as e:
             self.log.warning(f"Could not find RunViewContainer in watcher (maybe inactive tab?): {e}")

    def watch_loading(self, loading: bool) -> None:
        try:
            self.query_one("#loading-indicator").display = loading
            run_button = self.query_one("#run-analysis-button", Button)
            full_run_button = self.query_one("#run-full-set-button", Button)
            run_button.disabled = loading
            full_run_button.disabled = loading
        except Exception:
            self.log.warning("Could not find #loading-indicator or run buttons to update.")

    # Actions (keep action_run_analysis as before)
    async def action_run_analysis(self):
        """Runs the analysis for a single selected item."""
        if self.loading:
             self.notify("Analysis already running.", severity="warning")
             return

        self.current_run_results_data = None
        await asyncio.sleep(0.01)
        self.run_status = "Running Analysis..."

        try:
            args_obj = ArgsNamespace(
                data_dir=DATA_DIR,
                results_dir=RESULTS_DIR,
                species=self.selected_species,
                model=self.selected_model,
                reasoning_level=self.selected_depth,
                bench_file=BENCHMARKS_FILE,
                scenarios_file=SCENARIOS_FILE
            )

            if not args_obj.species or not args_obj.model or not args_obj.reasoning_level:
                 raise ValueError("Species, Model, and Depth must be selected.")

            results = None

            if self.selected_task_type == "Ethical Scenarios":
                 from run_scenario_pipelines import run_pipeline_for_scenario # Defer import
                 if not self.selected_task_item or not isinstance(self.scenarios, dict) or self.selected_task_item not in self.scenarios:
                      raise ValueError("Please select a valid scenario.")
                 scenario = {"id": self.selected_task_item, "prompt": self.scenarios.get(self.selected_task_item, "")}

                 def run_scenario_sync_wrapper():
                      return asyncio.run(run_pipeline_for_scenario(scenario, args_obj))

                 result_data = await asyncio.to_thread(run_scenario_sync_wrapper)
                 results = {"type": "scenario", "data": [result_data] if result_data else []}

            elif self.selected_task_type == "Benchmarks":
                 from run_benchmarks import run_benchmarks_async, load_benchmarks # Defer import
                 from reasoning_agent import EthicsAgent # Defer import

                 benchmarks_data = load_benchmarks(args_obj.bench_file)
                 target_benchmarks = benchmarks_data.get("eval_data", []) if isinstance(benchmarks_data, dict) else []
                 if not target_benchmarks:
                      raise ValueError("No benchmark data found or loaded.")

                 answer_agent = EthicsAgent(args_obj.species, args_obj.model, reasoning_level=args_obj.reasoning_level, data_dir=args_obj.data_dir)

                 def run_bench_sync_wrapper():
                      return asyncio.run(run_benchmarks_async(target_benchmarks, answer_agent))

                 result_data = await asyncio.to_thread(run_bench_sync_wrapper)
                 timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                 output_file = os.path.join(args_obj.results_dir,
                                f"bench_{args_obj.species.lower()}_{args_obj.model.lower()}_{args_obj.reasoning_level.lower()}_{timestamp}.json")
                 save_json(Path(output_file), result_data)
                 self.log.info(f"Benchmark results saved to {output_file}")
                 results = {"type": "benchmark", "data": result_data}

            else:
                 raise ValueError("Invalid task type selected")

            self.run_status = "Completed"
            self.current_run_results_data = results
            self.notify("Analysis complete.", title="Success")
            try:
                browser_view = self.query_one(ResultsBrowserView)
                browser_view._populate_file_list()
            except Exception:
                self.log.warning("Could not refresh results browser list.")

        except ImportError as e:
             self.run_status = f"Error: Import failed ({e})"
             self.current_run_results_data = None
             self.notify(f"Import Error: Could not load backend script ({e})", severity="error", title="Run Failed", timeout=10)
             self.log.error(f"Import Error during run: {e}\n{traceback.format_exc()}")
        except ValueError as e:
             self.run_status = f"Error: Configuration Issue ({e})"
             self.current_run_results_data = None
             self.notify(f"Configuration Error: {e}", severity="error", title="Run Failed", timeout=8)
             self.log.error(f"Configuration Error during run: {e}")
        except Exception as e:
             self.run_status = f"Error: {e}"
             self.current_run_results_data = None
             self.notify(f"Runtime Error: {e}", severity="error", title="Run Failed", timeout=10)
             self.log.error(f"Runtime Error during run: {e}\n{traceback.format_exc()}")


    # --- Updated Full Set Action Method ---
    async def action_run_full_set(self):
        """Runs all benchmarks and all scenario pipelines using the external script."""
        if self.loading:
             self.notify("Analysis already running.", severity="warning")
             return

        self.run_status = "Running Full Set..."

        try:
            # Prepare arguments (no need for ArgsNamespace here, just pass directly)
            species = self.selected_species
            model = self.selected_model
            level = self.selected_depth

            if not all([species, model, level]):
                 raise ValueError("Species, Model, and Depth must be selected.")

            self.log.info(f"Running full set for {species}, {model}, {level} in thread...")

            # --- Run the external function in a thread ---
            # Pass necessary arguments directly
            saved_files = await asyncio.to_thread(
                run_full_set, # The imported function
                species=species,
                model=model,
                reasoning_level=level,
                data_dir=DATA_DIR,
                results_dir=RESULTS_DIR,
                bench_file=BENCHMARKS_FILE,
                scenarios_file=SCENARIOS_FILE
            )

            # --- Update state after thread completes ---
            self.run_status = "Full Run Completed"

            if saved_files and len(saved_files) == 2 and all(saved_files):
                 bench_out, scenario_out = saved_files
                 self.notify(f"Full run finished.\nBenchmarks: {os.path.basename(bench_out)}\nScenarios: {os.path.basename(scenario_out)}", title="Success", timeout=10)
            else:
                 self.notify("Full run finished, but encountered issues saving files. Check logs.", severity="warning", title="Completed with Issues", timeout=10)

            # Refresh results browser
            try:
                browser_view = self.query_one(ResultsBrowserView)
                browser_view._populate_file_list()
                self.log.info("Results browser list refreshed.")
            except Exception:
                self.log.warning("Could not refresh results browser list after full run.")

        except ValueError as e:
             # Handle config errors before running the thread
             self.run_status = f"Error: Configuration Issue ({e})"
             self.notify(f"Configuration Error: {e}", severity="error", title="Run Failed", timeout=8)
             self.log.error(f"Configuration Error during full run setup: {e}")
        except Exception as e:
             # Handle errors during the threaded execution or afterwards
             self.run_status = f"Error: {e}"
             self.notify(f"Runtime Error during full run: {e}", severity="error", title="Run Failed", timeout=10)
             self.log.error(f"Runtime Error during full run: {e}\n{traceback.format_exc()}")


    # --- Event Handlers (Keep as before) ---
    def handle_species_change(self, new_species: str):
         self.selected_species = new_species
         self.log.info(f"Species selection changed to: {new_species}")

    def handle_model_change(self, new_model: str):
         self.selected_model = new_model
         self.log.info(f"Model selection changed to: {new_model}")

    def handle_depth_change(self, new_depth: str):
         self.selected_depth = new_depth
         self.log.info(f"Depth selection changed to: {new_depth}")

    def handle_task_type_change(self, new_task_type: str):
         if self.selected_task_type != new_task_type:
             self.selected_task_type = new_task_type
             self.log.info(f"Task type changed to: {new_task_type}")
             if new_task_type == "Ethical Scenarios":
                  default_item = next(iter(self.scenarios), None) if isinstance(self.scenarios, dict) else None
             elif new_task_type == "Benchmarks":
                  default_item = "All"
             else:
                  default_item = None
             self.selected_task_item = default_item

             try:
                 config_view = self.query_one("#run-configuration-view", RunConfigurationView)
                 config_view.current_task_type = new_task_type
                 task_item_select = config_view.query_one("#task-item-select", Select)
                 new_options = config_view._get_task_item_options()
                 task_item_select.set_options(new_options)
                 if default_item is not None and default_item is not Select.BLANK:
                     task_item_select.value = default_item
                 else:
                     task_item_select.value = Select.BLANK
                 self.log.info(f"Task item dropdown updated for {new_task_type}. Default: {default_item}")
             except Exception as e:
                 self.log.error(f"Error updating task item select from app: {e}")

    def handle_task_item_change(self, new_task_item: str | None):
         if new_task_item is not None and new_task_item is not Select.BLANK:
             self.selected_task_item = new_task_item
             self.log.info(f"Task item selection changed to: {new_task_item}")
         else:
             self.selected_task_item = None
             self.log.info("Task item selection cleared.")

    # --- Button Press Handler (Keep as before) ---
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-analysis-button":
             asyncio.create_task(self.action_run_analysis())
        elif event.button.id == "run-full-set-button":
             asyncio.create_task(self.action_run_full_set())
        elif event.button.id == "reset-log-btn":
             self.notify("Log reset functionality not yet implemented.", severity="warning")

# --- Main execution guard (Keep as before) ---
if __name__ == "__main__":
    all_files_exist = all([
        SCENARIOS_FILE.exists(),
        GOLDEN_PATTERNS_FILE.exists(),
        SPECIES_FILE.exists(),
        BENCHMARKS_FILE.exists()
    ])
    if not all_files_exist:
        print(f"Warning: One or more essential data files expected in '{DATA_DIR}/' not found.")
        print(f"Checked for: {SCENARIOS_FILE}, {GOLDEN_PATTERNS_FILE}, {SPECIES_FILE}, {BENCHMARKS_FILE}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    EthicsEngineApp().run()