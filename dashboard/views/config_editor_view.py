import json
import os
import logging
from textual.app import ComposeResult
from textual.containers import VerticalScroll, Container, Horizontal
from textual.widgets import (
    Static,
    Label,
    Input,
    Button,
    Select,
    TextArea,
    Switch,
    LoadingIndicator,
)
from textual.message import Message
from textual.reactive import reactive

# Assuming settings are loaded similarly or passed down
# For now, define the path directly
SETTINGS_FILE_PATH = "config/settings.json"
LOG_FILE_PATH = "app.log"
logger = logging.getLogger("EthicsEngine_Dashboard")

class ConfigEditorView(Static):
    """A view to edit application configuration settings."""

    # Message to notify parent when settings are saved
    class SettingsSaved(Message):
        pass

    # Reactive variables to hold current settings (will be loaded)
    llm_config_text = reactive("", layout=True)
    concurrency = reactive(10, layout=True)
    log_level = reactive("INFO", layout=True)
    agent_timeout = reactive(300, layout=True)
    reasoning_specs_text = reactive("", layout=True)
    status_message = reactive("", layout=True)

    def compose(self) -> ComposeResult:
        """Create child widgets for the configuration editor."""
        yield Label("Configuration Editor", classes="view-title")
        with VerticalScroll(id="config-editor-scroll"):
            yield Label("LLM Configuration (JSON):", classes="config-label")
            yield TextArea(
                id="llm-config-input",
                language="json",
                show_line_numbers=True,
                soft_wrap=True,
            )

            yield Label("Concurrency Limit:", classes="config-label")
            yield Input(
                id="concurrency-input", type="integer", placeholder="e.g., 10"
            )

            yield Label("Log Level:", classes="config-label")
            yield Select(
                [
                    ("DEBUG", "DEBUG"),
                    ("INFO", "INFO"),
                    ("WARNING", "WARNING"),
                    ("ERROR", "ERROR"),
                    ("CRITICAL", "CRITICAL"),
                ],
                id="log-level-select",
                value="INFO", # Default
                allow_blank=False,
            )

            yield Label("Agent Timeout (seconds):", classes="config-label")
            yield Input(
                id="agent-timeout-input", type="number", placeholder="e.g., 300"
            )

            yield Label("Reasoning Specifications (JSON):", classes="config-label")
            yield TextArea(
                id="reasoning-specs-input",
                language="json",
                show_line_numbers=True,
                soft_wrap=True,
            )

            yield Static(id="status-message", classes="status-message") # For feedback

            with Horizontal(classes="button-container"):
                yield Button("Save Settings", id="save-settings-button", variant="primary")
                yield Button("Reload Settings", id="reload-settings-button")
                yield Button("Clear Log File", id="clear-log-button", variant="error")

    def on_mount(self) -> None:
        """Load initial settings when the view is mounted."""
        self.load_settings_to_ui()

    def load_settings_to_ui(self) -> None:
        """Load settings from the JSON file and update UI elements."""
        self.query_one("#status-message", Static).update("Loading settings...")
        try:
            with open(SETTINGS_FILE_PATH, "r") as f:
                settings_data = json.load(f)

            # Update reactive vars and UI elements
            llm_list = settings_data.get("llm_config_list", [])
            # Convert list back to displayable JSON string and use load_text
            llm_text_area = self.query_one("#llm-config-input", TextArea)
            llm_text_area.load_text(json.dumps(llm_list, indent=2))

            concurrency_val = settings_data.get("concurrency", 10)
            self.query_one("#concurrency-input", Input).value = str(concurrency_val)

            log_level_val = settings_data.get("log_level", "INFO").upper()
            self.query_one("#log-level-select", Select).value = log_level_val

            timeout_val = settings_data.get("agent_timeout", 300)
            self.query_one("#agent-timeout-input", Input).value = str(timeout_val)

            reasoning_specs = settings_data.get("reasoning_specs", {})
            # Use load_text for reasoning specs as well
            reasoning_text_area = self.query_one("#reasoning-specs-input", TextArea)
            reasoning_text_area.load_text(json.dumps(reasoning_specs, indent=2))

            self.query_one("#status-message", Static).update("Settings loaded.")
            logger.info("Configuration loaded into editor UI.")

        except FileNotFoundError:
            self.query_one("#status-message", Static).update(f"[bold red]Error: {SETTINGS_FILE_PATH} not found.[/]")
            logger.error(f"Settings file not found at {SETTINGS_FILE_PATH}")
            # Populate with defaults maybe? For now, show error.
            self.query_one("#llm-config-input", TextArea).load_text(json.dumps([], indent=2))
            self.query_one("#concurrency-input", Input).value = "10"
            self.query_one("#log-level-select", Select).value = "INFO"
            self.query_one("#agent-timeout-input", Input).value = "300"
            self.query_one("#reasoning-specs-input", TextArea).load_text(json.dumps({}, indent=2))

        except json.JSONDecodeError:
            self.query_one("#status-message", Static).update(f"[bold red]Error: Invalid JSON in {SETTINGS_FILE_PATH}.[/]")
            logger.error(f"Invalid JSON in settings file {SETTINGS_FILE_PATH}", exc_info=True)
        except Exception as e:
            self.query_one("#status-message", Static).update(f"[bold red]Error loading settings: {e}[/]")
            logger.error(f"Unexpected error loading settings: {e}", exc_info=True)


    def save_settings_from_ui(self) -> None:
        """Save the current UI settings back to the JSON file."""
        self.query_one("#status-message", Static).update("Saving settings...")
        try:
            # --- LLM Config ---
            llm_text = self.query_one("#llm-config-input", TextArea).text
            try:
                llm_config_list = json.loads(llm_text)
                if not isinstance(llm_config_list, list):
                    raise ValueError("LLM Configuration must be a JSON list.")
            except json.JSONDecodeError:
                self.query_one("#status-message", Static).update("[bold red]Error: Invalid JSON in LLM Configuration.[/]")
                logger.error("Invalid JSON provided for LLM config.")
                return
            except ValueError as e:
                 self.query_one("#status-message", Static).update(f"[bold red]Error: {e}[/]")
                 logger.error(f"Validation error for LLM config: {e}")
                 return

            # --- Concurrency ---
            concurrency_str = self.query_one("#concurrency-input", Input).value
            try:
                concurrency_val = int(concurrency_str)
                if concurrency_val <= 0:
                    raise ValueError("Concurrency must be a positive integer.")
            except ValueError:
                self.query_one("#status-message", Static).update("[bold red]Error: Concurrency must be a positive integer.[/]")
                logger.error(f"Invalid concurrency value: {concurrency_str}")
                return

            # --- Log Level ---
            log_level_val = self.query_one("#log-level-select", Select).value
            if log_level_val not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
                 self.query_one("#status-message", Static).update("[bold red]Error: Invalid Log Level selected.[/]")
                 logger.error(f"Invalid log level selected: {log_level_val}")
                 return # Should not happen with Select, but good practice

            # --- Agent Timeout ---
            timeout_str = self.query_one("#agent-timeout-input", Input).value
            try:
                timeout_val = float(timeout_str) # Allow float for timeout
                if timeout_val <= 0:
                    raise ValueError("Agent Timeout must be a positive number.")
            except ValueError:
                self.query_one("#status-message", Static).update("[bold red]Error: Agent Timeout must be a positive number.[/]")
                logger.error(f"Invalid agent timeout value: {timeout_str}")
                return

            # --- Reasoning Specs ---
            reasoning_text = self.query_one("#reasoning-specs-input", TextArea).text
            try:
                reasoning_specs = json.loads(reasoning_text)
                if not isinstance(reasoning_specs, dict):
                    raise ValueError("Reasoning Specifications must be a JSON object.")
                # Add more validation if needed (e.g., check for low/medium/high keys)
            except json.JSONDecodeError:
                self.query_one("#status-message", Static).update("[bold red]Error: Invalid JSON in Reasoning Specifications.[/]")
                logger.error("Invalid JSON provided for reasoning specs.")
                return
            except ValueError as e:
                 self.query_one("#status-message", Static).update(f"[bold red]Error: {e}[/]")
                 logger.error(f"Validation error for reasoning specs: {e}")
                 return

            # --- Assemble and Save ---
            new_settings = {
                "llm_config_list": llm_config_list,
                "concurrency": concurrency_val,
                "log_level": log_level_val,
                "agent_timeout": timeout_val,
                "reasoning_specs": reasoning_specs,
            }

            with open(SETTINGS_FILE_PATH, "w") as f:
                json.dump(new_settings, f, indent=2)

            self.query_one("#status-message", Static).update("[bold green]Settings saved successfully![/]")
            logger.info(f"Configuration saved to {SETTINGS_FILE_PATH}")
            self.post_message(self.SettingsSaved()) # Notify parent

        except Exception as e:
            self.query_one("#status-message", Static).update(f"[bold red]Error saving settings: {e}[/]")
            logger.error(f"Unexpected error saving settings: {e}", exc_info=True)

    def clear_log_file(self) -> None:
        """Clears the content of the log file."""
        self.query_one("#status-message", Static).update("Clearing log file...")
        try:
            with open(LOG_FILE_PATH, "w") as f:
                f.truncate(0) # Clear the file
            self.query_one("#status-message", Static).update("[bold green]Log file cleared successfully![/]")
            logger.info(f"Log file cleared: {LOG_FILE_PATH}")
            # Optionally, notify the LogView to refresh if it's separate
            # self.app.query_one(LogView).refresh_log_content()
        except FileNotFoundError:
             self.query_one("#status-message", Static).update(f"[bold orange]Log file not found at {LOG_FILE_PATH}. Nothing to clear.[/]")
             logger.warning(f"Attempted to clear log file, but it was not found: {LOG_FILE_PATH}")
        except Exception as e:
            self.query_one("#status-message", Static).update(f"[bold red]Error clearing log file: {e}[/]")
            logger.error(f"Error clearing log file {LOG_FILE_PATH}: {e}", exc_info=True)


    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "save-settings-button":
            self.save_settings_from_ui()
        elif event.button.id == "reload-settings-button":
            self.load_settings_to_ui()
        elif event.button.id == "clear-log-button":
            self.clear_log_file()

