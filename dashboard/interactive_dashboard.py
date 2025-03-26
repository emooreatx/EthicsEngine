#!/usr/bin/env python3
import os
import json
import asyncio
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Header, Footer, Button, Input
from textual.binding import Binding
from textual.reactive import reactive
from textual import events

# Default data values.
DEFAULT_SCENARIOS = {"Scenario1": "Default scenario text"}
DEFAULT_GOLDEN_PATTERNS = {"Deontological": "Default model description"}
DEFAULT_SPECIES = {"Species1": "Default species traits"}
DEFAULT_SUMMARIZERS = {"Summarizer1": "Default summarizer text"}

# Simple JSON load/save implementations.
def load_json(file_path, default_data):
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return json.load(f)
    return default_data

def save_json(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)

# Import dashboard views and actions.
from dashboard.dashboard_views import ScenariosView, ModelsView, SummarizersView, RunsView
from dashboard.dashboard_actions import (
    refresh_view,
    run_analysis_action,
    update_results_table,
    action_create,
    action_edit,
    action_delete,
)

# File paths.
DATA_DIR = "data"
SCENARIOS_FILE = os.path.join(DATA_DIR, "scenarios.json")
GOLDEN_PATTERNS_FILE = os.path.join(DATA_DIR, "golden_patterns.json")
SPECIES_FILE = os.path.join(DATA_DIR, "species.json")
SUMMARIZERS_FILE = os.path.join(DATA_DIR, "summarizers.json")

class EthicsEngineApp(App):
    CSS_PATH = None  # No external CSS.
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("c", "create", "Create Item"),
        Binding("e", "edit", "Edit Item"),
        Binding("d", "delete", "Delete Item"),
    ]

    run_status = reactive("Not Started")
    run_results = reactive({})

    def __init__(self):
        super().__init__()
        self.current_tab = "Scenarios"
        self.scenarios = load_json(SCENARIOS_FILE, DEFAULT_SCENARIOS)
        self.models = load_json(GOLDEN_PATTERNS_FILE, DEFAULT_GOLDEN_PATTERNS)
        self.species = load_json(SPECIES_FILE, DEFAULT_SPECIES)
        self.summarizers = load_json(SUMMARIZERS_FILE, DEFAULT_SUMMARIZERS)
        self.editing_item = None  # Will store (data, file_path, key)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        tabs_container = Horizontal(
            Button("Scenarios", id="tab_scenarios", classes="tab-button"),
            Button("Models", id="tab_models", classes="tab-button"),
            Button("Species", id="tab_species", classes="tab-button"),
            Button("Summarizers", id="tab_summarizers", classes="tab-button"),
            Button("Runs", id="tab_runs", classes="tab-button"),
            id="tabs_container"
        )
        tabs_container.styles.width = "100%"
        tabs_container.styles.justify_content = "space-evenly"
        tabs_container.styles.padding = 1
        yield tabs_container

        # Container for dynamic content.
        yield Container(id="main_container")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_view()

    async def run_analysis(self):
        await run_analysis_action(self)

    def update_results_table(self):
        update_results_table(self)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id.startswith("tab_"):
            # Extract tab name from button ID (e.g., "tab_scenarios" -> "Scenarios")
            self.current_tab = button_id.split("_", 1)[1].capitalize()
            self.refresh_view()
        elif button_id == "run_analysis":
            if self.run_status != "Running...":
                asyncio.create_task(self.run_analysis())

    def action_create(self):
        action_create(self, SCENARIOS_FILE, GOLDEN_PATTERNS_FILE, SPECIES_FILE, SUMMARIZERS_FILE)

    def action_edit(self):
        action_edit(self, SCENARIOS_FILE, GOLDEN_PATTERNS_FILE, SPECIES_FILE, SUMMARIZERS_FILE)

    def action_delete(self):
        action_delete(self, SCENARIOS_FILE, GOLDEN_PATTERNS_FILE, SPECIES_FILE, SUMMARIZERS_FILE)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.name == "edit_input" and self.editing_item is not None:
            data, file_path, key = self.editing_item
            data[key] = event.value
            save_json(file_path, data)
            self.editing_item = None
            event.input.remove()
            self.refresh_view()

    def refresh_view(self):
        refresh_view(self)

if __name__ == "__main__":
    EthicsEngineApp().run()
