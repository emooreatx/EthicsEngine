# EthicsEngine/dashboard/views/results_browser_view.py
import json
import os
from pathlib import Path
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, ListView, ListItem, Label, Markdown
from textual.reactive import reactive
from textual.events import Mount

# Import helpers
try:
    # Use relative import within the dashboard package
    from ..dashboard_utils import load_json, RESULTS_DIR
except ImportError as e:
    print(f"ERROR importing dashboard_utils in results_browser_view.py: {e}")
    # Define dummy RESULTS_DIR if needed for standalone testing
    RESULTS_DIR = Path("./dummy_results")
    def load_json(path, default=None): return {"Error": f"Dummy load_json called for {path}"}

class ResultsBrowserView(Static):
    """View for Browse and displaying past result files."""

    selected_file = reactive(None) # Stores the name of the currently selected file

    def compose(self) -> ComposeResult:
        with Horizontal():
             # Container for the file list
             with Vertical(id="results-file-list-container", classes="browser-list-container"):
                 yield Label("Past Result Files (Newest First):", classes="title")
                 yield ListView(id="results-browser-list") # List to display filenames
             # Container for displaying the content of the selected file
             with VerticalScroll(id="results-content-container", classes="browser-content-container"):
                 yield Markdown("Select a file to view results", id="results-browser-content") # Markdown widget for content

    def on_mount(self) -> None:
        """Called when the view is mounted. Populates the file list."""
        self._populate_file_list()

    def _scan_results_dir(self) -> list[str]:
        """Scans the RESULTS_DIR for .json files and returns sorted filenames."""
        if not RESULTS_DIR.exists() or not RESULTS_DIR.is_dir():
            self.app.log.warning(f"Results directory not found: {RESULTS_DIR}")
            return []
        try:
            # Get all .json files, sort by modification time (newest first)
            files = sorted(
                RESULTS_DIR.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            return [f.name for f in files] # Return only the filenames
        except Exception as e:
            self.app.log.error(f"Error scanning results directory {RESULTS_DIR}: {e}")
            return []

    def _populate_file_list(self) -> None:
        """Populates the ListView with result filenames."""
        try:
            list_view = self.query_one("#results-browser-list", ListView)
            list_view.clear() # Clear existing items
            result_files = self._scan_results_dir()

            if not result_files:
                list_view.append(ListItem(Label("No result files found.")))
            else:
                for filename in result_files:
                    # Use filename as the name for the ListItem for easy retrieval
                    list_view.append(ListItem(Label(filename), name=filename))
        except Exception as e:
             self.app.log.error(f"Failed to populate results file list: {e}")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle selection changes in the file list."""
        # Ensure the event is from the correct ListView
        if event.list_view.id == "results-browser-list" and event.item is not None:
             # Get the filename from the selected ListItem's name attribute
             filename = event.item.name
             self.selected_file = filename # Update the reactive variable

    # Watcher for the selected_file reactive variable
    def watch_selected_file(self, filename: str | None) -> None:
        """Updates the content view when selected_file changes."""
        try:
            content_display = self.query_one("#results-browser-content", Markdown)
        except Exception as e:
            self.app.log.error(f"Cannot find results browser content display: {e}")
            return

        if not filename:
            content_display.update("Select a file to view results")
            return

        filepath = RESULTS_DIR / filename
        self.app.notify(f"Loading {filename}...") # Show loading notification

        # Load JSON data from the selected file
        data = load_json(filepath, default_data={"Error": f"File {filename} could not be loaded."})

        # Check for loading errors indicated within the loaded data
        if isinstance(data, dict) and ("Error" in data or "_load_error" in data):
            error_msg = data.get("Error", data.get("_load_error", "Could not load file content"))
            content_display.update(f"# Error Loading {filename}\n\n```\n{error_msg}\n```")
            self.app.notify(f"Error loading {filename}", severity="error", title="Load Error")
            return

        # Try to format and display the JSON data
        try:
             # Convert Python object back to formatted JSON string
             formatted_json = json.dumps(data, indent=2)
             # Update the Markdown widget with the formatted JSON inside a code block
             content_display.update(f"### {filename}\n\n```json\n{formatted_json}\n```")
             self.app.notify(f"Displayed {filename}.", title="Result Loaded")
             # Scroll to top after loading new content
             self.query_one("#results-content-container", VerticalScroll).scroll_home(animate=False)
        except Exception as e:
             # Handle errors during JSON formatting or Markdown update
             error_msg = f"Could not display content: {e}"
             content_display.update(f"# Error Displaying {filename}\n\n```\n{error_msg}\n```")
             self.app.notify(f"Error displaying {filename}: {e}", severity="error")