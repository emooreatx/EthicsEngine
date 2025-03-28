# dashboard/dashboard_actions.py
import os
import json
from pathlib import Path

# Import helpers and constants from the new utils file
from dashboard.dashboard_utils import (
    load_json,
    save_json,
    SCENARIOS_FILE,
    GOLDEN_PATTERNS_FILE,
    SPECIES_FILE,
    # Add other file constants if needed
)

# --- Refactored Data Management Actions ---
# (Keep the function bodies as provided in the previous step)

def handle_data_create(app, data_type: str):
    """
    Handles creating a new data item.
    Needs implementation for prompting user input (e.g., via a modal dialog).
    """
    print(f"Attempting to create item for: {data_type}")
    # (Keep existing placeholder logic from previous step...)
    if data_type == "Scenarios":
        data_dict = app.scenarios
        file_path = SCENARIOS_FILE
        new_key = f"NewScenario{len(data_dict) + 1}"
        new_value = "Enter scenario description here."
    elif data_type == "Models":
        data_dict = app.models
        file_path = GOLDEN_PATTERNS_FILE
        new_key = f"NewModel{len(data_dict) + 1}"
        new_value = "Enter model description here."
    elif data_type == "Species":
        data_dict = app.species
        file_path = SPECIES_FILE
        new_key = f"NewSpecies{len(data_dict) + 1}"
        new_value = "Enter species traits here."
    else:
        print(f"Error: Unknown data type '{data_type}' for create action.")
        return

    if not isinstance(data_dict, dict) or "_load_error" in data_dict or "Error" in data_dict:
         print(f"Error: Cannot add to {data_type} data due to load error.")
         return

    if new_key in data_dict:
         print(f"Error: Key '{new_key}' already exists.")
         return

    data_dict[new_key] = new_value
    save_json(file_path, data_dict)
    print(f"Placeholder: Created '{new_key}' in {data_type}. Refreshing view needed.")
    # Trigger view refresh in DataManagementView after save
    try:
        view = app.query_one("DataManagementView") # Assuming default ID
        view._update_list_view()
    except Exception:
        print("Could not find DataManagementView to refresh.")


def handle_data_edit(app, data_type: str, selected_key: str):
    """
    Handles editing a selected data item.
    Needs implementation for prompting user input (e.g., via a modal dialog).
    """
    print(f"Attempting to edit item: {selected_key} in {data_type}")
    if not selected_key:
        print("No item selected.")
        return

    # (Keep existing logic for selecting data_dict and file_path...)
    if data_type == "Scenarios":
        data_dict = app.scenarios
        file_path = SCENARIOS_FILE
    elif data_type == "Models":
        data_dict = app.models
        file_path = GOLDEN_PATTERNS_FILE
    elif data_type == "Species":
        data_dict = app.species
        file_path = SPECIES_FILE
    else:
        print(f"Error: Unknown data type '{data_type}' for edit action.")
        return

    if not isinstance(data_dict, dict) or "_load_error" in data_dict or "Error" in data_dict:
         print(f"Error: Cannot edit {data_type} data due to load error.")
         return

    if selected_key not in data_dict:
        print(f"Error: Key '{selected_key}' not found in {data_type}.")
        return

    # Placeholder edit logic
    new_value = str(data_dict[selected_key]) + " (edited)"
    data_dict[selected_key] = new_value
    save_json(file_path, data_dict)
    print(f"Placeholder: Edited '{selected_key}'. Refreshing view needed.")
    # Trigger view refresh
    try:
        view = app.query_one("DataManagementView")
        view._update_list_view()
    except Exception:
        print("Could not find DataManagementView to refresh.")


def handle_data_delete(app, data_type: str, selected_key: str):
    """Handles deleting a selected data item."""
    print(f"Attempting to delete item: {selected_key} in {data_type}")
    if not selected_key:
        print("No item selected.")
        return

    # Add confirmation dialog logic here in a real app

    # (Keep existing logic for selecting data_dict and file_path...)
    if data_type == "Scenarios":
        data_dict = app.scenarios
        file_path = SCENARIOS_FILE
    elif data_type == "Models":
        data_dict = app.models
        file_path = GOLDEN_PATTERNS_FILE
    elif data_type == "Species":
        data_dict = app.species
        file_path = SPECIES_FILE
    else:
        print(f"Error: Unknown data type '{data_type}' for delete action.")
        return

    if not isinstance(data_dict, dict) or "_load_error" in data_dict or "Error" in data_dict:
         print(f"Error: Cannot delete from {data_type} data due to load error.")
         return

    if selected_key in data_dict:
        del data_dict[selected_key]
        save_json(file_path, data_dict)
        print(f"Deleted '{selected_key}' from {data_type}. Refreshing view needed.")
        # Trigger view refresh
        try:
            view = app.query_one("DataManagementView")
            view._update_list_view()
        except Exception:
            print("Could not find DataManagementView to refresh.")
    else:
        print(f"Error: Key '{selected_key}' not found in {data_type}.")