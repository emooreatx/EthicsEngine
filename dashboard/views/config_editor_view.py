# dashboard/views/config_editor_view.py
"""
Provides a Textual view for editing the application's configuration settings
stored in config/settings.json.
"""
import json
import os
import logging
# --- Textual Imports ---
from textual.app import ComposeResult
from textual.containers import VerticalScroll, Container, Horizontal
from textual.widgets import (
    Static, Label, Input, Button, Select, TextArea, Switch, LoadingIndicator
)
from textual.message import Message # For emitting messages
from textual.reactive import reactive # For reactive attributes

# --- Constants and Logger ---
# Define paths relative to the project root
SETTINGS_FILE_PATH = "config/settings.json"
LOG_FILE_PATH = "app.log"
# Use the application's configured logger if available
try:
    from config.config import logger
except ImportError:
    logger = logging.getLogger("ConfigEditorView_Fallback")

# --- View Class ---
class ConfigEditorView(Static):
    """
    A Textual view widget for displaying and editing application settings.

    Allows users to modify LLM configurations, concurrency limits, log levels,
    agent timeouts, and reasoning specifications via UI elements. Includes
    buttons to save, reload settings, and clear the log file.
    """

    # --- Custom Messages ---
    class SettingsSaved(Message):
        """Message posted when settings are successfully saved."""
        pass

    # --- Reactive Attributes (Not currently used for UI binding, but could be) ---
    # These could potentially hold the state if not directly bound to widgets.
    # llm_config_text = reactive("", layout=True)
    # concurrency = reactive(10, layout=True)
    # log_level = reactive("INFO", layout=True)
    # agent_timeout = reactive(300, layout=True)
    # reasoning_specs_text = reactive("", layout=True)
    # status_message = reactive("", layout=True) # Status is now a Static widget

    def compose(self) -> ComposeResult:
        """Compose the UI elements for the configuration editor view."""
        yield Label("Configuration Editor", classes="view-title")
        # Use VerticalScroll to allow content to exceed screen height
        with VerticalScroll(id="config-editor-scroll"):
            # --- LLM Configuration ---
            yield Label("LLM Configuration (JSON List):", classes="config-label")
            # TextArea for editing the JSON list of LLM configurations
            yield TextArea(
                id="llm-config-input",
                language="json", # Enable JSON syntax highlighting
                show_line_numbers=True,
                soft_wrap=True,
            )

            # --- Concurrency Limit ---
            yield Label("Concurrency Limit:", classes="config-label")
            yield Input(
                id="concurrency-input", type="integer", placeholder="e.g., 10"
            )

            # --- Log Level ---
            yield Label("Log Level:", classes="config-label")
            yield Select(
                [ # Options for the log level dropdown
                    ("DEBUG", "DEBUG"),
                    ("INFO", "INFO"),
                    ("WARNING", "WARNING"),
                    ("ERROR", "ERROR"),
                    ("CRITICAL", "CRITICAL"),
                ],
                id="log-level-select",
                value="INFO", # Default selection
                allow_blank=False, # Prevent selecting a blank option
            )

            # --- Agent Timeout ---
            yield Label("Agent Timeout (seconds):", classes="config-label")
            yield Input(
                id="agent-timeout-input", type="number", placeholder="e.g., 300" # Use 'number' for numeric input
            )

            # --- Reasoning Specifications ---
            yield Label("Reasoning Specifications (JSON Object):", classes="config-label")
            # TextArea for editing the JSON object defining reasoning levels
            yield TextArea(
                id="reasoning-specs-input",
                language="json",
                show_line_numbers=True,
                soft_wrap=True,
            )

            # --- Status Message ---
            # Static widget to display feedback (e.g., "Settings saved", "Error")
            yield Static(id="status-message", classes="status-message")

            # --- Action Buttons ---
            with Horizontal(classes="button-container"):
                yield Button("Save Settings", id="save-settings-button", variant="primary")
                yield Button("Reload Settings", id="reload-settings-button")
                yield Button("Clear Log File", id="clear-log-button", variant="error")

    def on_mount(self) -> None:
        """Load initial settings into the UI when the view is mounted."""
        self.load_settings_to_ui()

    def load_settings_to_ui(self) -> None:
        """Loads settings from the settings.json file and populates the UI widgets."""
        status_widget = self.query_one("#status-message", Static)
        status_widget.update("Loading settings...")
        try:
            # Load settings from the JSON file
            with open(SETTINGS_FILE_PATH, "r", encoding="utf-8") as f: # Specify encoding
                settings_data = json.load(f)

            # --- Populate UI Elements ---
            # LLM Config: Load list and format as JSON string for TextArea
            llm_list = settings_data.get("llm_config_list", [])
            llm_text_area = self.query_one("#llm-config-input", TextArea)
            # Use load_text for efficient TextArea update
            llm_text_area.load_text(json.dumps(llm_list, indent=2))

            # Concurrency: Set Input value
            concurrency_val = settings_data.get("concurrency", 10)
            self.query_one("#concurrency-input", Input).value = str(concurrency_val)

            # Log Level: Set Select value (ensure uppercase)
            log_level_val = settings_data.get("log_level", "INFO").upper()
            self.query_one("#log-level-select", Select).value = log_level_val

            # Agent Timeout: Set Input value
            timeout_val = settings_data.get("agent_timeout", 300)
            self.query_one("#agent-timeout-input", Input).value = str(timeout_val)

            # Reasoning Specs: Load object and format as JSON string for TextArea
            reasoning_specs = settings_data.get("reasoning_specs", {})
            reasoning_text_area = self.query_one("#reasoning-specs-input", TextArea)
            reasoning_text_area.load_text(json.dumps(reasoning_specs, indent=2))

            status_widget.update("Settings loaded.")
            logger.info("Configuration loaded into editor UI.")

        except FileNotFoundError:
            # Handle case where settings file doesn't exist
            status_widget.update(f"[bold red]Error: {SETTINGS_FILE_PATH} not found.[/]")
            logger.error(f"Settings file not found at {SETTINGS_FILE_PATH}")
            # Populate UI with default values as placeholders
            self.query_one("#llm-config-input", TextArea).load_text(json.dumps([], indent=2))
            self.query_one("#concurrency-input", Input).value = "10"
            self.query_one("#log-level-select", Select).value = "INFO"
            self.query_one("#agent-timeout-input", Input).value = "300"
            self.query_one("#reasoning-specs-input", TextArea).load_text(json.dumps({}, indent=2))

        except json.JSONDecodeError:
            # Handle invalid JSON in the settings file
            status_widget.update(f"[bold red]Error: Invalid JSON in {SETTINGS_FILE_PATH}.[/]")
            logger.error(f"Invalid JSON in settings file {SETTINGS_FILE_PATH}", exc_info=True)
        except Exception as e:
            # Handle other unexpected errors during loading
            status_widget.update(f"[bold red]Error loading settings: {e}[/]")
            logger.error(f"Unexpected error loading settings: {e}", exc_info=True)


    def save_settings_from_ui(self) -> None:
        """Reads values from UI widgets, validates them, and saves to settings.json."""
        status_widget = self.query_one("#status-message", Static)
        status_widget.update("Saving settings...")
        try:
            # --- Read and Validate LLM Config ---
            llm_text = self.query_one("#llm-config-input", TextArea).text
            try:
                llm_config_list = json.loads(llm_text)
                if not isinstance(llm_config_list, list):
                    raise ValueError("LLM Configuration must be a JSON list.")
                # TODO: Add more detailed validation of list items if needed
            except json.JSONDecodeError:
                status_widget.update("[bold red]Error: Invalid JSON in LLM Configuration.[/]")
                logger.error("Invalid JSON provided for LLM config.")
                return
            except ValueError as e:
                 status_widget.update(f"[bold red]Error: {e}[/]")
                 logger.error(f"Validation error for LLM config: {e}")
                 return

            # --- Read and Validate Concurrency ---
            concurrency_str = self.query_one("#concurrency-input", Input).value
            try:
                concurrency_val = int(concurrency_str)
                if concurrency_val <= 0:
                    raise ValueError("Concurrency must be a positive integer.")
            except ValueError:
                status_widget.update("[bold red]Error: Concurrency must be a positive integer.[/]")
                logger.error(f"Invalid concurrency value: {concurrency_str}")
                return

            # --- Read Log Level ---
            log_level_val = self.query_one("#log-level-select", Select).value
            # Basic check, though Select should prevent invalid values if allow_blank=False
            if log_level_val not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
                 status_widget.update("[bold red]Error: Invalid Log Level selected.[/]")
                 logger.error(f"Invalid log level selected: {log_level_val}")
                 return

            # --- Read and Validate Agent Timeout ---
            timeout_str = self.query_one("#agent-timeout-input", Input).value
            try:
                timeout_val = float(timeout_str) # Allow float for timeout
                if timeout_val <= 0:
                    raise ValueError("Agent Timeout must be a positive number.")
            except ValueError:
                status_widget.update("[bold red]Error: Agent Timeout must be a positive number.[/]")
                logger.error(f"Invalid agent timeout value: {timeout_str}")
                return

            # --- Read and Validate Reasoning Specs ---
            reasoning_text = self.query_one("#reasoning-specs-input", TextArea).text
            try:
                reasoning_specs = json.loads(reasoning_text)
                if not isinstance(reasoning_specs, dict):
                    raise ValueError("Reasoning Specifications must be a JSON object.")
                # TODO: Add more detailed validation (e.g., check for low/medium/high keys)
            except json.JSONDecodeError:
                status_widget.update("[bold red]Error: Invalid JSON in Reasoning Specifications.[/]")
                logger.error("Invalid JSON provided for reasoning specs.")
                return
            except ValueError as e:
                 status_widget.update(f"[bold red]Error: {e}[/]")
                 logger.error(f"Validation error for reasoning specs: {e}")
                 return

            # --- Assemble and Save Settings ---
            new_settings = {
                "llm_config_list": llm_config_list,
                "concurrency": concurrency_val,
                "log_level": log_level_val,
                "agent_timeout": timeout_val,
                "reasoning_specs": reasoning_specs,
            }

            # Write the validated settings back to the file
            with open(SETTINGS_FILE_PATH, "w", encoding="utf-8") as f: # Specify encoding
                json.dump(new_settings, f, indent=2)

            status_widget.update("[bold green]Settings saved successfully![/]")
            logger.info(f"Configuration saved to {SETTINGS_FILE_PATH}")
            # Post a message to notify the parent app that settings changed
            self.post_message(self.SettingsSaved())

        except Exception as e:
            # Catch any other unexpected errors during saving
            status_widget.update(f"[bold red]Error saving settings: {e}[/]")
            logger.error(f"Unexpected error saving settings: {e}", exc_info=True)

    def clear_log_file(self) -> None:
        """Clears the content of the application log file."""
        status_widget = self.query_one("#status-message", Static)
        status_widget.update("Clearing log file...")
        try:
            # Open the log file in write mode and truncate it
            with open(LOG_FILE_PATH, "w") as f:
                f.truncate(0)
            status_widget.update("[bold green]Log file cleared successfully![/]")
            logger.info(f"Log file cleared: {LOG_FILE_PATH}")
            # Optionally, notify the LogView to refresh if it's active
            # try:
            #     log_view = self.app.query_one("LogView")
            #     log_view.refresh_log_content() # Assuming such a method exists
            # except Exception: pass
        except FileNotFoundError:
             # Handle case where log file doesn't exist
             status_widget.update(f"[bold orange]Log file not found at {LOG_FILE_PATH}. Nothing to clear.[/]")
             logger.warning(f"Attempted to clear log file, but it was not found: {LOG_FILE_PATH}")
        except Exception as e:
            # Handle other errors during file clearing
            status_widget.update(f"[bold red]Error clearing log file: {e}[/]")
            logger.error(f"Error clearing log file {LOG_FILE_PATH}: {e}", exc_info=True)


    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events for Save, Reload, and Clear Log."""
        if event.button.id == "save-settings-button":
            self.save_settings_from_ui()
        elif event.button.id == "reload-settings-button":
            self.load_settings_to_ui()
        elif event.button.id == "clear-log-button":
            self.clear_log_file()
