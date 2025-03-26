from pathlib import Path
import json

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import ListView, ListItem, Label, Button, Static, DataTable

class ScenariosView(Container):
    def __init__(self, scenarios: dict, **kwargs):
        super().__init__(**kwargs)
        self.scenarios = scenarios

    def compose(self) -> ComposeResult:
        # Display each scenario id and first 50 characters of its text.
        items = [
            ListItem(Label(f"{sid}: {desc[:50]}…"))
            for sid, desc in self.scenarios.items()
        ]
        yield ListView(*items)

class ModelsView(Container):
    def __init__(self, models: dict, **kwargs):
        super().__init__(**kwargs)
        self.models = models

    def compose(self) -> ComposeResult:
        # Display each model name and first 50 characters of its description.
        items = [
            ListItem(Label(f"{name}: {desc[:50]}…"))
            for name, desc in self.models.items()
        ]
        yield ListView(*items)

class JudgesView(Container):
    def __init__(self, judges: list, **kwargs):
        super().__init__(**kwargs)
        self.judges = judges

    def compose(self) -> ComposeResult:
        # Display each judge's species and first 50 characters of its prompt template.
        items = [
            ListItem(Label(f"{cfg.get('species', '<unknown>')}: {cfg.get('prompt_template', '')[:50]}…"))
            for cfg in self.judges
        ]
        yield ListView(*items)

class RunsView(Container):
    def compose(self) -> ComposeResult:
        run_button = Button("Run Analysis", id="run_analysis", variant="primary")
        status = Static("Status: Ready", id="run_status")

        # Updated table columns for the new pipeline output.
        table = DataTable(id="run_results")
        table.add_column("Scenario ID")
        table.add_column("Scenario Text")
        table.add_column("Planner Output")
        table.add_column("Executor Output")
        table.add_column("Judge Output")

        results_dir = Path("results")
        # Look for the latest pipeline result file with the 'scenarios_pipeline_' prefix.
        latest = max(
            results_dir.glob("scenarios_pipeline_*.json"), 
            default=None, 
            key=lambda p: p.stat().st_mtime
        )
        if latest:
            # Load the JSON file as a list of pipeline result objects.
            data = json.loads(latest.read_text())
            for result in data:
                scenario_id = result.get("scenario_id", "unknown")
                scenario_text = result.get("scenario_text", "")
                planner_output = result.get("planner_output", "")
                executor_output = result.get("executor_output", "")
                judge_output = result.get("judge_output", "")
                # Truncate long strings to 50 characters.
                def truncate(text): 
                    return text if len(text) <= 50 else text[:50] + "…"
                table.add_row(
                    scenario_id,
                    truncate(scenario_text),
                    truncate(planner_output),
                    truncate(executor_output),
                    truncate(judge_output)
                )
        else:
            table.add_row("No results found", "", "", "", "")

        yield Container(run_button, status, table, id="runs_container")
