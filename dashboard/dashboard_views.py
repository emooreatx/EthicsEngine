# dashboard/dashboard_views.py
import json
import os
from pathlib import Path
from textual.app import ComposeResult, App
from textual.containers import Container, VerticalScroll, Horizontal, Vertical
from textual.widgets import (
    Label,
    Button,
    Static,
    DataTable,
    ListView,
    ListItem,
    Select,
    RadioSet,
    RadioButton,
    Tabs,
    Tab,
    ContentSwitcher,
    Placeholder,
    Markdown, # Use Markdown for results display
    # Input, TextArea only needed in modals
)
from textual.reactive import reactive
from textual.message import Message
from textual.events import Mount

# Import helpers and constants from the utils file
# Ensure dashboard_utils.py exists and is in the python path
try:
    from dashboard.dashboard_utils import (
        load_json,
        save_json,
        SCENARIOS_FILE,
        GOLDEN_PATTERNS_FILE,
        SPECIES_FILE,
        BENCHMARKS_FILE,
        RESULTS_DIR,
        DATA_DIR,
    )
except ImportError as e:
     print(f"Fatal Error: Could not import dashboard utils: {e}")
     exit()


# Import actions
# Ensure dashboard_actions.py exists and is in the python path
try:
    from dashboard.dashboard_actions import handle_data_delete
except ImportError as e:
     print(f"Fatal Error: Could not import dashboard actions: {e}")
     # Define dummy if needed
     def handle_data_delete(app, data_type, key): print("Error: handle_data_delete not found")


# --- Import Modal Screens ---
# Ensure dashboard_modals.py exists and is in the python path
try:
    from dashboard.dashboard_modals import CreateItemScreen, EditItemScreen
except ImportError:
    print("Warning: dashboard_modals.py not found. Create/Edit functionality will be limited.")
    class CreateItemScreen: pass # Dummy classes
    class EditItemScreen: pass


# --- Implemented Views ---

class RunConfigurationView(Static):
    """View for configuring simulation runs."""

    def __init__(self, species: dict, models: dict, depth_options: list, task_types: list, scenarios: dict, benchmarks: dict, current_species: str | None, current_model: str | None, current_depth: str, current_task_type: str, current_task_item: str | None, **kwargs):
        super().__init__(**kwargs)
        self.species_options = list(species.keys()) if isinstance(species, dict) and "Error" not in species else []
        self.model_options = list(models.keys()) if isinstance(models, dict) and "Error" not in models else []
        self.depth_options = depth_options
        self.task_types = task_types
        self.scenarios = scenarios if isinstance(scenarios, dict) and "Error" not in scenarios else {}
        self.benchmarks = benchmarks if isinstance(benchmarks, dict) and "Error" not in benchmarks else {}
        self.current_species = current_species
        self.current_model = current_model
        self.current_depth = current_depth
        self.current_task_type = current_task_type
        self.current_task_item = current_task_item

    def compose(self) -> ComposeResult:
        with Vertical(id="run-config-vertical"):
            yield Label("Species:")
            yield Select(
                options=[(s, s) for s in self.species_options],
                value=self.current_species, id="species-select", allow_blank=False,
                prompt="Select Species" if not self.current_species else None )
            yield Label("Reasoning Type (Model):")
            yield Select(
                 options=[(m, m) for m in self.model_options],
                 value=self.current_model, id="model-select", allow_blank=False,
                 prompt="Select Model" if not self.current_model else None )
            yield Label("Reasoning Depth:")
            yield RadioSet(
                 *[RadioButton(d, id=d, value=(d == self.current_depth)) for d in self.depth_options],
                 id="depth-radioset" )
            yield Label("Task Type:")
            yield Select(
                 options=[(t, t) for t in self.task_types],
                 value=self.current_task_type, id="task-type-select", allow_blank=False )
            yield Label("Task Item:")
            yield Select(
                 options=self._get_task_item_options(),
                 value=self.current_task_item, id="task-item-select", allow_blank=False,
                 prompt="Select Item" if not self.current_task_item else None )
            yield Button("Run Analysis", id="run-analysis-button", variant="primary", classes="run-button")
            status_text = f"Status: {self.app.run_status}" if hasattr(self, 'app') else "Status: Initializing"
            yield Static(status_text, id="run-status")

    def _get_task_item_options(self):
        if self.current_task_type == "Ethical Scenarios":
             if isinstance(self.scenarios, dict):
                  return [(s_id, s_id) for s_id in self.scenarios.keys()]
        elif self.current_task_type == "Benchmarks":
            return [("All Benchmarks", "All")]
        return []

    def on_select_changed(self, event: Select.Changed) -> None:
        app = self.app
        select_id = event.select.id
        new_value = event.value
        if new_value is Select.BLANK: return
        if select_id == "species-select": app.handle_species_change(new_value)
        elif select_id == "model-select": app.handle_model_change(new_value)
        elif select_id == "task-type-select":
            self.current_task_type = new_value
            app.handle_task_type_change(new_value)
            # Logic to update dependent select is now handled in app.handle_task_type_change
        elif select_id == "task-item-select": app.handle_task_item_change(new_value)

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.radio_set.id == "depth-radioset" and event.pressed is not None:
             self.app.handle_depth_change(event.pressed.label.plain)


class ResultsView(Static):
    """View displaying run results in a DataTable + Detail Markdown."""

    full_results_data = reactive(None)
    selected_row_data = reactive(None)

    def __init__(self, results_data=None, **kwargs):
        super().__init__(**kwargs)
        self.full_results_data = results_data

    def compose(self) -> ComposeResult:
        with Vertical(id="results-display-area"):
             yield DataTable(id="results-table", show_header=True, show_cursor=True, zebra_stripes=True)
             yield Static("--- Details (Select Row Above) ---", classes="title", id="results-detail-title")
             with VerticalScroll(id="results-detail-scroll"):
                  yield Markdown(id="results-detail-markdown") # Correct init

    def on_mount(self) -> None:
        self._render_table()
        self.query_one("#results-detail-markdown", Markdown).update("Select a row to see details.")
        self.query_one("#results-detail-title").display = False

    def _render_table(self) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=True); table.fixed_columns = 1
        if not self.full_results_data or not isinstance(self.full_results_data, dict) or not self.full_results_data.get("data"):
            table.add_column("Status"); table.add_row("No results to display.")
            self.query_one("#results-detail-title").display = False; return

        result_type = self.full_results_data.get("type"); data = self.full_results_data.get("data", [])
        def truncate(text, length=70): text_str = str(text).replace('\n', ' ').replace('\r', ''); return text_str if len(text_str) <= length else text_str[:length] + "…"
        try:
            if result_type == "scenario":
                table.add_columns("Scenario ID", "Scenario Text", "Planner Output", "Executor Output", "Judge Output")
                for result in data: row_key = str(result.get("scenario_id", "")) if result.get("scenario_id") else None; table.add_row( result.get("scenario_id", "N/A"), truncate(result.get("scenario_text", "")), truncate(result.get("planner_output", "")), truncate(result.get("executor_output", "")), truncate(result.get("judge_output", "")), key=row_key )
            elif result_type == "benchmark":
                table.add_columns("QID", "Question", "Expected", "Response", "Evaluation")
                for result in data: row_key = str(result.get("question_id", "")) if result.get("question_id") else None; table.add_row( result.get("question_id", "N/A"), truncate(result.get("question", "")), truncate(result.get("expected_answer", "")), truncate(result.get("response", "")), truncate(result.get("evaluation", "")), key=row_key )
            else: table.add_column("Info"); table.add_row(f"Unknown results format ('{result_type}')."); return
            self.query_one("#results-detail-title").display = True
        except Exception as e: table.clear(columns=True); table.add_column("Error"); table.add_row(f"Failed to display table: {e}"); self.query_one("#results-detail-title").display = False

    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        if not event.cell_key or event.cell_key.row_key is None: self.selected_row_data = None; return
        row_key = event.cell_key.row_key; data = self.full_results_data.get("data", []); result_type = self.full_results_data.get("type"); found_data = None
        for item in data:
            item_id_str = None
            if result_type == "scenario": item_id_str = str(item.get("scenario_id"))
            elif result_type == "benchmark": item_id_str = str(item.get("question_id"))
            if item_id_str == row_key: found_data = item; break
        self.selected_row_data = found_data

    def watch_selected_row_data(self, row_data: dict | None) -> None:
        markdown_widget = self.query_one("#results-detail-markdown", Markdown)
        if row_data is None: markdown_widget.update("Select a row in the table above to see full details."); self.query_one("#results-detail-title").display = False; return
        details = f"### Details for Row: {row_data.get('scenario_id') or row_data.get('question_id')}\n\n";
        for key, value in row_data.items():
             value_str = str(value); display_value = f"\n```\n{value_str}\n```\n" if len(value_str) > 60 or '\n' in value_str else f" {value_str}\n"
             details += f"**{key}:**{display_value}\n"
        markdown_widget.update(details)
        self.query_one("#results-detail-title").display = True
        try: self.query_one("#results-detail-scroll", VerticalScroll).scroll_home(animate=False)
        except Exception: pass


class DataManagementView(Static):
    """View for managing Scenarios, Models, Species data."""

    current_data_tab = reactive("Scenarios")

    def __init__(self, scenarios: dict, models: dict, species_data: dict, **kwargs):
        super().__init__(**kwargs); self.scenarios = scenarios; self.models = models; self.species_data = species_data

    def compose(self) -> ComposeResult:
        with Tabs( Tab("Scenarios", id="tab-Scenarios"), Tab("Models", id="tab-Models"), Tab("Species", id="tab-Species"), id="data-tabs" ): pass
        with ContentSwitcher(initial=self.current_data_tab.lower()): # Use lowercase ID
             with Vertical(id="scenarios"): yield Label("Scenarios List:", classes="title"); yield ListView(id="scenarios-list")
             with Vertical(id="models"): yield Label("Models (Golden Patterns) List:", classes="title"); yield ListView(id="models-list")
             with Vertical(id="species"): yield Label("Species List:", classes="title"); yield ListView(id="species-list")
        with Horizontal(id="data-actions"): yield Button("Create New", id="data-create-btn", variant="success"); yield Button("Edit Selected", id="data-edit-btn", variant="primary"); yield Button("Delete Selected", id="data-delete-btn", variant="error")

    def on_mount(self) -> None:
        try: self.query_one(ContentSwitcher).current = self.current_data_tab.lower()
        except Exception as e: print(f"Error setting initial ContentSwitcher state: {e}")
        self._update_list_view()

    def watch_current_data_tab(self, new_tab_name: str) -> None:
        try: self.query_one(ContentSwitcher).current = new_tab_name.lower(); self._update_list_view()
        except Exception as e: print(f"Error watching current_data_tab: {e}")

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        new_tab = event.tab.id.split("-")[1]
        if self.current_data_tab != new_tab: self.current_data_tab = new_tab

    def _get_active_listview_and_data(self):
        try: current_tab_value = self.current_data_tab; active_id_lower = current_tab_value.lower()
        except AttributeError: active_id_lower = DataManagementView.current_data_tab.default.lower(); current_tab_value = DataManagementView.current_data_tab.default
        list_view_id = f"#{active_id_lower}-list"
        try: list_view = self.query_one(list_view_id, ListView)
        except Exception: return None, None, None
        data_dict = None; file_path = None
        if hasattr(self, 'app'):
            if current_tab_value == "Scenarios": data_dict = self.app.scenarios; file_path = SCENARIOS_FILE
            elif current_tab_value == "Models": data_dict = self.app.models; file_path = GOLDEN_PATTERNS_FILE
            elif current_tab_value == "Species": data_dict = self.app.species; file_path = SPECIES_FILE
        else: # Fallback
            if current_tab_value == "Scenarios": data_dict = self.scenarios
            elif current_tab_value == "Models": data_dict = self.models
            elif current_tab_value == "Species": data_dict = self.species_data
        return list_view, data_dict, file_path

    def _update_list_view(self) -> None:
        list_view, data_dict, _ = self._get_active_listview_and_data();
        if list_view is None: return
        if data_dict is None: list_view.clear(); list_view.append(ListItem(Label(f"Error: Data source not found."))); return
        current_index = list_view.index; list_view.clear()
        if not isinstance(data_dict, dict) or "Error" in data_dict or "_load_error" in data_dict: fail_message = data_dict.get("Error", "load error") if isinstance(data_dict, dict) else "load error"; list_view.append(ListItem(Label(f"Error loading {self.current_data_tab} data: {fail_message}"))); return
        if not data_dict: list_view.append(ListItem(Label(f"No {self.current_data_tab} defined."))); return
        sorted_keys = sorted(data_dict.keys())
        for key in sorted_keys: value = data_dict[key]; display_text = f"{key}: {str(value)[:70]}..." if value else key; list_view.append(ListItem(Label(display_text), name=key))
        if current_index is not None and current_index < len(list_view): list_view.index = current_index
        elif len(list_view) > 0: list_view.index = 0

    def _create_callback(self, result: tuple | None) -> None:
        if result:
            new_key, new_value = result; list_view, data_dict, file_path = self._get_active_listview_and_data()
            if data_dict is None or file_path is None: return
            if new_key in data_dict: self.app.notify(f"Error: Key '{new_key}' already exists.", severity="error", title="Create Failed"); return
            data_dict[new_key] = new_value; save_json(file_path, data_dict); self.app.notify(f"Created '{new_key}'.", title="Create Success"); self._update_list_view()
            for index, item in enumerate(list_view.children):
                 if isinstance(item, ListItem) and item.name == new_key: list_view.index = index; break

    def _edit_callback(self, new_value: str | None, item_key: str) -> None:
        if new_value is not None:
             list_view, data_dict, file_path = self._get_active_listview_and_data()
             if data_dict is None or file_path is None or item_key not in data_dict: return
             data_dict[item_key] = new_value; save_json(file_path, data_dict); self.app.notify(f"Updated '{item_key}'.", title="Edit Success"); self._update_list_view()
             for index, item in enumerate(list_view.children):
                  if isinstance(item, ListItem) and item.name == item_key: list_view.index = index; break

    def on_button_pressed(self, event: Button.Pressed) -> None:
        list_view, data_dict, _ = self._get_active_listview_and_data()
        if not list_view: self.app.notify("List view not available.", severity="error"); return
        if not isinstance(data_dict, dict) or "Error" in data_dict or "_load_error" in data_dict: self.app.notify("Data not loaded.", severity="error"); return
        selected_list_item = list_view.highlighted_child; selected_key = selected_list_item.name if selected_list_item else None
        if event.button.id == "data-create-btn":
            if 'CreateItemScreen' in globals() and CreateItemScreen is not None: self.app.push_screen(CreateItemScreen(self.current_data_tab), self._create_callback)
            else: self.app.notify("Create functionality unavailable.", severity="error")
        elif event.button.id == "data-edit-btn":
            if selected_key and selected_key in data_dict:
                 initial_value = data_dict[selected_key]
                 if 'EditItemScreen' in globals() and EditItemScreen is not None: self.app.push_screen( EditItemScreen(self.current_data_tab, selected_key, str(initial_value)), lambda value: self._edit_callback(value, selected_key) )
                 else: self.app.notify("Edit functionality unavailable.", severity="error")
            elif selected_key: self.app.notify(f"Key '{selected_key}' not found.", severity="error")
            else: self.app.notify("No item selected.", severity="warning")
        elif event.button.id == "data-delete-btn":
            if selected_key: handle_data_delete(self.app, self.current_data_tab, selected_key)
            else: self.app.notify("No item selected.", severity="warning")


class ResultsBrowserView(Static):
    """View for Browse and displaying past result files."""

    selected_file = reactive(None)

    def compose(self) -> ComposeResult:
        with Horizontal():
             with Vertical(id="results-file-list-container"):
                 yield Label("Past Result Files (Newest First):", classes="title")
                 yield ListView(id="results-browser-list")
             with VerticalScroll(id="results-content-container"):
                 yield Markdown("Select a file to view results", id="results-browser-content")

    def on_mount(self) -> None: self._populate_file_list()

    def _scan_results_dir(self) -> list[str]:
        if not RESULTS_DIR.exists() or not RESULTS_DIR.is_dir(): return []
        try: files = sorted(RESULTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True); return [f.name for f in files]
        except Exception as e: print(f"Error scanning results directory: {e}"); return []

    def _populate_file_list(self) -> None:
        list_view = self.query_one("#results-browser-list", ListView); list_view.clear()
        result_files = self._scan_results_dir()
        if not result_files: list_view.append(ListItem(Label("No result files found.")))
        else:
            for filename in result_files: list_view.append(ListItem(Label(filename), name=filename))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "results-browser-list" and event.item is not None:
             filename = event.item.name; self.selected_file = filename

    def watch_selected_file(self, filename: str | None) -> None:
        content_display = self.query_one("#results-browser-content", Markdown)
        if not filename: content_display.update("Select a file to view results"); return
        filepath = RESULTS_DIR / filename; self.app.notify(f"Loading {filename}...")
        data = load_json(filepath)
        if isinstance(data, dict) and ("Error" in data or "_load_error" in data):
            content_display.update(f"# Error Loading {filename}\n\n{data.get('Error', 'Could not load')}")
            self.app.notify(f"Error loading {filename}", severity="error", title="Load Error"); return
        try:
             formatted_json = json.dumps(data, indent=2)
             content_display.update(f"### {filename}\n\n```json\n{formatted_json}\n```")
             self.app.notify(f"Displayed {filename}.", title="Result Loaded")
        except Exception as e:
             content_display.update(f"# Error Displaying {filename}\n\n{e}")
             self.app.notify(f"Error displaying {filename}: {e}", severity="error")


class ConfigurationView(Static):
     """Placeholder view for managing configuration."""
     def compose(self) -> ComposeResult:
          yield Label("Configuration Management (Placeholder)", classes="title")
          yield Static("LLM Config, Semaphore, Logger settings could be managed here.", classes="body")
          yield Button("Reset Log File (Not Implemented)", id="reset-log-btn")


