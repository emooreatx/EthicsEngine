# EthicsEngine/dashboard/views/data_mgmt_view.py
import json
from pathlib import Path
import logging # Import logging
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import (
    Label,
    Button,
    Static,
    ListView,
    ListItem,
    Tabs,
    Tab,
    ContentSwitcher,
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
    # Keep handle_data_delete for Models/Species for now
    from ..dashboard_actions import handle_data_delete
    # Import modals, but note they might need changes for scenario list CRUD
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

    def __init__(self, scenarios: list | dict, models: dict, species_data: dict, **kwargs):
        super().__init__(**kwargs)
        # Scenarios is now expected as a list (or error dict/list)
        self.scenarios = scenarios
        self.models = models
        self.species_data = species_data
        self.log.debug(f"DataManagementView initialized. Scenarios type: {type(self.scenarios)}")

    def compose(self) -> ComposeResult:
        yield Tabs(
            Tab("Scenarios", id="tab-Scenarios"),
            Tab("Models", id="tab-Models"),
            Tab("Species", id="tab-Species"),
            id="data-tabs"
        )
        yield Static(
            "Note: Create/Edit/Delete for Scenarios requires further updates for the list format.",
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
        """Called when the widget is mounted."""
        self.log.debug("DataManagementView mounted.")
        try:
            # Ensure the correct content switcher pane is active
            self.query_one(ContentSwitcher).current = f"content-{self.current_data_tab.lower()}"
        except Exception as e: self.log.error(f"Error setting initial ContentSwitcher: {e}", exc_info=True)
        # Populate the list for the initially active tab
        self._update_list_view()

    def watch_current_data_tab(self, new_tab_name: str) -> None:
        """Switch content and update list when the active tab changes."""
        self.log.debug(f"Data tab changed to: {new_tab_name}")
        try:
            self.query_one(ContentSwitcher).current = f"content-{new_tab_name.lower()}"
            self._update_list_view() # Update the list view for the new tab
        except Exception as e: self.log.error(f"Error watching current_data_tab: {e}", exc_info=True)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        """Update the reactive variable when a tab is clicked."""
        new_tab_name = event.tab.id.split("-")[1] # e.g., "Scenarios"
        self.log.debug(f"Tab activated: {new_tab_name}")
        # This will trigger the watch_current_data_tab method if the value changes
        self.current_data_tab = new_tab_name

    def _get_active_listview_and_data(self):
        """Gets the currently active ListView, its corresponding data source, and file path."""
        active_tab_name = self.current_data_tab
        list_view_id = f"#{active_tab_name.lower()}-list"
        data_source = None
        file_path = None

        try:
            list_view = self.query_one(list_view_id, ListView)
        except Exception:
            self.log.error(f"Could not find ListView with ID: {list_view_id}")
            return None, None, None

        # Get data source from the view's attributes (passed from the app)
        if active_tab_name == "Scenarios":
            data_source = self.scenarios # Should be a list or error dict/list
            file_path = SCENARIOS_FILE
        elif active_tab_name == "Models":
            data_source = self.models # Should be a dict or error dict
            file_path = GOLDEN_PATTERNS_FILE
        elif active_tab_name == "Species":
            data_source = self.species_data # Should be a dict or error dict
            file_path = SPECIES_FILE

        if data_source is None: self.log.error(f"Data source for {active_tab_name} is None.")
        if file_path is None: self.log.error(f"File path for {active_tab_name} is None.")

        self.log.debug(f"Active tab: {active_tab_name}, ListView: {list_view_id}, Data type: {type(data_source)}")
        return list_view, data_source, file_path

    def _update_list_view(self) -> None:
        """Populates the active ListView based on the current tab."""
        list_view, data_source, _ = self._get_active_listview_and_data()
        if list_view is None:
            self.log.error("Cannot update list view: ListView not found.")
            return

        current_index = list_view.index # Preserve selection if possible
        list_view.clear()

        # --- Helper to truncate text ---
        def _truncate(text, length=70):
            text_str = str(text).replace('\n', ' ').strip()
            return text_str if len(text_str) <= length else text_str[:length-1] + "\u2026" # Ellipsis

        # --- Handle Scenarios (List Format) ---
        if self.current_data_tab == "Scenarios":
            self.log.debug(f"Updating Scenarios list. Data type: {type(data_source)}")
            if isinstance(data_source, list):
                if not data_source:
                    list_view.append(ListItem(Label("No Scenarios defined.")))
                else:
                    for item in data_source:
                        if isinstance(item, dict) and "id" in item:
                            item_id = item.get("id", "NO_ID")
                            prompt = item.get("prompt", "")
                            label_text = f"{item_id}: {_truncate(prompt)}"
                            # Set the 'name' attribute to the ID for later retrieval
                            list_view.append(ListItem(Label(escape(label_text)), name=str(item_id)))
                        elif isinstance(item, dict) and ("LOAD_ERROR" in item.get("id", "") or "FORMAT_ERROR" in item.get("id", "")):
                             # Handle dummy error items created in App.__init__
                             list_view.append(ListItem(Label(escape(item.get("prompt", "Unknown load error")))))
                        else:
                             list_view.append(ListItem(Label(f"Invalid item format: {escape(str(item))}")))
            elif isinstance(data_source, dict) and ("Error" in data_source or "_load_error" in data_source):
                 # Handle case where load_json returned an error dict initially
                 fail_message = data_source.get("Error", data_source.get("_load_error", "load error"))
                 list_view.append(ListItem(Label(f"Error loading Scenarios: {escape(fail_message)}")))
            else:
                 # Handle unexpected format
                 list_view.append(ListItem(Label(f"Error: Expected list for Scenarios, got {escape(str(type(data_source)))}")))

        # --- Handle Models and Species (Dict Format) ---
        else:
            self.log.debug(f"Updating {self.current_data_tab} list (expecting dict). Data type: {type(data_source)}")
            if not isinstance(data_source, dict) or "Error" in data_source or "_load_error" in data_source:
                fail_message = data_source.get("Error", data_source.get("_load_error", "load error")) if isinstance(data_source, dict) else "unknown error"
                list_view.append(ListItem(Label(f"Error loading {self.current_data_tab}: {escape(fail_message)}")))
            elif not data_source:
                list_view.append(ListItem(Label(f"No {self.current_data_tab} defined.")))
            else:
                # Sort by key for consistent order
                sorted_keys = sorted(data_source.keys())
                for key in sorted_keys:
                    value = data_source[key]
                    display_text = f"{key}: {_truncate(value)}"
                    # Set the 'name' attribute to the key for later retrieval
                    list_view.append(ListItem(Label(escape(display_text)), name=key))

        # Try to restore selection
        if current_index is not None and 0 <= current_index < len(list_view):
            list_view.index = current_index
        elif len(list_view) > 0:
            list_view.index = 0 # Select first item if possible

    # --- Modal Callbacks (Placeholders for Scenario List CRUD) ---
    def _create_callback(self, result: tuple | None) -> None:
        """Callback after attempting to create an item."""
        if not hasattr(self, 'app'): self.log.error("App not available in create callback"); return
        if not result: return # User cancelled

        new_key, new_value = result
        list_view, data_source, file_path = self._get_active_listview_and_data()

        if data_source is None or file_path is None:
            self.app.notify("Cannot save: Data source missing.", severity="error"); return

        if self.current_data_tab == "Scenarios":
            # --- TODO: Implement Scenario List Create Logic ---
            self.log.warning("Scenario list creation not implemented yet.")
            self.app.notify("Scenario creation from UI not yet supported for list format.", severity="warning", timeout=6)
            # Placeholder logic:
            # 1. Check if ID (new_key) already exists in the list
            # 2. Create new scenario dict: {"id": new_key, "prompt": new_value, "tags": [], "evaluation_criteria": {}}
            # 3. Append to self.scenarios list (data_source)
            # 4. save_json(file_path, data_source)
            # 5. self._update_list_view()
            # 6. Try to select the new item
            pass
        else: # Handle Models and Species (Dict format)
            if not isinstance(data_source, dict):
                 self.app.notify(f"Cannot save: Data source for {self.current_data_tab} is not a dictionary.", severity="error"); return
            if new_key in data_source:
                self.app.notify(f"Error: Key '{new_key}' already exists.", severity="error"); return
            data_source[new_key] = new_value
            save_json(file_path, data_source)
            self.app.notify(f"Created '{new_key}'.", title="Success");
            self._update_list_view()
            # Try select new item
            try:
                 for index, item in enumerate(list_view.children):
                      if isinstance(item, ListItem) and item.name == new_key: list_view.index = index; list_view.scroll_to_index(index); break
            except Exception: pass

    def _edit_callback(self, new_value: str | None, item_key: str) -> None:
        """Callback after attempting to edit an item."""
        if not hasattr(self, 'app'): self.log.error("App not available in edit callback"); return
        if new_value is None: return # User cancelled

        list_view, data_source, file_path = self._get_active_listview_and_data()

        if data_source is None or file_path is None:
            self.app.notify("Cannot save: Data source missing.", severity="error"); return

        if self.current_data_tab == "Scenarios":
             # --- TODO: Implement Scenario List Edit Logic ---
             self.log.warning("Scenario list editing not implemented yet.")
             self.app.notify("Scenario editing from UI not yet supported for list format.", severity="warning", timeout=6)
             # Placeholder logic:
             # 1. Find the dictionary in the list `data_source` where item['id'] == item_key
             # 2. If found, update its 'prompt' field (or others if modal is enhanced) to new_value
             # 3. save_json(file_path, data_source)
             # 4. self._update_list_view()
             # 5. Try to re-select the edited item
             pass
        else: # Handle Models and Species (Dict format)
             if not isinstance(data_source, dict):
                  self.app.notify(f"Cannot save: Data source for {self.current_data_tab} is not a dictionary.", severity="error"); return
             if item_key not in data_source:
                 self.app.notify(f"Error: Item '{item_key}' not found.", severity="error"); self._update_list_view(); return
             data_source[item_key] = new_value
             save_json(file_path, data_source)
             self.app.notify(f"Updated '{item_key}'.", title="Success");
             self._update_list_view()
             # Try re-select
             try:
                 for index, item in enumerate(list_view.children):
                      if isinstance(item, ListItem) and item.name == item_key: list_view.index = index; break
             except Exception: pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle Create, Edit, Delete button presses."""
        if not hasattr(self, 'app'): return # Should not happen in normal operation

        list_view, data_source, _ = self._get_active_listview_and_data()
        if not list_view: self.app.notify("Active list view not found.", severity="error"); return

        # Check for load errors before proceeding with actions
        is_error = False
        if self.current_data_tab == "Scenarios":
             # Check if it's the dummy error list/dict
             if isinstance(data_source, list) and data_source and isinstance(data_source[0], dict) and ("LOAD_ERROR" in data_source[0].get("id", "") or "FORMAT_ERROR" in data_source[0].get("id", "")): is_error = True
             elif isinstance(data_source, dict) and ("Error" in data_source or "_load_error" in data_source): is_error = True
        elif not isinstance(data_source, dict) or "Error" in data_source or "_load_error" in data_source:
             is_error = True

        if is_error:
             self.app.notify(f"Data for {self.current_data_tab} not loaded correctly. Cannot perform actions.", severity="error"); return

        selected_list_item = list_view.highlighted_child
        # The 'name' attribute holds the key (for dicts) or ID (for scenario list)
        selected_key_or_id = selected_list_item.name if selected_list_item else None

        if event.button.id == "data-create-btn":
            # Note: CreateItemScreen expects key/value. Needs update for scenario list structure.
            if 'CreateItemScreen' in globals() and CreateItemScreen is not None:
                 if self.current_data_tab == "Scenarios":
                      self.app.notify("Scenario creation from UI needs update for list format.", severity="warning", timeout=6)
                      # Optionally, could launch a simplified modal asking only for ID and Prompt
                      # self.app.push_screen(CreateItemScreen(self.current_data_tab), self._create_callback)
                 else:
                      self.app.push_screen(CreateItemScreen(self.current_data_tab), self._create_callback)
            else: self.app.notify("Create action unavailable.", severity="error")

        elif event.button.id == "data-edit-btn":
            if selected_key_or_id:
                 initial_value = ""
                 if self.current_data_tab == "Scenarios":
                      # Find prompt for the selected ID
                      found = False
                      if isinstance(data_source, list):
                           for item in data_source:
                                if isinstance(item, dict) and item.get("id") == selected_key_or_id:
                                     initial_value = item.get("prompt", "")
                                     found = True
                                     break
                      if not found:
                           self.app.notify(f"Cannot edit: Scenario ID '{selected_key_or_id}' not found.", severity="error"); return
                      self.app.notify("Scenario editing from UI needs update for list format.", severity="warning", timeout=6)
                      # Optionally, launch modal pre-filled with prompt
                      # if 'EditItemScreen' in globals() and EditItemScreen is not None:
                      #      self.app.push_screen( EditItemScreen(self.current_data_tab, selected_key_or_id, str(initial_value)), lambda value: self._edit_callback(value, selected_key_or_id) )
                      # else: self.app.notify("Edit action unavailable.", severity="error")

                 elif isinstance(data_source, dict) and selected_key_or_id in data_source:
                      initial_value = data_source[selected_key_or_id]
                      if 'EditItemScreen' in globals() and EditItemScreen is not None:
                           self.app.push_screen( EditItemScreen(self.current_data_tab, selected_key_or_id, str(initial_value)), lambda value: self._edit_callback(value, selected_key_or_id) )
                      else: self.app.notify("Edit action unavailable.", severity="error")
                 else:
                      self.app.notify(f"Cannot edit: Key '{selected_key_or_id}' not found.", severity="error"); self._update_list_view()
            else:
                 self.app.notify("Please select an item to edit.", severity="warning")

        elif event.button.id == "data-delete-btn":
            if selected_key_or_id:
                 if self.current_data_tab == "Scenarios":
                     # --- TODO: Implement Scenario List Delete Logic ---
                     self.log.warning("Scenario list deletion not implemented yet.")
                     self.app.notify("Scenario deletion from UI not yet supported for list format.", severity="warning", timeout=6)
                     # Placeholder logic:
                     # 1. Find index of item in list `data_source` where item['id'] == selected_key_or_id
                     # 2. If found, remove item using `data_source.pop(index)`
                     # 3. save_json(file_path, data_source)
                     # 4. self._update_list_view()
                     pass
                 else: # Handle Models and Species (Dict format)
                     # Use the existing dashboard_actions helper for dicts
                     handle_data_delete(self.app, self.current_data_tab, selected_key_or_id)
            else:
                 self.app.notify("Please select an item to delete.", severity="warning")

