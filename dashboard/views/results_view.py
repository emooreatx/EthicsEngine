# EthicsEngine/dashboard/views/results_view.py
import json
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static, DataTable, Markdown
from textual.reactive import reactive
from textual.events import Mount
from textual.message import Message # Keep if custom messages are needed later

class ResultsView(Static):
    """View displaying run results in a DataTable + Detail Markdown."""

    # Make sure reactive variables are used correctly if data is passed/updated
    full_results_data = reactive(None)
    selected_row_data = reactive(None)

    def __init__(self, results_data=None, **kwargs):
        super().__init__(**kwargs)
        # Initialize reactive variable directly
        self.full_results_data = results_data

    def compose(self) -> ComposeResult:
        with Vertical(id="results-display-area"):
             yield DataTable(id="results-table", show_header=True, show_cursor=True, zebra_stripes=True)
             yield Static("--- Details (Select Row Above) ---", classes="title", id="results-detail-title")
             with VerticalScroll(id="results-detail-scroll"):
                  yield Markdown(id="results-detail-markdown") # Initialize Markdown

    def on_mount(self) -> None:
        """Called when the widget is mounted."""
        self._render_table()
        # Safely query and update Markdown
        try:
            self.query_one("#results-detail-markdown", Markdown).update("Select a row to see details.")
            self.query_one("#results-detail-title").display = False
        except Exception as e:
            self.app.log.error(f"Error initializing ResultsView details: {e}")


    def _render_table(self) -> None:
        """Renders the DataTable based on the full_results_data."""
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.fixed_columns = 1 # Keep fixed columns setting

        if not self.full_results_data or not isinstance(self.full_results_data, dict) or not self.full_results_data.get("data"):
            table.add_column("Status")
            table.add_row("No results to display.")
            try:
                self.query_one("#results-detail-title").display = False
            except Exception: pass # Ignore if not found during initial render error
            return

        result_type = self.full_results_data.get("type")
        data = self.full_results_data.get("data", [])

        # Helper to truncate long text for table cells
        def truncate(text, length=70):
            text_str = str(text).replace('\n', ' ').replace('\r', '')
            return text_str if len(text_str) <= length else text_str[:length] + "…"

        try:
            if result_type == "scenario":
                table.add_columns("Scenario ID", "Scenario Text", "Planner Output", "Executor Output", "Judge Output")
                for result in data:
                    row_key = str(result.get("scenario_id", "")) if result.get("scenario_id") else None
                    table.add_row(
                        result.get("scenario_id", "N/A"),
                        truncate(result.get("scenario_text", "")),
                        truncate(result.get("planner_output", "")),
                        truncate(result.get("executor_output", "")),
                        truncate(result.get("judge_output", "")),
                        key=row_key
                    )
            elif result_type == "benchmark":
                table.add_columns("QID", "Question", "Expected", "Response", "Evaluation")
                for result in data:
                    row_key = str(result.get("question_id", "")) if result.get("question_id") else None
                    table.add_row(
                        result.get("question_id", "N/A"),
                        truncate(result.get("question", "")),
                        truncate(result.get("expected_answer", "")),
                        truncate(result.get("response", "")),
                        truncate(result.get("evaluation", "")),
                        key=row_key
                    )
            else:
                table.add_column("Info")
                table.add_row(f"Unknown results format ('{result_type}').")
                return # Don't show detail title if format is unknown

            # Show detail title only if data was successfully processed
            self.query_one("#results-detail-title").display = True

        except Exception as e:
            # Log error and display error in table
            self.app.log.error(f"Failed to display results table: {e}")
            table.clear(columns=True)
            table.add_column("Error")
            table.add_row(f"Failed to display table: {e}")
            try:
                self.query_one("#results-detail-title").display = False
            except Exception: pass # Ignore if not found


    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        """Handle cell selection to update the detail view."""
        if not event.cell_key or event.cell_key.row_key is None:
            self.selected_row_data = None # Clear selection
            return

        row_key = event.cell_key.row_key
        data = self.full_results_data.get("data", [])
        result_type = self.full_results_data.get("type")
        found_data = None

        # Find the full data for the selected row
        for item in data:
            item_id_str = None
            if result_type == "scenario":
                item_id_str = str(item.get("scenario_id"))
            elif result_type == "benchmark":
                item_id_str = str(item.get("question_id"))

            if item_id_str == row_key:
                found_data = item
                break

        self.selected_row_data = found_data

    # Watcher for the selected row data
    def watch_selected_row_data(self, row_data: dict | None) -> None:
        """Update the Markdown view when selected_row_data changes."""
        try:
            markdown_widget = self.query_one("#results-detail-markdown", Markdown)
            title_widget = self.query_one("#results-detail-title")
            scroll_widget = self.query_one("#results-detail-scroll", VerticalScroll)
        except Exception as e:
            self.app.log.error(f"Error finding detail widgets in watch_selected_row_data: {e}")
            return # Cannot proceed if widgets aren't found

        if row_data is None:
            markdown_widget.update("Select a row in the table above to see full details.")
            title_widget.display = False
            return

        # Format the selected row data into Markdown
        row_id = row_data.get('scenario_id') or row_data.get('question_id') or "N/A"
        details = f"### Details for Row: {row_id}\n\n"
        for key, value in row_data.items():
             value_str = str(value)
             # Use code block for multi-line or long values
             display_value = f"\n```\n{value_str}\n```\n" if len(value_str) > 60 or '\n' in value_str else f" {value_str}\n"
             details += f"**{key.replace('_', ' ').title()}:**{display_value}\n" # Format key nicely

        markdown_widget.update(details)
        title_widget.display = True

        # Scroll detail view to top
        try:
            scroll_widget.scroll_home(animate=False)
        except Exception as e:
            self.app.log.warning(f"Could not scroll detail view: {e}")

