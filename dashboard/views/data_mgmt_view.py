# EthicsEngine/dashboard/views/data_mgmt_view.py
import json
from pathlib import Path
import logging # Import logging
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal # <-- ContentSwitcher REMOVED from here
from textual.widgets import (
    Label,
    Button,
    Static,
    ListView,
    ListItem,
    Tabs,
    Tab,
    ContentSwitcher, # <-- ContentSwitcher ADDED here
)
from textual.reactive import reactive
from textual.events import Mount
from textual.message import Message
from textual.markup import escape # Import escape

# Import helpers, actions, and modals
try:
    from ..dashboard_utils import (
        save_json,
        SCENARIOS_FILE,
        GOLDEN_PATTERNS_FILE,
        SPECIES_FILE,
    )
    from ..dashboard_actions import handle_data_delete
    from ..dashboard_modals import CreateItemScreen, EditItemScreen
except ImportError as e:
     # Use basic logger if app/config logger isn't available
     logger = logging.getLogger("DataMgmtView_Fallback")
     logger.error(f"ERROR importing dependencies in data_mgmt_view.py: {e}")
     def save_json(path, data): print(f"Dummy save_json called for {path}")
     def handle_data_delete(app, data_type, key): print(f"Dummy delete called for {key}")
     class CreateItemScreen: pass
     class EditItemScreen: pass
     SCENARIOS_FILE = Path("dummy_scenarios.json")
     GOLDEN_PATTERNS_FILE = Path("dummy_models.json")
     SPECIES_FILE = Path("dummy_species.json")

# Use specific logger
try:
    from config.config import logger
except ImportError:
    logger = logging.getLogger("DataMgmtView_Fallback")


class DataManagementView(Static):
    """View for managing Scenarios, Models, Species data."""

    current_data_tab = reactive("Scenarios")
    log = logger # Use imported logger

    def __init__(self, scenarios: dict, models: dict, species_data: dict, **kwargs):
        super().__init__(**kwargs)
        self.scenarios = scenarios
        self.models = models
        self.species_data = species_data

    def compose(self) -> ComposeResult:
        yield Tabs(
            Tab("Scenarios", id="tab-Scenarios"),
            Tab("Models", id="tab-Models"),
            Tab("Species", id="tab-Species"),
            id="data-tabs"
        )
        yield Static(
            "Note: Create/Edit buttons use basic placeholders. For full editing, modify the JSON files in the 'data' directory directly.",
            classes="note text-muted"
        )
        with ContentSwitcher(initial=f"content-{self.current_data_tab.lower()}"):
             with Vertical(id="content-scenarios"):
                 yield Label("Scenarios List:", classes="title")
                 yield ListView(id="scenarios-list")
             with Vertical(id="content-models"):
                 yield Label("Models (Golden Patterns) List:", classes="title")
                 yield ListView(id="models-list")
             with Vertical(id="content-species"):
                 yield Label("Species List:", classes="title")
                 yield ListView(id="species-list")
        with Horizontal(id="data-actions"):
            yield Button("Create New", id="data-create-btn", variant="success")
            yield Button("Edit Selected", id="data-edit-btn", variant="primary")
            yield Button("Delete Selected", id="data-delete-btn", variant="error")

    def on_mount(self) -> None:
        # ... (Keep as before) ...
        try:
            self.query_one(ContentSwitcher).current = f"content-{self.current_data_tab.lower()}"
        except Exception as e: self.log.error(f"Error setting initial ContentSwitcher: {e}", exc_info=True)
        self._update_list_view()

    def watch_current_data_tab(self, new_tab_name: str) -> None:
        # ... (Keep as before) ...
        try:
            self.query_one(ContentSwitcher).current = f"content-{new_tab_name.lower()}"
            self._update_list_view()
        except Exception as e: self.log.error(f"Error watching current_data_tab: {e}", exc_info=True)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        # ... (Keep as before) ...
        new_tab_name = event.tab.id.split("-")[1]
        if self.current_data_tab != new_tab_name:
            self.current_data_tab = new_tab_name

    def _get_active_listview_and_data(self):
        # ... (Keep as before) ...
        try: current_tab_value = self.current_data_tab
        except AttributeError: current_tab_value = DataManagementView.current_data_tab.default
        active_id_lower = current_tab_value.lower(); list_view_id = f"#{active_id_lower}-list"
        try: list_view = self.query_one(list_view_id, ListView)
        except Exception: self.log.error(f"Could not find ListView: {list_view_id}"); return None, None, None
        data_dict = None; file_path = None
        if hasattr(self, 'app') and self.app: # Check app reference first
            if current_tab_value == "Scenarios": data_dict = self.app.scenarios; file_path = SCENARIOS_FILE
            elif current_tab_value == "Models": data_dict = self.app.models; file_path = GOLDEN_PATTERNS_FILE
            elif current_tab_value == "Species": data_dict = self.app.species; file_path = SPECIES_FILE
        else: # Fallback to self attributes if app isn't available (less robust)
            if current_tab_value == "Scenarios": data_dict = self.scenarios; file_path = SCENARIOS_FILE
            elif current_tab_value == "Models": data_dict = self.models; file_path = GOLDEN_PATTERNS_FILE
            elif current_tab_value == "Species": data_dict = self.species_data; file_path = SPECIES_FILE
        if data_dict is None: self.log.error(f"Data dict for {current_tab_value} is None.")
        if file_path is None: self.log.error(f"File path for {current_tab_value} is None.")
        return list_view, data_dict, file_path

    def _update_list_view(self) -> None:
        # ... (Keep as before) ...
        list_view, data_dict, _ = self._get_active_listview_and_data()
        if list_view is None: return
        current_index = list_view.index; list_view.clear()
        if data_dict is None: list_view.append(ListItem(Label(f"Error: Data source missing."))); return
        if not isinstance(data_dict, dict) or "Error" in data_dict or "_load_error" in data_dict:
            fail_message = data_dict.get("Error", data_dict.get("_load_error", "load error")) if isinstance(data_dict, dict) else "unknown error"
            list_view.append(ListItem(Label(f"Error loading {self.current_data_tab}: {escape(fail_message)}")))
            return
        if not data_dict: list_view.append(ListItem(Label(f"No {self.current_data_tab} defined."))); return
        sorted_keys = sorted(data_dict.keys())
        for key in sorted_keys:
            value = data_dict[key]
            display_text = f"{key}: {str(value)[:70]}..." if len(str(value)) > 70 else f"{key}: {value}"
            list_view.append(ListItem(Label(escape(display_text)), name=key))
        if current_index is not None and 0 <= current_index < len(list_view): list_view.index = current_index
        elif len(list_view) > 0: list_view.index = 0

    # --- Modal Callbacks (Keep as before) ---
    def _create_callback(self, result: tuple | None) -> None: # ... (Keep as before) ...
        if not hasattr(self, 'app'): print("App not available in callback"); return
        if result:
            new_key, new_value = result; list_view, data_dict, file_path = self._get_active_listview_and_data()
            if data_dict is None or file_path is None: self.app.notify("Cannot save: Data source missing.", severity="error"); return
            if new_key in data_dict: self.app.notify(f"Error: Key '{new_key}' exists.", severity="error"); return
            data_dict[new_key] = new_value; save_json(file_path, data_dict); self.app.notify(f"Created '{new_key}'.", title="Success"); self._update_list_view()
            try: # Try select new item
                 for index, item in enumerate(list_view.children):
                      if isinstance(item, ListItem) and item.name == new_key: list_view.index = index; list_view.scroll_to_index(index); break
            except Exception: pass

    def _edit_callback(self, new_value: str | None, item_key: str) -> None: # ... (Keep as before) ...
        if not hasattr(self, 'app'): print("App not available in callback"); return
        if new_value is not None:
             list_view, data_dict, file_path = self._get_active_listview_and_data()
             if data_dict is None or file_path is None: self.app.notify("Cannot save: Data source missing.", severity="error"); return
             if item_key not in data_dict: self.app.notify(f"Error: Item '{item_key}' not found.", severity="error"); self._update_list_view(); return
             data_dict[item_key] = new_value; save_json(file_path, data_dict); self.app.notify(f"Updated '{item_key}'.", title="Success"); self._update_list_view()
             try: # Try re-select
                 for index, item in enumerate(list_view.children):
                      if isinstance(item, ListItem) and item.name == item_key: list_view.index = index; break
             except Exception: pass

    def on_button_pressed(self, event: Button.Pressed) -> None: # ... (Keep as before) ...
        if not hasattr(self, 'app'): return
        list_view, data_dict, _ = self._get_active_listview_and_data()
        if not list_view: self.app.notify("Active list view not found.", severity="error"); return
        if not isinstance(data_dict, dict) or "Error" in data_dict or "_load_error" in data_dict: self.app.notify("Data not loaded correctly.", severity="error"); return
        selected_list_item = list_view.highlighted_child; selected_key = selected_list_item.name if selected_list_item else None
        if event.button.id == "data-create-btn":
            if 'CreateItemScreen' in globals() and CreateItemScreen is not None: self.app.push_screen(CreateItemScreen(self.current_data_tab), self._create_callback)
            else: self.app.notify("Create unavailable.", severity="error")
        elif event.button.id == "data-edit-btn":
            if selected_key:
                 if selected_key in data_dict:
                      initial_value = data_dict[selected_key]
                      if 'EditItemScreen' in globals() and EditItemScreen is not None: self.app.push_screen( EditItemScreen(self.current_data_tab, selected_key, str(initial_value)), lambda value: self._edit_callback(value, selected_key) )
                      else: self.app.notify("Edit unavailable.", severity="error")
                 else: self.app.notify(f"Cannot edit: Key '{selected_key}' not found.", severity="error"); self._update_list_view()
            else: self.app.notify("Please select an item to edit.", severity="warning")
        elif event.button.id == "data-delete-btn":
            if selected_key: handle_data_delete(self.app, self.current_data_tab, selected_key)
            else: self.app.notify("Please select an item to delete.", severity="warning")