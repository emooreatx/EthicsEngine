# dashboard/dashboard_modals.py
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll, Horizontal, Vertical # Added Vertical
from textual.widgets import (
    Label,
    Button,
    Static,
    Input,
    TextArea,
)
from textual.screen import Screen, ModalScreen
from textual.validation import Validator, ValidationResult

# --- Validator ---
class NonEmpty(Validator):
    """Simple validator to ensure input is not empty."""
    def validate(self, value: str) -> ValidationResult:
        if not value.strip(): # Use strip() to check for whitespace-only input
            return self.failure("Value cannot be empty.")
        return self.success()

# --- Modal Screen Classes ---
class CreateItemScreen(ModalScreen[tuple | None]):
    """Screen to create a new data item (key and value)."""

    def __init__(self, data_type: str):
        super().__init__()
        self.data_type = data_type

    def compose(self) -> ComposeResult:
        with Vertical(): # Wrap content in a container for styling
            yield Label(f"Create New {self.data_type[:-1]}") # e.g., "Create New Scenario"
            yield Label("Key:")
            yield Input(placeholder="Enter unique key/name", id="create-key-input", validators=[NonEmpty()])
            yield Label("Value:")
            yield TextArea(language="text", id="create-value-input", theme="vscode_dark") # Use a default theme
            with Horizontal():
                yield Button("Save", id="create-save-btn", variant="success")
                yield Button("Cancel", id="create-cancel-btn", variant="default")

    def on_mount(self) -> None:
        # Focus the first input field
        self.query_one(Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create-save-btn":
            key_input = self.query_one("#create-key-input", Input)
            value_input = self.query_one("#create-value-input", TextArea)
            # Validate the key input
            validation_result = key_input.validate(key_input.value)
            if not validation_result.is_valid:
                 # Display validation failures
                 self.app.notify(
                      "\n".join(validation_result.failure_descriptions),
                      severity="error",
                      title="Validation Error"
                 )
                 return
            # Return tuple (key, value)
            self.dismiss((key_input.value.strip(), value_input.text)) # Strip key whitespace
        elif event.button.id == "create-cancel-btn":
            self.dismiss(None) # Return None if cancelled


class EditItemScreen(ModalScreen[str | None]):
    """Screen to edit an existing data item's value."""

    def __init__(self, data_type: str, item_key: str, initial_value: str):
        super().__init__()
        self.data_type = data_type
        self.item_key = item_key
        self.initial_value = initial_value

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(f"Edit {self.data_type[:-1]}: {self.item_key}")
            yield Label("Value:")
            yield TextArea(self.initial_value, language="text", id="edit-value-input", theme="vscode_dark")
            with Horizontal():
                yield Button("Save", id="edit-save-btn", variant="success")
                yield Button("Cancel", id="edit-cancel-btn", variant="default")

    def on_mount(self) -> None:
        # Focus the text area when the screen opens
        self.query_one(TextArea).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "edit-save-btn":
            value_input = self.query_one("#edit-value-input", TextArea)
            self.dismiss(value_input.text) # Return the new value
        elif event.button.id == "edit-cancel-btn":
            self.dismiss(None) # Return None if cancelled