# EthicsEngine/dashboard/views/data_mgmt_view.py
import json # Keep json import if needed for potential future use
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal # <-- ContentSwitcher removed
from textual.widgets import (
    Label,
    Button,
    Static,
    ListView,
    ListItem,
    Tabs,
    Tab,
    ContentSwitcher, # <-- ContentSwitcher moved here
    # Placeholder, # Not used here
)
from textual.reactive import reactive
from textual.events import Mount
from textual.message import Message # Keep if custom messages are needed later

# Import helpers, actions, and modals
try:
    from ..dashboard_utils import ( # Use relative import within the dashboard package
        save_json,
        SCENARIOS_FILE,
        GOLDEN_PATTERNS_FILE,
        SPECIES_FILE,
    )
    from ..dashboard_actions import handle_data_delete # Relative import
    from ..dashboard_modals import CreateItemScreen, EditItemScreen # Relative import
except ImportError as e:
     # Provide dummy versions or re-raise if critical
     print(f"ERROR importing dependencies in data_mgmt_view.py: {e}")
     # Define dummy functions/classes if running this file standalone is needed for testing
     def save_json(path, data): print(f"Dummy save_json called for {path}")
     def handle_data_delete(app, data_type, key): print(f"Dummy handle_data_delete called for {key}")
     class CreateItemScreen: pass
     class EditItemScreen: pass
     SCENARIOS_FILE = "dummy_scenarios.json"
     GOLDEN_PATTERNS_FILE = "dummy_models.json"
     SPECIES_FILE = "dummy_species.json"


class DataManagementView(Static):
    """View for managing Scenarios, Models, Species data."""

    # Default tab
    current_data_tab = reactive("Scenarios")

    # Data is passed from the app
    def __init__(self, scenarios: dict, models: dict, species_data: dict, **kwargs):
        super().__init__(**kwargs)
        self.scenarios = scenarios
        self.models = models
        self.species_data = species_data

    def compose(self) -> ComposeResult:
        # Define tabs - IDs should be unique and descriptive
        yield Tabs(
            Tab("Scenarios", id="tab-Scenarios"),
            Tab("Models", id="tab-Models"),
            Tab("Species", id="tab-Species"),
            id="data-tabs"
        )
        # ContentSwitcher switches between different lists based on the active tab
        # The initial value should match the ID of the container for the default tab
        with ContentSwitcher(initial=f"content-{self.current_data_tab.lower()}"):
             # Each section needs a unique ID for the switcher
             with Vertical(id="content-scenarios"):
                 yield Label("Scenarios List:", classes="title")
                 yield ListView(id="scenarios-list")
             with Vertical(id="content-models"):
                 yield Label("Models (Golden Patterns) List:", classes="title")
                 yield ListView(id="models-list")
             with Vertical(id="content-species"):
                 yield Label("Species List:", classes="title")
                 yield ListView(id="species-list")
        # Action buttons at the bottom
        with Horizontal(id="data-actions"):
            yield Button("Create New", id="data-create-btn", variant="success")
            yield Button("Edit Selected", id="data-edit-btn", variant="primary")
            yield Button("Delete Selected", id="data-delete-btn", variant="error")

    def on_mount(self) -> None:
        """Initial setup when the view is mounted."""
        try:
            # Ensure the ContentSwitcher shows the correct initial content
            self.query_one(ContentSwitcher).current = f"content-{self.current_data_tab.lower()}"
        except Exception as e:
            self.app.log.error(f"Error setting initial ContentSwitcher state: {e}")
        # Populate the list for the initially active tab
        self._update_list_view()

    def watch_current_data_tab(self, new_tab_name: str) -> None:
        """Reacts when the current_data_tab reactive variable changes."""
        try:
            # Update the ContentSwitcher to show the content for the new tab
            self.query_one(ContentSwitcher).current = f"content-{new_tab_name.lower()}"
            # Update the list view with data for the new tab
            self._update_list_view()
        except Exception as e:
            self.app.log.error(f"Error watching current_data_tab change: {e}")

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        """Handle activation of a new tab."""
        # Extract the data type from the tab's ID (e.g., "tab-Scenarios" -> "Scenarios")
        new_tab_name = event.tab.id.split("-")[1]
        # Update the reactive variable if the tab has actually changed
        if self.current_data_tab != new_tab_name:
            self.current_data_tab = new_tab_name # This triggers the watcher

    def _get_active_listview_and_data(self):
        """Helper to get the currently active ListView, its corresponding data dict, and file path."""
        # Determine the active tab name (use default if attribute not set yet)
        try:
            current_tab_value = self.current_data_tab
        except AttributeError:
            # Fallback to the default defined in the reactive variable
            current_tab_value = DataManagementView.current_data_tab.default

        active_id_lower = current_tab_value.lower()
        list_view_id = f"#{active_id_lower}-list" # e.g., #scenarios-list

        try:
            list_view = self.query_one(list_view_id, ListView)
        except Exception:
            self.app.log.error(f"Could not find ListView with ID: {list_view_id}")
            return None, None, None # Return None if list view not found

        data_dict = None
        file_path = None

        # Access data stored in the app instance (passed during initialization)
        # Ensure self.app exists (it should in a running Textual app)
        if hasattr(self, 'app'):
            if current_tab_value == "Scenarios":
                data_dict = self.app.scenarios # Assumes app stores loaded data
                file_path = SCENARIOS_FILE
            elif current_tab_value == "Models":
                data_dict = self.app.models
                file_path = GOLDEN_PATTERNS_FILE
            elif current_tab_value == "Species":
                data_dict = self.app.species
                file_path = SPECIES_FILE
        else:
            # Fallback: Access data stored directly on the view instance (less ideal)
            if current_tab_value == "Scenarios": data_dict = self.scenarios
            elif current_tab_value == "Models": data_dict = self.models
            elif current_tab_value == "Species": data_dict = self.species_data

        if data_dict is None:
            self.app.log.error(f"Data dictionary for {current_tab_value} is None.")
        if file_path is None:
             self.app.log.error(f"File path for {current_tab_value} is None.")

        return list_view, data_dict, file_path

    def _update_list_view(self) -> None:
        """Populates the currently active ListView with data."""
        list_view, data_dict, _ = self._get_active_listview_and_data()
        if list_view is None: return # Guard if list view couldn't be found

        # Store current selection index to restore it later
        current_index = list_view.index
        list_view.clear() # Clear previous items

        # Check if data loaded correctly
        if data_dict is None:
            list_view.append(ListItem(Label(f"Error: Data source for {self.current_data_tab} not found.")))
            return
        if not isinstance(data_dict, dict) or "Error" in data_dict or "_load_error" in data_dict:
            fail_message = data_dict.get("Error", data_dict.get("_load_error", "load error")) if isinstance(data_dict, dict) else "unknown load error"
            list_view.append(ListItem(Label(f"Error loading {self.current_data_tab} data: {fail_message}")))
            return
        if not data_dict:
            list_view.append(ListItem(Label(f"No {self.current_data_tab} defined.")))
            return

        # Populate list with data items, sorted by key
        sorted_keys = sorted(data_dict.keys())
        for key in sorted_keys:
            value = data_dict[key]
            # Display key and a truncated value
            display_text = f"{key}: {str(value)[:70]}..." if len(str(value)) > 70 else f"{key}: {value}"
            # Use the key as the name for the ListItem for easy identification
            list_view.append(ListItem(Label(display_text), name=key))

        # Restore selection if possible
        if current_index is not None and current_index < len(list_view):
            list_view.index = current_index
        elif len(list_view) > 0:
            list_view.index = 0 # Select the first item if no previous selection or index out of bounds

    # --- Modal Callbacks ---
    def _create_callback(self, result: tuple | None) -> None:
        """Callback function after the CreateItemScreen is dismissed."""
        if result: # If Save was pressed and result is not None
            new_key, new_value = result
            list_view, data_dict, file_path = self._get_active_listview_and_data()

            if data_dict is None or file_path is None:
                self.app.notify("Cannot save: Data source not available.", severity="error")
                return

            # Prevent overwriting existing keys
            if new_key in data_dict:
                self.app.notify(f"Error: Key '{new_key}' already exists.", severity="error", title="Create Failed")
                return

            # Add new item and save
            data_dict[new_key] = new_value
            save_json(file_path, data_dict)
            self.app.notify(f"Created '{new_key}'.", title="Create Success")
            self._update_list_view() # Refresh the list

            # Try to highlight the newly added item
            for index, item in enumerate(list_view.children):
                 if isinstance(item, ListItem) and item.name == new_key:
                      list_view.index = index
                      list_view.scroll_to_index(index) # Scroll to the new item
                      break

    def _edit_callback(self, new_value: str | None, item_key: str) -> None:
        """Callback function after the EditItemScreen is dismissed."""
        if new_value is not None: # If Save was pressed
             list_view, data_dict, file_path = self._get_active_listview_and_data()

             if data_dict is None or file_path is None:
                 self.app.notify("Cannot save: Data source not available.", severity="error")
                 return
             if item_key not in data_dict:
                 self.app.notify(f"Error: Item '{item_key}' no longer exists.", severity="error")
                 self._update_list_view() # Refresh list in case it changed
                 return

             # Update item and save
             data_dict[item_key] = new_value
             save_json(file_path, data_dict)
             self.app.notify(f"Updated '{item_key}'.", title="Edit Success")
             self._update_list_view() # Refresh the list

             # Try to re-highlight the edited item
             for index, item in enumerate(list_view.children):
                  if isinstance(item, ListItem) and item.name == item_key:
                       list_view.index = index
                       break # No need to scroll if it was likely visible

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses for Create, Edit, Delete."""
        list_view, data_dict, _ = self._get_active_listview_and_data()

        # Basic checks
        if not list_view:
            self.app.notify("Active list view not found.", severity="error")
            return
        if not isinstance(data_dict, dict) or "Error" in data_dict or "_load_error" in data_dict:
            self.app.notify("Data for the current tab is not loaded correctly.", severity="error")
            return

        # Get selected item's key from the ListItem's name attribute
        selected_list_item = list_view.highlighted_child
        selected_key = selected_list_item.name if selected_list_item else None

        # Handle actions
        if event.button.id == "data-create-btn":
            # Check if modal screen is available
            if 'CreateItemScreen' in globals() and CreateItemScreen is not None:
                self.app.push_screen(CreateItemScreen(self.current_data_tab), self._create_callback)
            else:
                self.app.notify("Create functionality is unavailable (Modal not loaded).", severity="error")

        elif event.button.id == "data-edit-btn":
            if selected_key:
                 if selected_key in data_dict:
                      initial_value = data_dict[selected_key]
                      # Check if modal screen is available
                      if 'EditItemScreen' in globals() and EditItemScreen is not None:
                           # Pass callback lambda to handle dismissal
                           self.app.push_screen(
                                EditItemScreen(self.current_data_tab, selected_key, str(initial_value)),
                                lambda value: self._edit_callback(value, selected_key) # Pass key to callback
                           )
                      else:
                           self.app.notify("Edit functionality is unavailable (Modal not loaded).", severity="error")
                 else:
                      self.app.notify(f"Cannot edit: Key '{selected_key}' not found (data may have changed).", severity="error")
                      self._update_list_view() # Refresh list
            else:
                 self.app.notify("Please select an item to edit.", severity="warning")

        elif event.button.id == "data-delete-btn":
            if selected_key:
                # Call the delete handler function (imported from dashboard_actions)
                # Assumes handle_data_delete takes care of confirmation, saving, and refreshing
                handle_data_delete(self.app, self.current_data_tab, selected_key)
            else:
                self.app.notify("Please select an item to delete.", severity="warning")