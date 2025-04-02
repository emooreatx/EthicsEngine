# EthicsEngine/dashboard/views/results_browser_view.py
import json
import os
import logging
from pathlib import Path
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, ListView, ListItem, Label, Markdown, DataTable
from textual.reactive import reactive
from textual.events import Mount
from textual.message import Message
from textual.markup import escape

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

# --- ResultsBrowserView Class ---
class ResultsBrowserView(Static):
    """View for browsing and displaying past result files using a table and detail view."""

    selected_file = reactive(None)
    # Store the full loaded data and just the results list separately
    _current_loaded_data = reactive(None, repaint=False)
    _current_results_list = reactive(None, repaint=False)

    log = logger

    def compose(self) -> ComposeResult:
        self.log.debug("Composing ResultsBrowserView")
        try:
            with Horizontal(): # Main container for list and content
                # File List Pane
                with Vertical(id="results-file-list-container", classes="browser-list-container"):
                    yield Label("Past Result Files (Newest First):", classes="title")
                    yield ListView(id="results-browser-list")
                # Content Display Pane
                with VerticalScroll(id="results-content-container", classes="browser-content-container"):
                    # Use markup=False initially for metadata to avoid parsing issues before formatting
                    yield Static("Select a file to view metadata.", id="results-browser-metadata", classes="metadata-display", markup=False)
                    yield Label("Results Summary:", classes="title", id="results-browser-table-title")
                    yield DataTable(id="results-browser-table", show_header=True, show_cursor=True, zebra_stripes=True)
                    yield Label("Details (Select Row Above):", classes="title", id="results-browser-detail-title")
                    # Use Markdown for flexible detail display
                    yield Markdown("", id="results-browser-detail-markdown")
        except Exception as e:
            self.log.exception(f"Error during ResultsBrowserView compose: {e}")
            yield Static(f"Error composing ResultsBrowserView: {escape(str(e))}")


    def on_mount(self) -> None:
        """Called when the view is mounted. Populates the file list."""
        self.log.debug("Mounting ResultsBrowserView")
        try:
            # Hide titles initially
            self.query_one("#results-browser-table-title").display = False
            self.query_one("#results-browser-detail-title").display = False
            self.query_one("#results-browser-detail-markdown").update("Select a file from the list.")
            # Load the list of result files
            self._populate_file_list()
        except Exception as e:
             self.log.error(f"Error during on_mount: {e}", exc_info=True)
             try:
                  # Attempt to display error in metadata area if mount fails
                  metadata_widget = self.query_one("#results-browser-metadata", Static)
                  metadata_widget.update(f"Error during view mount: {escape(str(e))}")
             except Exception as query_e:
                  self.log.error(f"Could not query metadata widget during on_mount error handling: {query_e}")


    def _scan_results_dir(self) -> list[str]:
        """Scans the RESULTS_DIR for .json files, returning sorted filenames."""
        self.log.debug(f"Scanning results directory: {RESULTS_DIR.absolute()}")
        if not RESULTS_DIR.exists() or not RESULTS_DIR.is_dir():
            self.log.warning(f"Results directory not found or not a directory: {RESULTS_DIR}")
            return []
        try:
            # Find all .json files and sort by modification time, newest first
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
                    # Use filename as the 'name' for easy retrieval on selection
                    list_view.append(ListItem(Label(escape(filename)), name=filename))
            # Select the first item if the list is not empty
            list_view.index = 0 if result_files else None
        except Exception as e:
             self.log.error(f"Failed to populate results file list: {e}", exc_info=True)
             try:
                  # Attempt to display error in the list view itself
                  list_view = self.query_one("#results-browser-list", ListView)
                  list_view.clear()
                  list_view.append(ListItem(Label(f"Error populating list: {escape(str(e))}")))
             except Exception as query_e:
                  self.log.error(f"Could not query list view during populate error handling: {query_e}")


    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle selection changes in the file list view."""
        self.log.debug(f"ListView selection event: {event.item}")
        if event.list_view.id == "results-browser-list" and event.item is not None:
             # Retrieve the filename stored in the item's 'name' attribute
             filename = getattr(event.item, 'name', None)
             if filename:
                  self.log.info(f"File selected via ListView: {filename}")
                  # Update the reactive variable, triggering watch_selected_file
                  self.selected_file = filename

    def _truncate(self, text, length=50):
        """Helper function to truncate long strings for table display."""
        text_str = str(text).replace('\n', ' ').replace('\r', '')
        if len(text_str) > length:
            return text_str[:length-1] + "\u2026" # Ellipsis
        return text_str

    # --- Updated Metadata Formatting Helper ---
    def _format_metadata(self, metadata: dict, filename: str) -> str:
        """Formats the metadata dictionary into a Markdown string."""
        # Use a plain string builder first, apply final escaping later if needed
        # Or rely on Markdown widget's parsing for simple cases.
        # Let's build a simple string first.
        metadata_str = f"File: {filename}\n\n---\n"
        for key, value in metadata.items():
             key_title = key.replace('_', ' ').title()
             val_str = "[Error formatting value]" # Default in case of error
             try:
                 if isinstance(value, list):
                     if key == 'llm_config' and value:
                         models = [cfg.get("model", "N/A") for cfg in value if isinstance(cfg, dict)]
                         val_str = ", ".join(models)
                     elif key == 'species_traits' and value:
                         val_str = ", ".join(map(str, value))
                     elif not value:
                          val_str = "[]"
                     else:
                         val_str = f"[{len(value)} items]"
                 elif isinstance(value, dict):
                     if key in ['agent_reasoning_config', 'evaluation_criteria'] and value:
                          items_str = ", ".join(f"{k}={v}" for k, v in value.items())
                          val_str = f"{{{items_str}}}"
                          val_str = self._truncate(val_str, 100)
                     elif not value:
                          val_str = "{}"
                     else:
                         keys_str = ", ".join(value.keys())
                         val_str = f"{{{len(value)} keys: {keys_str}}}"
                         val_str = self._truncate(val_str, 100)
                 else:
                     val_str = self._truncate(str(value), 100)

                 # Brackets are intentionally NOT escaped here as the target Static widget uses markup=False.
                 # If markup=True is used later, escaping might be needed for complex values,
                 # but simple '[]' or '{}' should render correctly.
                 # Also escape other potential markup characters if necessary, e.g., '*'
                 # val_str = str(val_str).replace("*", r"\*") # Uncomment if needed

             except Exception as fmt_e:
                 self.log.error(f"Error formatting metadata key '{key}': {fmt_e}")

             # --- MODIFIED: Skip empty top-level tags/criteria ---
             if key in ['tags', 'evaluation_criteria'] and not value:
                 self.log.debug(f"Skipping empty metadata key: {key}")
                 continue

             # Use bold for keys via Markdown syntax if passing to Markdown widget
             # If passing to Static(markup=True), use [b]key[/b]
             # Since we pass to Static(markup=False), bolding won't work here.
             # Keep it simple for Static(markup=False)
             metadata_str += f"{key_title}: {val_str}\n"

        return metadata_str # Return the potentially complex string

    def watch_selected_file(self, filename: str | None) -> None:
        """Loads file data, updates metadata, and populates the results table when selection changes."""
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
        metadata_display.update("") # Use update for Static
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

        # Handle Load Errors or Missing Structure
        if not isinstance(loaded_data, dict) or ("Error" in loaded_data or "_load_error" in loaded_data):
            error_msg = loaded_data.get("Error", "Could not load or parse file content") if isinstance(loaded_data, dict) else "Invalid file content"
            # Display error safely in the Static widget (markup=False)
            metadata_display.update(f"**Error Loading {filename}:**\n\n{error_msg}")
            if hasattr(self, 'app') and self.app: self.app.notify(f"Error loading {filename}", severity="error", title="Load Error")
            return
        elif "metadata" not in loaded_data or "results" not in loaded_data:
            self.log.warning(f"File {filename} missing 'metadata' or 'results' key. Displaying raw content.")
            metadata_display.update(f"**Warning:** File format may be outdated or incorrect (missing 'metadata' or 'results'). Displaying raw content.")
            try:
                 formatted_json = json.dumps(loaded_data, indent=2)
                 # Use Markdown widget for potentially large raw JSON
                 detail_markdown.update(f"```json\n{escape(formatted_json)}\n```")
                 detail_title.display = True
            except Exception as e:
                 detail_markdown.update(f"```\nError displaying raw content: {escape(str(e))}\n```")
            return

        # Process New Format (Metadata and Results)
        self.log.debug("Processing new file format (metadata and results)")
        metadata = loaded_data.get("metadata", {})
        results_data = loaded_data.get("results")
        self._current_results_list = results_data

        # 1. Update Metadata Display using helper
        # Pass the formatted string to the Static widget. Since markup=False, it's treated as plain text.
        formatted_metadata_str = self._format_metadata(metadata, filename)
        metadata_display.update(formatted_metadata_str)

        # 2. Populate Results Table based on run_type
        # (Table population logic remains the same as the previous version)
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

        # --- MODIFIED: Added "benchmark_set" and "benchmark_single" to handle list-based benchmark results ---
        if run_type in ["benchmark", "benchmark_set", "benchmark_single"] and isinstance(results_data, list):
            self.log.debug(f"Populating {run_type} results table") # Log the actual type
            results_table.add_columns("QID", "Question", "Expected", "Response", "Judgement")
            results_table.fixed_columns = 1
            for item in results_data:
                if isinstance(item, dict):
                     qid = item.get("question_id", "N/A")
                     output_data = item.get("output", {})
                     response = output_data.get("answer", "")
                     judgement = output_data.get("judgement", "")
                     add_row_safely(results_table, qid, self._truncate(item.get("question", "")), self._truncate(item.get("expected_answer", "")), self._truncate(response), self._truncate(judgement), key=str(qid))
                else: self.log.warning(f"Skipping non-dict item in benchmark results: {item}")

        # --- MODIFIED: Added "scenario_set" and "scenario_pipeline_single" to handle list-based results ---
        elif run_type in ["scenario_pipeline", "scenario_set", "scenario_pipeline_single"] and isinstance(results_data, list):
            self.log.debug(f"Populating {run_type} results table") # Log the actual type
            results_table.add_columns("ID", "Scenario Text", "Planner", "Executor", "Tags", "Eval Criteria") # Added Eval Criteria
            results_table.fixed_columns = 1
            for item in results_data:
                if isinstance(item, dict):
                     sid = item.get("scenario_id", "N/A")
                     tags_list = item.get("tags", [])
                     tags_str = ", ".join(map(str, tags_list)) if tags_list else ""
                     # Format eval criteria for table summary
                     eval_criteria = item.get("evaluation_criteria", {})
                     pos_count = len(eval_criteria.get("positive", []))
                     neg_count = len(eval_criteria.get("negative", []))
                     eval_str = f"P:{pos_count}, N:{neg_count}" if pos_count or neg_count else ""

                     add_row_safely(results_table,
                                    sid,
                                    self._truncate(item.get("scenario_text", "")),
                                    self._truncate(item.get("planner_output", "")),
                                    self._truncate(item.get("executor_output", "")),
                                    self._truncate(tags_str),
                                    eval_str, # Added eval criteria summary
                                    key=str(sid))
                else: self.log.warning(f"Skipping non-dict item in {run_type} results: {item}")

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


    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        """Update the detail markdown view when a cell/row is selected in the results table."""
        # (This logic remains the same as the previous version - it correctly finds
        # the data and formats it for the Markdown widget, which handles complex structures)
        self.log.debug(f"Cell selected: cell_key='{event.cell_key}', value='{event.value}', table_id='{event.control.id}'")

        if not event.cell_key or event.cell_key.row_key is None:
             self.log.warning("Cell selection event missing row key object.")
             return

        row_key_obj = event.cell_key.row_key
        try:
             lookup_key = str(row_key_obj.value)
             self.log.debug(f"Extracted lookup_key: '{lookup_key}' from RowKey object")
        except AttributeError:
             self.log.error(f"Could not get '.value' from RowKey object: {row_key_obj}. Cannot lookup details.")
             return

        try:
            detail_markdown = self.query_one("#results-browser-detail-markdown", Markdown)
            content_scroll = self.query_one("#results-content-container", VerticalScroll)
        except Exception as e:
            self.log.error(f"Cannot find detail markdown/scroll widget in cell selection handler: {e}", exc_info=True)
            return

        if self._current_results_list is None:
            self.log.warning("Current results list is None, cannot load details.")
            detail_markdown.update("Could not load details for selected row (results data not available).")
            return

        selected_item_data = None
        run_type = None
        if isinstance(self._current_loaded_data, dict) and "metadata" in self._current_loaded_data:
            run_type = self._current_loaded_data.get("metadata", {}).get("run_type")
            self.log.debug(f"Determined run_type for detail view: '{run_type}'")
        else:
             self.log.warning("Could not determine run_type from loaded data for detail view.")
             detail_markdown.update("Error: Could not determine result type.")
             return

        try:
            # --- MODIFIED: Added single run types to the list for list-based lookup ---
            if run_type in ["benchmark", "benchmark_set", "benchmark_single", "scenario_pipeline", "scenario_set", "scenario_pipeline_single"] and isinstance(self._current_results_list, list):
                # Determine the correct key based on whether it's a benchmark or scenario type
                key_to_match = "question_id" if run_type in ["benchmark", "benchmark_set", "benchmark_single"] else "scenario_id"
                self.log.debug(f"Searching for item with {key_to_match} == '{lookup_key}' in list of {len(self._current_results_list)} items")
                found = False
                for item in self._current_results_list:
                     if isinstance(item, dict):
                          item_key_val = item.get(key_to_match)
                          # Ensure comparison is robust (e.g., handle potential type differences if key isn't always string)
                          if str(item_key_val) == str(lookup_key):
                              selected_item_data = item
                              self.log.info(f"Found matching item data for key '{lookup_key}'")
                              found = True
                              break
                if not found: self.log.warning(f"Item with {key_to_match} == '{lookup_key}' not found in list.")
            # --- MODIFIED: Removed the 'else' block that logged a warning for valid run_types like 'scenario' ---
            # else:
            #      self.log.warning(f"Cannot determine how to find selected item details. run_type='{run_type}', results type='{type(self._current_results_list)}'")

        except Exception as find_e:
             self.log.error(f"Error occurred while searching for selected item data: {find_e}", exc_info=True)
             detail_markdown.update(f"Error finding details for key: {escape(lookup_key)}")
             return

        if selected_item_data and isinstance(selected_item_data, dict):
            self.log.info(f"Formatting details for key '{lookup_key}'...")
            detail_md = ""
            try:
                # --- MODIFIED: Determine item_id_key based on run_type including scenario_set ---
                item_id_key = "question_id" if run_type == "benchmark" else "scenario_id"
                item_id_val = selected_item_data.get(item_id_key, lookup_key)
                detail_md = f"### Details for ID: {escape(str(item_id_val))}\n\n---\n"

                for key, value in selected_item_data.items():
                    value_str = str(value) # Default string representation
                    key_title = escape(key.replace('_', ' ').title())

                    # --- MODIFIED: Handle formatting based on run_type and key ---
                    if key == "output" and run_type == "benchmark" and isinstance(value, dict):
                         detail_md += f"**{key_title}:**\n"
                         detail_md += f"  - **Answer:** {escape(value.get('answer', 'N/A'))}\n"
                         detail_md += f"  - **Judgement:** {escape(value.get('judgement', 'N/A'))}\n"
                    # --- MODIFIED: Include scenario_set for decision_tree formatting ---
                    elif key == "decision_tree" and run_type in ["scenario_pipeline", "scenario_set"] and isinstance(value, dict):
                         # Format large dicts like decision_tree as JSON block
                         detail_md += f"**{key_title}:**\n```json\n{escape(json.dumps(value, indent=2))}\n```\n"
                    # --- MODIFIED: Include scenario_set for evaluation_criteria formatting ---
                    elif key == "evaluation_criteria" and run_type in ["scenario_pipeline", "scenario_set"] and isinstance(value, dict):
                         detail_md += f"**{key_title}:**\n"
                         pos = value.get("positive", [])
                         neg = value.get("negative", [])
                         detail_md += f"  - Positive: {escape(', '.join(map(str, pos)))}\n"
                         detail_md += f"  - Negative: {escape(', '.join(map(str, neg)))}\n"
                    elif key == "tags" and isinstance(value, list):
                         detail_md += f"**{key_title}:** {escape(', '.join(map(str, value)))}\n"
                    elif isinstance(value, (list, dict)):
                         val_formatted = json.dumps(value, indent=2)
                         detail_md += f"**{key_title}:**\n```json\n{escape(val_formatted)}\n```\n"
                    else:
                         detail_md += f"**{key_title}:** {escape(value_str)}\n"
                    detail_md += "\n" # Add spacing

                detail_markdown.update(detail_md)
                content_scroll.scroll_home(animate=False)
                self.log.info(f"Detail markdown updated for key '{lookup_key}'.")

            except Exception as format_e:
                 self.log.error(f"Error formatting details markdown: {format_e}", exc_info=True)
                 detail_markdown.update(f"Error formatting details for key: {escape(lookup_key)}")
        else:
            self.log.info(f"No details found or data is not a dict for key '{lookup_key}'.")
            detail_markdown.update(f"Details not found or invalid format for key: {escape(lookup_key)}")
