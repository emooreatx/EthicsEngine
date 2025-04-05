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

# --- Validators ---
class NonEmpty(Validator):
    """A simple Textual validator to ensure an input field is not empty or just whitespace."""
    def validate(self, value: str) -> ValidationResult:
        """Validate the input value."""
        if not value.strip(): # Use strip() to check for whitespace-only input
            return self.failure("Value cannot be empty.")
        return self.success()

# --- Modal Screens ---
class CreateItemScreen(ModalScreen[tuple | None]):
    """
    A modal screen for creating a new data item (e.g., Scenario, Model, Species).
    Prompts for a key/ID and a value (using TextArea for potentially long values).
    Returns a tuple (key, value) on success, or None if cancelled.
    """

    def __init__(self, data_type: str):
        """
        Initialize the CreateItemScreen.

        Args:
            data_type: The type of data being created (e.g., "Scenarios", "Models"). Used for the title.
        """
        super().__init__()
        self.data_type = data_type

    def compose(self) -> ComposeResult:
        """Compose the UI elements for the create screen."""
        with Vertical(classes="modal-container"): # Add a class for potential styling
            yield Label(f"Create New {self.data_type[:-1]}") # e.g., "Create New Scenario"
            yield Label("Key/ID:")
            yield Input(placeholder="Enter unique key/name", id="create-key-input", validators=[NonEmpty()])
            yield Label("Value/Description:")
            # Use TextArea for potentially multi-line values like prompts or descriptions
            yield TextArea(language="text", id="create-value-input", theme="vscode_dark")
            with Horizontal(classes="modal-buttons"): # Add a class for potential styling
                yield Button("Save", id="create-save-btn", variant="success")
                yield Button("Cancel", id="create-cancel-btn", variant="default")

    def on_mount(self) -> None:
        """Focus the first input field when the screen is mounted."""
        self.query_one(Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses for Save and Cancel."""
        if event.button.id == "create-save-btn":
            key_input = self.query_one("#create-key-input", Input)
            value_input = self.query_one("#create-value-input", TextArea)
            # Validate the key input before dismissing
            validation_result = key_input.validate(key_input.value)
            if not validation_result.is_valid:
                 # Display validation failures using app notifications
                 self.app.notify(
                      "\n".join(validation_result.failure_descriptions),
                      severity="error",
                      title="Validation Error"
                 )
                 return # Prevent dismissal if validation fails
            # Return tuple (key, value) stripped of leading/trailing whitespace
            self.dismiss((key_input.value.strip(), value_input.text))
        elif event.button.id == "create-cancel-btn":
            self.dismiss(None) # Return None if cancelled


class EditItemScreen(ModalScreen[str | None]):
    """
    A modal screen for editing the value of an existing data item.
    Displays the item's key/ID and provides a TextArea to modify its value.
    Returns the new value string on success, or None if cancelled.
    """

    def __init__(self, data_type: str, item_key: str, initial_value: str):
        """
        Initialize the EditItemScreen.

        Args:
            data_type: The type of data being edited (e.g., "Scenarios").
            item_key: The key/ID of the item being edited.
            initial_value: The current value of the item to pre-fill the editor.
        """
        super().__init__()
        self.data_type = data_type
        self.item_key = item_key
        self.initial_value = initial_value

    def compose(self) -> ComposeResult:
        """Compose the UI elements for the edit screen."""
        with Vertical(classes="modal-container"):
            yield Label(f"Edit {self.data_type[:-1]}: {self.item_key}")
            yield Label("Value/Description:")
            # Pre-fill the TextArea with the existing value
            yield TextArea(self.initial_value, language="text", id="edit-value-input", theme="vscode_dark")
            with Horizontal(classes="modal-buttons"):
                yield Button("Save", id="edit-save-btn", variant="success")
                yield Button("Cancel", id="edit-cancel-btn", variant="default")

    def on_mount(self) -> None:
        """Focus the text area when the screen opens."""
        self.query_one(TextArea).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses for Save and Cancel."""
        if event.button.id == "edit-save-btn":
            value_input = self.query_one("#edit-value-input", TextArea)
            self.dismiss(value_input.text) # Return the potentially modified text
        elif event.button.id == "edit-cancel-btn":
            self.dismiss(None) # Return None if cancelled
