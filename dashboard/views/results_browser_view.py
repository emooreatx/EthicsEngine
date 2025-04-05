# EthicsEngine/dashboard/views/results_browser_view.py
"""
Provides a Textual view for browsing and inspecting JSON result files.

Features:
- Lists result files from the designated results directory, sorted by modification time.
- Displays formatted metadata of the selected file.
- Presents results in a DataTable for scenarios and benchmarks.
- Shows detailed information (including reasoning trees) for selected table rows in a Markdown view.
- Includes a button to upload the selected result file to a predefined AWS endpoint.
"""
import json
import os
import logging
from pathlib import Path
from datetime import datetime

# --- Textual Imports ---
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import (
    Static, Label, Button, DataTable, Markdown, DirectoryTree, Pretty
)
from textual.reactive import reactive
from textual.message import Message

# --- Project Imports ---
try:
    from ..dashboard_utils import RESULTS_DIR, load_json
    # Assuming an upload function exists, potentially in dashboard_actions or a dedicated module
    # from ..dashboard_actions import upload_result_file
except ImportError as e:
    # Fallback logging and dummy definitions if imports fail
    logger = logging.getLogger("ResultsBrowser_Fallback")
    logger.error(f"ERROR importing dependencies in results_browser_view.py: {e}")
    RESULTS_DIR = Path("./results") # Dummy path
    def load_json(path, default=None): return {"Error": f"Dummy load_json called for {path}"}
    # def upload_result_file(filepath): print(f"Dummy upload_result_file called for {filepath}")

# --- Main View Class ---

class ResultsBrowserView(Static):
    """
    A view widget for browsing, inspecting, and uploading result JSON files.
    """

    # Reactive property to store the content of the selected result file
    selected_result_data = reactive(None)
    # Reactive property to store the path of the selected file
    selected_file_path = reactive(None)

    def __init__(self, **kwargs):
        """Initializes the ResultsBrowserView."""
        super().__init__(**kwargs)
        self.logger = logging.getLogger(__name__)
        self.logger.info("ResultsBrowserView initialized.")
        # Ensure results directory exists
        if not RESULTS_DIR.exists():
            try:
                RESULTS_DIR.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"Created results directory: {RESULTS_DIR}")
            except OSError as e:
                self.logger.error(f"Failed to create results directory {RESULTS_DIR}: {e}")


    def compose(self) -> ComposeResult:
        """Creates the UI structure for the Results Browser view."""
        self.logger.debug("Composing ResultsBrowserView UI...")
        yield Label("Results Browser (Placeholder)") # Simple placeholder
        # TODO: Implement full UI with DirectoryTree, DataTable, Markdown, Button etc.
        # Example structure:
        # with Horizontal():
        #     with Vertical(id="results-file-list"):
        #         yield Label("Result Files:")
        #         yield DirectoryTree(RESULTS_DIR, id="results-dir-tree")
        #     with Vertical(id="results-details"):
        #         yield Label("File Metadata:", id="metadata-label")
        #         yield Pretty("", id="metadata-display") # Display metadata nicely
        #         yield Label("Results:", id="results-table-label")
        #         yield DataTable(id="results-data-table")
        #         yield Label("Details:", id="details-label")
        #         yield Markdown("", id="details-markdown-view")
        #         yield Button("Upload Result", id="upload-button", disabled=True)
        self.logger.debug("ResultsBrowserView UI composed.")

    # --- Add methods for handling DirectoryTree selection, populating table/markdown, upload ---
    # Example:
    # def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected):
    #     # Load JSON, update selected_file_path, selected_result_data
    #     # Populate metadata, table, enable upload button
    #     pass

    # def watch_selected_result_data(self, data):
    #     # Update metadata display, populate DataTable
    #     pass

    # def on_data_table_row_selected(self, event: DataTable.RowSelected):
    #     # Extract row data, format for Markdown, update Markdown view
    #     pass

    # def on_button_pressed(self, event: Button.Pressed):
    #     # If upload button, call upload function with self.selected_file_path
    #     pass
