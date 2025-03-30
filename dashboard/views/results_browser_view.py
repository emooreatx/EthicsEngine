# EthicsEngine/dashboard/views/results_browser_view.py
import json
import os
import logging
from pathlib import Path
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, ListView, ListItem, Label, Markdown, DataTable # Added DataTable
from textual.reactive import reactive
from textual.events import Mount, Click # Import Click event
from textual.message import Message
from textual.markup import escape # Import the escape function


# Import Helpers and Logger
try:
    from ..dashboard_utils import load_json, RESULTS_DIR
except ImportError as e:
    print(f"ERROR importing dashboard_utils: {e}")
    RESULTS_DIR = Path("./dummy_results")
    def load_json(path, default=None): return {"Error": f"Dummy load: {path}", "_load_error": True}

try:
    from config.config import logger
except ImportError:
    print("ERROR: Could not import logger from config.config. Using basic logger.")
    logger = logging.getLogger("ResultsBrowserView_Fallback")
    # logging.basicConfig(level=logging.DEBUG) # Example basic config if needed

# --- ResultsBrowserView Class ---
class ResultsBrowserView(Static):
    """View for Browse and displaying past result files using a table and detail view."""

    selected_file = reactive(None)
    _current_loaded_data = reactive(None, repaint=False)
    _current_results_list = reactive(None, repaint=False)

    log = logger

    def compose(self) -> ComposeResult:
        self.log.debug("Composing ResultsBrowserView")
        try:
            with Horizontal(): # Needs height definition from CSS
                with Vertical(id="results-file-list-container", classes="browser-list-container"): # Needs CSS
                    yield Label("Past Result Files (Newest First):", classes="title")
                    yield ListView(id="results-browser-list")
                with VerticalScroll(id="results-content-container", classes="browser-content-container"): # Needs CSS
                    yield Static("Select a file to view metadata.", id="results-browser-metadata", classes="metadata-display")
                    yield Label("Results Summary:", classes="title", id="results-browser-table-title")
                    yield DataTable(id="results-browser-table", show_header=True, show_cursor=True, zebra_stripes=True)
                    yield Label("Details (Select Row Above):", classes="title", id="results-browser-detail-title")
                    yield Markdown(id="results-browser-detail-markdown")
        except Exception as e:
            self.log.exception(f"Error during ResultsBrowserView compose: {e}")
            yield Static(f"Error composing ResultsBrowserView: {escape(str(e))}")


    def on_mount(self) -> None:
        """Called when the view is mounted."""
        self.log.debug("Mounting ResultsBrowserView")
        try:
            self.query_one("#results-browser-table-title").display = False
            self.query_one("#results-browser-detail-title").display = False
            self.query_one("#results-browser-detail-markdown").update("Select a file from the list.")
            self._populate_file_list()
        except Exception as e:
             self.log.error(f"Error during on_mount: {e}", exc_info=True)
             try:
                  metadata_widget = self.query_one("#results-browser-metadata", Static)
                  metadata_widget.update(f"Error during view mount: {escape(str(e))}")
             except Exception as query_e:
                  self.log.error(f"Could not query metadata widget during on_mount error handling: {query_e}")


    def _scan_results_dir(self) -> list[str]:
        """Scans the RESULTS_DIR for .json files."""
        self.log.debug(f"Scanning results directory: {RESULTS_DIR.absolute()}")
        if not RESULTS_DIR.exists() or not RESULTS_DIR.is_dir():
            self.log.warning(f"Results directory not found or not a directory: {RESULTS_DIR}")
            return []
        try:
            files = sorted(
                RESULTS_DIR.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            filenames = [f.name for f in files]
            self.log.debug(f"Found {len(filenames)} result files.")
            return filenames
        except PermissionError as pe:
             self.log.error(f"Permission error scanning results directory {RESULTS_DIR}: {pe}")
             return []
        except Exception as e:
            self.log.error(f"Error scanning results directory {RESULTS_DIR}: {e}", exc_info=True)
            return []

    def _populate_file_list(self) -> None:
        """Populates the ListView with result filenames."""
        self.log.debug("Populating file list")
        try:
            list_view = self.query_one("#results-browser-list", ListView)
            list_view.clear()
            result_files = self._scan_results_dir()

            if not result_files:
                self.log.info("No result files found.")
                list_view.append(ListItem(Label("No result files found.")))
            else:
                self.log.info(f"Populating list with {len(result_files)} files.")
                for filename in result_files:
                    list_view.append(ListItem(Label(escape(filename)), name=filename))
            list_view.index = 0 if result_files else None
        except Exception as e:
             self.log.error(f"Failed to populate results file list: {e}", exc_info=True)
             try:
                  list_view = self.query_one("#results-browser-list", ListView)
                  list_view.clear()
                  list_view.append(ListItem(Label(f"Error populating list: {escape(str(e))}")))
             except Exception as query_e:
                  self.log.error(f"Could not query list view during populate error handling: {query_e}")


    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle selection changes in the file list."""
        self.log.debug(f"ListView selection event: {event.item}")
        if event.list_view.id == "results-browser-list" and event.item is not None:
             filename = getattr(event.item, 'name', None)
             if filename:
                  self.log.info(f"File selected via ListView: {filename}")
                  self.selected_file = filename # Triggers watch_selected_file

    def _truncate(self, text, length=50):
        """Truncates text for display in table cells."""
        text_str = str(text).replace('\n', ' ').replace('\r', '')
        if len(text_str) > length:
            return text_str[:length-1] + "\u2026" # Ellipsis
        return text_str

    def watch_selected_file(self, filename: str | None) -> None:
        """Loads file, updates metadata display, and populates the results table."""
        self.log.debug(f"Watcher triggered for selected_file: {filename}")
        try:
            metadata_display = self.query_one("#results-browser-metadata", Static)
            results_table = self.query_one("#results-browser-table", DataTable)
            detail_markdown = self.query_one("#results-browser-detail-markdown", Markdown)
            table_title = self.query_one("#results-browser-table-title")
            detail_title = self.query_one("#results-browser-detail-title")
            content_scroll = self.query_one("#results-content-container", VerticalScroll)
        except Exception as e:
            self.log.error(f"Cannot find results browser widgets in watcher: {e}", exc_info=True)
            return

        # Clear previous state
        results_table.clear(columns=True)
        detail_markdown.update("")
        metadata_display.update("")
        table_title.display = False
        detail_title.display = False
        self._current_loaded_data = None
        self._current_results_list = None

        if not filename:
            metadata_display.update("Select a file from the list.")
            return

        filepath = RESULTS_DIR / filename
        self.log.info(f"Loading results file: {filepath}")
        if hasattr(self, 'app') and self.app: self.app.notify(f"Loading {filename}...")

        loaded_data = load_json(filepath, default_data={"Error": f"File {filename} could not be loaded.", "_load_error": True})
        self._current_loaded_data = loaded_data

        # Error Handling... (same as before)
        if not isinstance(loaded_data, dict) or ("Error" in loaded_data or "_load_error" in loaded_data):
            error_msg = loaded_data.get("Error", "Could not load or parse file content") if isinstance(loaded_data, dict) else "Invalid file content"
            metadata_display.update(f"**Error Loading {escape(filename)}:**\n\n```\n{escape(error_msg)}\n```")
            if hasattr(self, 'app') and self.app: self.app.notify(f"Error loading {filename}", severity="error", title="Load Error")
            return
        elif "metadata" not in loaded_data or "results" not in loaded_data:
            self.log.warning(f"File {filename} does not match new metadata/results structure. Displaying raw.")
            metadata_display.update(f"**Warning:** File format may be outdated or incorrect. Displaying raw content.")
            try:
                 formatted_json = json.dumps(loaded_data, indent=2)
                 detail_markdown.update(f"```json\n{escape(formatted_json)}\n```")
                 detail_title.display = True
            except Exception as e:
                 detail_markdown.update(f"```\nError displaying raw content: {escape(str(e))}\n```")
            return

        # --- Process New Format ---
        self.log.debug("Processing new file format")
        metadata = loaded_data.get("metadata", {})
        results_data = loaded_data.get("results")
        self._current_results_list = results_data

        # 1. Update Metadata Display
        # ... (metadata display logic same) ...
        metadata_md = f"**File:** {escape(filename)}\n"
        for key, value in metadata.items():
             key_title = escape(key.replace('_', ' ').title())
             val_str = "..."
             try:
                 if isinstance(value, (list, dict)):
                     if key == 'llm_config' and isinstance(value, list) and value:
                         val_str = escape(f"{value[0].get('model', 'N/A')}")
                     elif isinstance(value, list):
                         val_str = f"\\[{len(value)} items\\]"
                     elif isinstance(value, dict):
                         keys_str = escape(", ".join(value.keys()))
                         val_str = escape(f"{len(value)} keys: ") + keys_str
                         val_str = self._truncate(val_str, 100)
                     else:
                         val_str = escape(self._truncate(str(value), 100))
                 else:
                     val_str = escape(self._truncate(str(value), 100))
             except Exception as fmt_e:
                 self.log.error(f"Error formatting metadata key '{key}': {fmt_e}")
                 val_str = "[Error formatting value]"
             metadata_md += f"**{key_title}:** {val_str}\n"
        metadata_display.update(metadata_md)

        # 2. Populate Results Table
        # ... (table population logic same) ...
        results_table.clear(columns=True)
        run_type = metadata.get("run_type")
        table_title.display = True
        detail_title.display = True
        detail_markdown.update("Select a row from the table above to see details.")

        def add_row_safely(table, *cells, key):
            try:
                str_cells = [str(cell) for cell in cells]
                table.add_row(*str_cells, key=key)
            except Exception as table_e:
                self.log.error(f"Failed to add row to table (key={key}): {table_e}", exc_info=True)

        if run_type == "benchmark" and isinstance(results_data, list):
            self.log.debug("Populating benchmark results table")
            results_table.add_columns("QID", "Question", "Expected", "Response", "Evaluation")
            results_table.fixed_columns = 1
            for item in results_data:
                if isinstance(item, dict):
                     qid = item.get("question_id", "N/A")
                     add_row_safely(results_table, qid, self._truncate(item.get("question", "")), self._truncate(item.get("expected_answer", "")), self._truncate(item.get("response", "")), self._truncate(item.get("evaluation", "")), key=str(qid))
                else: self.log.warning(f"Skipping non-dict item in benchmark results: {item}")

        elif run_type == "scenario_pipeline" and isinstance(results_data, list):
            self.log.debug("Populating scenario pipeline results table")
            results_table.add_columns("ID", "Scenario Text", "Planner", "Executor", "Judge")
            results_table.fixed_columns = 1
            for item in results_data:
                if isinstance(item, dict):
                     sid = item.get("scenario_id", "N/A")
                     add_row_safely(results_table, sid, self._truncate(item.get("scenario_text", "")), self._truncate(item.get("planner_output", "")), self._truncate(item.get("executor_output", "")), self._truncate(item.get("judge_output", "")), key=str(sid))
                else: self.log.warning(f"Skipping non-dict item in scenario_pipeline results: {item}")

        elif run_type == "scenario" and isinstance(results_data, dict):
             self.log.debug("Populating old scenario format results table")
             results_table.add_columns("Role", "Scenario IDs")
             results_table.fixed_columns = 1
             for role, outcomes in results_data.items():
                 ids = ", ".join(outcomes.keys()) if isinstance(outcomes, dict) else "Invalid data"
                 add_row_safely(results_table, escape(role.title()), self._truncate(ids, 100), key=role)
             detail_markdown.update("Select a file. Row details not available for this results format.")
             detail_title.display = False
        else:
            self.log.warning(f"Unknown or empty results format. Run type: {run_type}, Data type: {type(results_data)}")
            results_table.add_column("Info")
            add_row_safely(results_table, f"No results found or unknown format in 'results' field.", key="info")
            detail_markdown.update("")
            detail_title.display = False

        try:
             content_scroll.scroll_home(animate=False)
        except Exception as scroll_e:
             self.log.warning(f"Could not scroll content container to top: {scroll_e}")

        if hasattr(self, 'app') and self.app: self.app.notify(f"Loaded data for {filename}.", title="File Loaded")


    # --- FIX: Use row_key.value in comparison ---
    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        """Update the detail markdown view when a cell is selected in the results table."""
        self.log.warning(f"--- HANDLING CELL SELECTION (on_data_table_cell_selected) ---")
        self.log.debug(f"Cell selected: cell_key='{event.cell_key}', value='{event.value}', table_id='{event.control.id}'")

        if not event.cell_key or event.cell_key.row_key is None:
             self.log.warning("Cell selection event missing row key object.")
             return

        # --- FIX: Extract the *value* from the RowKey object ---
        row_key_obj = event.cell_key.row_key
        try:
             # Assuming RowKey has a .value attribute holding the original key
             lookup_key = str(row_key_obj.value)
             self.log.debug(f"Extracted lookup_key: '{lookup_key}' (type: {type(lookup_key)}) from RowKey object")
        except AttributeError:
             self.log.error(f"Could not get '.value' from RowKey object: {row_key_obj}. Cannot lookup details.")
             # Update detail view with error
             try:
                  detail_markdown = self.query_one("#results-browser-detail-markdown", Markdown)
                  detail_markdown.update(f"Error: Could not extract key value from table selection.")
             except Exception: pass # Ignore if query fails
             return
        # --- END FIX ---

        try:
            detail_markdown = self.query_one("#results-browser-detail-markdown", Markdown)
            content_scroll = self.query_one("#results-content-container", VerticalScroll)
        except Exception as e:
            self.log.error(f"Cannot find detail markdown/scroll widget in cell selection handler: {e}", exc_info=True)
            return

        if self._current_results_list is None:
            self.log.warning("Current results list is None, cannot load details.")
            if isinstance(self._current_loaded_data, dict) and self._current_loaded_data.get("results"):
                 self.log.debug("Re-assigning _current_results_list from _current_loaded_data.")
                 self._current_results_list = self._current_loaded_data.get("results")
            else:
                 detail_markdown.update("Could not load details for selected row (results data not available).")
                 return

        selected_item_data = None
        run_type = None
        if isinstance(self._current_loaded_data, dict) and "metadata" in self._current_loaded_data:
            run_type = self._current_loaded_data.get("metadata", {}).get("run_type")
            self.log.debug(f"Determined run_type: '{run_type}'")
        else:
             self.log.warning("Could not determine run_type from loaded data.")

        # Find the selected item's full data using the corrected lookup_key
        try:
            if run_type in ["benchmark", "scenario_pipeline"] and isinstance(self._current_results_list, list):
                key_to_match = "question_id" if run_type == "benchmark" else "scenario_id"
                self.log.debug(f"Searching for item with {key_to_match} == '{lookup_key}' in list of {len(self._current_results_list)} items")
                found = False
                for index, item in enumerate(self._current_results_list):
                     if isinstance(item, dict):
                          item_key_val = item.get(key_to_match)
                          # --- FIX: Compare item's key value with the extracted lookup_key ---
                          if str(item_key_val) == lookup_key: # Compare string forms
                              selected_item_data = item
                              self.log.info(f"Found item at index {index}: ID={item_key_val}")
                              found = True
                              break
                     else:
                          self.log.warning(f"Item {index} in results list is not a dict: {item}")
                if not found: self.log.warning(f"Item with {key_to_match} == '{lookup_key}' not found in list.")
            elif run_type == "scenario" and isinstance(self._current_results_list, dict):
                 # For role-based results, the row_key value *should* be the role string
                 selected_item_data = self._current_results_list.get(lookup_key)
                 if selected_item_data:
                      self.log.info(f"Found data for role '{lookup_key}'")
                 else:
                      self.log.warning(f"Data for role '{lookup_key}' not found in dict.")
            else:
                 self.log.warning(f"Cannot determine how to find selected item. run_type='{run_type}', results type='{type(self._current_results_list)}'")

        except Exception as find_e:
             self.log.error(f"Error occurred while searching for selected item data: {find_e}", exc_info=True)
             detail_markdown.update(f"Error finding details for key: {escape(lookup_key)}")
             return

        # Format and update the detail markdown
        if selected_item_data:
            self.log.info(f"Formatting details for key '{lookup_key}'...")
            detail_md = ""
            try:
                # ... (Formatting logic remains the same) ...
                if run_type == "scenario" and isinstance(selected_item_data, dict):
                     detail_md = f"### Details for Role: {escape(str(lookup_key).title())}\n\n"
                     formatted_role_data = json.dumps(selected_item_data, indent=2)
                     detail_md += f"```json\n{escape(formatted_role_data)}\n```\n"
                elif isinstance(selected_item_data, dict):
                     item_id_key = "question_id" if run_type == "benchmark" else "scenario_id"
                     item_id_val = selected_item_data.get(item_id_key, lookup_key) # Use lookup_key as fallback
                     detail_md = f"### Details for ID: {escape(str(item_id_val))}\n\n"
                     for key, value in selected_item_data.items():
                         value_str = str(value)
                         key_title = escape(key.replace('_', ' ').title())
                         if key in ["planner_output", "executor_output", "judge_output", "question", "response", "scenario_text"]:
                             detail_md += f"**{key_title}:**\n\n{escape(value_str)}\n\n---\n"
                         elif isinstance(value, (list, dict)):
                              val_formatted = json.dumps(value, indent=2)
                              detail_md += f"**{key_title}:**\n```json\n{escape(val_formatted)}\n```\n"
                         else:
                              detail_md += f"**{key_title}:** {escape(value_str)}\n"
                else:
                     detail_md = f"Unexpected data format for details: {escape(str(type(selected_item_data)))}"

                detail_markdown.update(detail_md)
                content_scroll.scroll_home(animate=False) # Scroll parent container
                self.log.info(f"Detail markdown updated for key '{lookup_key}'.")

            except Exception as format_e:
                 self.log.error(f"Error formatting details markdown: {format_e}", exc_info=True)
                 detail_markdown.update(f"Error formatting details for key: {escape(lookup_key)}")
        else:
            self.log.info(f"No details found to display for key '{lookup_key}'.")
            detail_markdown.update(f"Details not found for key: {escape(lookup_key)}")