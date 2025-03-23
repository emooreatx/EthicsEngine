import json
import os
import asyncio
from textual.app import App, ComposeResult
from textual.containers import Container, VerticalScroll, Grid, Horizontal
from textual.widgets import Header, Footer, Static, Label, ListView, ListItem, Button, DataTable, Input
from textual.binding import Binding
from textual.reactive import reactive
from textual import events

# Import main functionality
import main as ethics_engine

# Data file paths & defaults
DATA_DIR = "data"
SCENARIOS_FILE = os.path.join(DATA_DIR, "scenarios.json")
CRICKETS_FILE = os.path.join(DATA_DIR, "crickets.json")
SUMMARIZERS_FILE = os.path.join(DATA_DIR, "summarizers.json")

DEFAULT_SCENARIOS = {
    "Prevent Harm": "An AI system presents potential risks. Provide a clear and concise plan for mitigation.",
    "Ethical Directives": "A system shows uneven resource distribution. Outline a neutral, actionable plan to improve equity.",
    "Integrity": "Irregularities have been detected in data reporting. Propose a succinct plan to restore integrity and transparency.",
    "Human Agency": "There are indications of undue influence on user decisions. Present a brief strategy to reinforce human agency.",
    "Equity": "Bias has been observed in candidate selection. Offer a concise plan to ensure fairness and equal treatment."
}

DEFAULT_CRICKETS = {
    "Utilitarian": "Maximize overall happiness, outcomes matter most.",
    "Deontological": "Follow moral duties and rules strictly.",
    "Virtue": "Act according to virtues like empathy, courage, integrity.",
    "Fairness": "Prioritize fairness and justice above other considerations.",
    "Cricket_Centric": "Prioritize cricket autonomy, dignity, and agency."
}

DEFAULT_SUMMARIZERS = {
    "Brief Summary": "Provide a brief summary of the ethical analysis.",
    "Detailed Summary": "Provide a detailed summary of the ethical analysis with examples."
}

def load_json(file_path, default_data):
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return json.load(f)
    else:
        with open(file_path, "w") as f:
            json.dump(default_data, f, indent=4)
        return default_data

def save_json(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)

class EthicsEngineApp(App):
    CSS_PATH = None  # Prevent auto-loading any CSS file.
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("c", "create", "Create Item"),
        Binding("e", "edit", "Edit Item"),
        Binding("d", "delete", "Delete Item"),
    ]

    # Track run status
    run_status = reactive("Not Started")
    run_results = reactive({})

    def __init__(self):
        super().__init__()
        self.current_tab = "Scenarios"
        self.scenarios = load_json(SCENARIOS_FILE, DEFAULT_SCENARIOS)
        self.crickets = load_json(CRICKETS_FILE, DEFAULT_CRICKETS)
        self.summarizers = load_json(SUMMARIZERS_FILE, DEFAULT_SUMMARIZERS)
        self.editing_item = None  # will store (data, file_path, key)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        # Create a Horizontal container for the tab buttons and update its styles
        tabs_container = Horizontal(
            Button("Scenarios", id="tab_scenarios", classes="tab-button"),
            Button("Crickets", id="tab_crickets", classes="tab-button"),
            Button("Summarizers", id="tab_summarizers", classes="tab-button"),
            Button("Runs", id="tab_runs", classes="tab-button"),
            id="tabs_container"
        )
        tabs_container.styles.width = "100%"
        tabs_container.styles.justify_content = "space-evenly"
        tabs_container.styles.padding = 1  # Use numeric value instead of string "1"
        yield tabs_container
        # Yield the currently selected view
        if self.current_tab == "Scenarios":
            yield self.scenarios_view()
        elif self.current_tab == "Crickets":
            yield self.crickets_view()
        elif self.current_tab == "Summarizers":
            yield self.summarizers_view()
        else:  # "Runs"
            yield self.runs_view()
        yield Footer()

    def scenarios_view(self) -> Container:
        list_view = ListView(
            *[ListItem(Label(f"{name}: {desc[:50]}...")) for name, desc in self.scenarios.items()],
            id="scenarios_list"
        )
        return Container(list_view)

    def crickets_view(self) -> Container:
        list_view = ListView(
            *[ListItem(Label(f"{name}: {desc[:50]}...")) for name, desc in self.crickets.items()],
            id="crickets_list"
        )
        return Container(list_view)

    def summarizers_view(self) -> Container:
        list_view = ListView(
            *[ListItem(Label(f"{name}: {prompt[:50]}...")) for name, prompt in self.summarizers.items()],
            id="summarizers_list"
        )
        return Container(list_view)

    def runs_view(self) -> Container:
        """Enhanced runs view with a button to start analysis and status display"""
        grid = Grid(id="runs_grid")
        
        run_button = Button("Run Analysis", id="run_analysis", variant="primary")
        status_display = Static(f"Status: {self.run_status}", id="run_status")
        results_table = DataTable(id="run_results_table")
        results_table.add_column("Agent")
        results_table.add_column("Scenario")
        results_table.add_column("Reasoning")
        results_table.add_column("Outcome")
        
        container = Container(
            run_button,
            status_display,
            results_table,
            id="runs_container"
        )
        
        return container

    async def run_analysis(self):
        """Run the ethics engine analysis"""
        self.run_status = "Running..."
        self.query_one("#run_status", Static).update(f"Status: {self.run_status}")
        
        try:
            # Run the analysis in a separate thread to avoid blocking the UI
            await asyncio.to_thread(self._run_analysis_thread)
            
            # Update status with the last debug message instead of "Completed"
            if hasattr(self, 'analysis_results'):
                results_text = self.analysis_results
                # extract last non-empty line from results_text
                last_line = ""
                for line in reversed(results_text.strip().splitlines()):
                    if line.strip():
                        last_line = line.strip()
                        break
                self.run_status = last_line if last_line else "Completed"
                self.query_one("#run_status", Static).update(f"Status: {self.run_status}")
                self.update_results_table(results_text)
        
        except Exception as e:
            self.run_status = f"Error: {str(e)}"
            self.query_one("#run_status", Static).update(f"Status: {self.run_status}")

    def _run_analysis_thread(self):
        """Run analysis in a separate thread to prevent UI blocking"""
        try:
            # Remove extra stdout/stderr redirection to allow summary output
            from main import run_analysis_for_dashboard
            scenarios_data = self.scenarios
            crickets_data = self.crickets
            summarizers_data = self.summarizers
            self.analysis_results = run_analysis_for_dashboard(
                scenarios=scenarios_data,
                ethical_agents=crickets_data,
                summarizer_prompts=summarizers_data
            )
        except Exception as e:
            self.analysis_results = f"Error during analysis: {str(e)}"

    def update_results_table(self, results_text):
        """Update the results table with the summary data from results.json if available."""
        results_table = self.query_one("#run_results_table", DataTable)
        results_table.clear()
        import os, json
        results_path = os.path.join("data", "results.json")
        if os.path.exists(results_path):
            with open(results_path, "r") as f:
                data = json.load(f)
            summary = data.get("summary", "")
            # Add a single row displaying the summary in the Outcome column
            results_table.add_row("Summary", "", "", summary)
        else:
            # Fallback: parse the results_text as before
            rows_added = 0
            lines = results_text.split("\n")
            for line in lines:
                if line.startswith("🚀") or line.strip() == "":
                    continue
                parts = line.split(":")
                if len(parts) == 2 and " (" in parts[0] and ") - Reasoning:" in parts[1]:
                    agent_scenario, details = parts
                    agent, scenario = agent_scenario.split(" (")
                    scenario = scenario.rstrip(")")
                    reasoning, outcome = details.split("- Outcome:")
                    reasoning = reasoning.replace("- Reasoning:", "").strip()
                    outcome = outcome.strip()
                    results_table.add_row(agent.strip(), scenario.strip(), reasoning, outcome)
                    rows_added += 1
            if rows_added == 0:
                results_table.add_row("Summary", "", "", results_text.strip().replace("\n", "<br>"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id
        
        # Handle tab buttons
        if button_id == "tab_scenarios":
            self.current_tab = "Scenarios"
            self.refresh_view()
        elif button_id == "tab_crickets":
            self.current_tab = "Crickets"
            self.refresh_view()
        elif button_id == "tab_summarizers":
            self.current_tab = "Summarizers"
            self.refresh_view()
        elif button_id == "tab_runs":
            self.current_tab = "Runs"
            self.refresh_view()
        # Handle run analysis button
        elif button_id == "run_analysis":
            if self.run_status != "Running...":
                asyncio.create_task(self.run_analysis())

    def action_create(self):
        if self.current_tab == "Scenarios":
            new_name = f"New Scenario {len(self.scenarios) + 1}"
            self.scenarios[new_name] = f"Description for {new_name}"
            save_json(SCENARIOS_FILE, self.scenarios)
        elif self.current_tab == "Crickets":
            new_name = f"New Cricket {len(self.crickets) + 1}"
            self.crickets[new_name] = f"Description for {new_name}"
            save_json(CRICKETS_FILE, self.crickets)
        elif self.current_tab == "Summarizers":
            new_name = f"New Summarizer {len(self.summarizers) + 1}"
            self.summarizers[new_name] = f"Prompt for {new_name}"
            save_json(SUMMARIZERS_FILE, self.summarizers)
        self.refresh_view()

    def launch_edit(self, list_selector: str, data: dict, file_path: str):
        list_view = self.query_one(list_selector, ListView)
        selected_index = list_view.index
        if selected_index is None or selected_index < 0 or selected_index >= len(data):
            return  # No valid selection
        key = list(data.keys())[selected_index]
        input_widget = Input(name="edit_input", placeholder="Edit item text…", value=data[key])
        self.editing_item = (data, file_path, key)
        list_view.parent.mount(input_widget, before=list_view)
        input_widget.focus()

    def action_edit(self):
        if self.current_tab == "Scenarios":
            self.launch_edit("#scenarios_list", self.scenarios, SCENARIOS_FILE)
        elif self.current_tab == "Crickets":
            self.launch_edit("#crickets_list", self.crickets, CRICKETS_FILE)
        elif self.current_tab == "Summarizers":
            self.launch_edit("#summarizers_list", self.summarizers, SUMMARIZERS_FILE)
        else:
            # ...existing edit behavior for other tabs if any...
            pass

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.name == "edit_input" and self.editing_item is not None:
            data, file_path, key = self.editing_item
            data[key] = event.value
            save_json(file_path, data)
            self.editing_item = None
            event.input.remove()  # Remove inline input
            self.refresh_view()

    def action_delete(self):
        list_view = None
        data = None
        file_path = None
        if self.current_tab == "Scenarios":
            list_view = self.query_one("#scenarios_list", ListView)
            data = self.scenarios
            file_path = SCENARIOS_FILE
        elif self.current_tab == "Crickets":
            list_view = self.query_one("#crickets_list", ListView)
            data = self.crickets
            file_path = CRICKETS_FILE
        elif self.current_tab == "Summarizers":
            list_view = self.query_one("#summarizers_list", ListView)
            data = self.summarizers
            file_path = SUMMARIZERS_FILE

        if list_view and data:
            try:
                selected_index = list_view.index
                key = list(data.keys())[selected_index]
                del data[key]
                save_json(file_path, data)
                self.refresh_view()
            except Exception:
                pass

    def refresh_view(self):
        """Refresh the content area with the current tab's view"""
        # Remove all children except the header, tab buttons, and footer
        for child in self.query():
            if isinstance(child, Container) and not isinstance(child, Header) and not isinstance(child, Footer):
                child.remove()
            
        # Add the appropriate view based on current_tab
        if self.current_tab == "Scenarios":
            self.mount(self.scenarios_view())
        elif self.current_tab == "Crickets":
            self.mount(self.crickets_view())
        elif self.current_tab == "Summarizers":
            self.mount(self.summarizers_view())
        else:  # "Runs"
            # Remove existing runs_container if it exists
            try:
                existing_runs_container = self.query_one("#runs_container", Container)
                existing_runs_container.remove()
            except Exception as e:
                #print(e)
                print("No existing runs_container found.")
                pass
            self.mount(self.runs_view())

if __name__ == "__main__":
    EthicsEngineApp().run()
