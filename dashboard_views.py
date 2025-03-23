# dashboard_views.py
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import ListView, ListItem, Label, Button, Static, DataTable

class ScenariosView(Container):
    def __init__(self, scenarios: dict, **kwargs):
        super().__init__(**kwargs)
        self.scenarios = scenarios

    def compose(self) -> ComposeResult:
        list_view = ListView(
            *[ListItem(Label(f"{name}: {desc[:50]}...")) for name, desc in self.scenarios.items()],
            id="scenarios_list"
        )
        yield list_view

class ModelsView(Container):
    def __init__(self, models: dict, **kwargs):
        super().__init__(**kwargs)
        self.models = models

    def compose(self) -> ComposeResult:
        list_view = ListView(
            *[ListItem(Label(f"{name}: {desc[:50]}...")) for name, desc in self.models.items()],
            id="models_list"
        )
        yield list_view

class SummarizersView(Container):
    def __init__(self, summarizers: dict, **kwargs):
        super().__init__(**kwargs)
        self.summarizers = summarizers

    def compose(self) -> ComposeResult:
        list_view = ListView(
            *[ListItem(Label(f"{name}: {prompt[:50]}...")) for name, prompt in self.summarizers.items()],
            id="summarizers_list"
        )
        yield list_view

class RunsView(Container):
    def compose(self) -> ComposeResult:
        import os, json
        # Create the run button and status display
        run_button = Button("Run Analysis", id="run_analysis", variant="primary")
        status_display = Static("Status: Not Started", id="run_status")
        
        # Attempt to load results from results/results.json using final_results structure
        results_file = os.path.join("results", "results.json")
        summary_text = "No summary produced."
        grid = DataTable(id="run_results_table")
        grid.add_column("Model | Species | Scenario")
        grid.add_column("Reasoning")
        grid.add_column("Outcome")
        if os.path.exists(results_file):
            with open(results_file, "r") as f:
                results_data = json.load(f)
            summary_text = results_data.get("summary", "No summary produced.")
            reasoning_results = results_data.get("reasoning_results", {})
            simulation_results = results_data.get("simulation_results", {})
            if reasoning_results:
                for key, reasoning_text in reasoning_results.items():
                    simulation_text = simulation_results.get(key, "No simulation")
                    short_reasoning = reasoning_text if len(reasoning_text) < 50 else reasoning_text[:50] + "..."
                    short_simulation = simulation_text if len(simulation_text) < 50 else simulation_text[:50] + "..."
                    grid.add_row(key, short_reasoning, short_simulation)
            else:
                grid.add_row("No results found", "", "")
        else:
            grid.add_row("No results file found", "", "")
        
        # Create final_summary with full summary text, one row high with horizontal scrolling
        final_summary = Static(summary_text, id="final_summary")
        final_summary.styles.height = "1"
        final_summary.styles.overflow_x = "auto"
        final_summary.styles.white_space = "nowrap"
        
        container = Container(run_button, status_display, final_summary, grid, id="runs_container")
        yield container
