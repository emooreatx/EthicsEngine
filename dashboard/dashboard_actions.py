# dashboard/dashboard_actions.py
"""
Contains action handlers for the Data Management view in the dashboard.

These functions are typically called in response to button presses and
handle creating, editing, and deleting data items (Scenarios, Models, Species)
by interacting with the underlying JSON files and triggering UI updates.

Note: These currently use placeholder logic for user input (modals are needed).
"""
import os
import json
from pathlib import Path

# Import helpers and constants from dashboard_utils
from dashboard.dashboard_utils import (
    load_json, # Utility for loading JSON data
    save_json, # Utility for saving JSON data
    SCENARIOS_FILE, # Path constant
    GOLDEN_PATTERNS_FILE, # Path constant
    SPECIES_FILE, # Path constant
)

# --- Data Management Actions ---

def handle_data_create(app, data_type: str):
    """
    Handles creating a new data item (Scenario, Model, or Species).

    Currently uses placeholder logic to add a new entry. A modal dialog
    should be implemented to get the actual key/value from the user.

    Args:
        app: The main application instance (provides access to data).
        data_type: The type of data ("Scenarios", "Models", "Species").
    """
    print(f"Attempting to create item for: {data_type}") # Placeholder log

    # Determine the target data dictionary and file path based on type
    if data_type == "Scenarios":
        data_dict = app.scenarios # Expected to be a list
        file_path = SCENARIOS_FILE
        # Placeholder: Generate a unique key/ID (Modal should get this)
        new_key = f"NewScenario{len(data_dict) + 1}" if isinstance(data_dict, list) else "NewScenario_ERR"
        new_value = "Enter scenario description here." # Placeholder value
    elif data_type == "Models":
        data_dict = app.models # Expected to be a dict
        file_path = GOLDEN_PATTERNS_FILE
        # Placeholder: Generate a unique key (Modal should get this)
        new_key = f"NewModel{len(data_dict) + 1}" if isinstance(data_dict, dict) else "NewModel_ERR"
        new_value = "Enter model description here." # Placeholder value
    elif data_type == "Species":
        data_dict = app.species # Expected to be a dict
        file_path = SPECIES_FILE
        # Placeholder: Generate a unique key (Modal should get this)
        new_key = f"NewSpecies{len(data_dict) + 1}" if isinstance(data_dict, dict) else "NewSpecies_ERR"
        new_value = "Enter species traits here." # Placeholder value
    else:
        # Handle unknown data type
        print(f"Error: Unknown data type '{data_type}' for create action.")
        return

    # Validate data structure before modification (basic check)
    # Note: Scenarios are lists, Models/Species are dicts. This needs refinement.
    if data_type == "Scenarios":
        if not isinstance(data_dict, list):
             print(f"Error: Scenario data is not a list. Cannot add item.")
             return
        # Check for duplicate ID in list format
        if any(isinstance(item, dict) and item.get("id") == new_key for item in data_dict):
             print(f"Error: Scenario ID '{new_key}' already exists.")
             return
        # Append new scenario dictionary (placeholder structure)
        data_dict.append({"id": new_key, "prompt": new_value, "tags": [], "evaluation_criteria": {}})
    else: # Models and Species (assuming dict format)
        if not isinstance(data_dict, dict) or "_load_error" in data_dict or "Error" in data_dict:
             print(f"Error: Cannot add to {data_type} data due to load error or invalid format.")
             return
        if new_key in data_dict:
             print(f"Error: Key '{new_key}' already exists in {data_type}.")
             return
        # Add new key-value pair
        data_dict[new_key] = new_value

    # Save the modified data back to the JSON file
    save_json(file_path, data_dict)
    print(f"Placeholder: Created '{new_key}' in {data_type}. Refreshing view needed.")

    # Trigger view refresh in DataManagementView after save
    try:
        # Find the DataManagementView instance and call its update method
        view = app.query_one("DataManagementView") # Assuming default ID "data-management-view"
        view._update_list_view()
    except Exception as e:
        print(f"Could not find DataManagementView to refresh after create: {e}")


def handle_data_edit(app, data_type: str, selected_key: str):
    """
    Handles editing a selected data item (Scenario, Model, or Species).

    Currently uses placeholder logic to modify the value. A modal dialog
    should be implemented to get the updated value from the user.

    Args:
        app: The main application instance.
        data_type: The type of data ("Scenarios", "Models", "Species").
        selected_key: The key or ID of the item to edit.
    """
    print(f"Attempting to edit item: {selected_key} in {data_type}") # Placeholder log
    if not selected_key:
        print("No item selected.")
        return

    # Determine the target data dictionary and file path
    if data_type == "Scenarios":
        data_dict = app.scenarios # List
        file_path = SCENARIOS_FILE
    elif data_type == "Models":
        data_dict = app.models # Dict
        file_path = GOLDEN_PATTERNS_FILE
    elif data_type == "Species":
        data_dict = app.species # Dict
        file_path = SPECIES_FILE
    else:
        print(f"Error: Unknown data type '{data_type}' for edit action.")
        return

    # Placeholder edit logic - Replace with modal interaction
    new_value = None
    if data_type == "Scenarios":
        if not isinstance(data_dict, list):
             print(f"Error: Scenario data is not a list. Cannot edit item.")
             return
        # Find the scenario dict by ID and update its prompt (placeholder)
        found = False
        for item in data_dict:
            if isinstance(item, dict) and item.get("id") == selected_key:
                item["prompt"] = str(item.get("prompt", "")) + " (edited)" # Placeholder edit
                new_value = item["prompt"] # Store the new value for saving confirmation
                found = True
                break
        if not found:
            print(f"Error: Scenario ID '{selected_key}' not found.")
            return
    else: # Models and Species (Dict)
        if not isinstance(data_dict, dict) or "_load_error" in data_dict or "Error" in data_dict:
             print(f"Error: Cannot edit {data_type} data due to load error or invalid format.")
             return
        if selected_key not in data_dict:
            print(f"Error: Key '{selected_key}' not found in {data_type}.")
            return
        # Placeholder edit
        new_value = str(data_dict[selected_key]) + " (edited)"
        data_dict[selected_key] = new_value

    # Save the modified data
    if new_value is not None: # Check if an edit was actually performed
        save_json(file_path, data_dict)
        print(f"Placeholder: Edited '{selected_key}'. Refreshing view needed.")
        # Trigger view refresh
        try:
            view = app.query_one("DataManagementView")
            view._update_list_view()
        except Exception as e:
            print(f"Could not find DataManagementView to refresh after edit: {e}")


def handle_data_delete(app, data_type: str, selected_key: str):
    """
    Handles deleting a selected data item (Scenario, Model, or Species).

    Args:
        app: The main application instance.
        data_type: The type of data ("Scenarios", "Models", "Species").
        selected_key: The key or ID of the item to delete.
    """
    print(f"Attempting to delete item: {selected_key} in {data_type}") # Placeholder log
    if not selected_key:
        print("No item selected.")
        return

    # TODO: Add confirmation dialog logic here in a real app

    # Determine the target data dictionary and file path
    if data_type == "Scenarios":
        data_dict = app.scenarios # List
        file_path = SCENARIOS_FILE
    elif data_type == "Models":
        data_dict = app.models # Dict
        file_path = GOLDEN_PATTERNS_FILE
    elif data_type == "Species":
        data_dict = app.species # Dict
        file_path = SPECIES_FILE
    else:
        print(f"Error: Unknown data type '{data_type}' for delete action.")
        return

    # Perform deletion based on data type
    deleted = False
    if data_type == "Scenarios":
        if not isinstance(data_dict, list):
             print(f"Error: Scenario data is not a list. Cannot delete item.")
             return
        initial_len = len(data_dict)
        # Remove item from list by ID
        app.scenarios = [item for item in data_dict if not (isinstance(item, dict) and item.get("id") == selected_key)]
        data_dict = app.scenarios # Update local reference after modification
        deleted = len(data_dict) < initial_len
    else: # Models and Species (Dict)
        if not isinstance(data_dict, dict) or "_load_error" in data_dict or "Error" in data_dict:
             print(f"Error: Cannot delete from {data_type} data due to load error or invalid format.")
             return
        if selected_key in data_dict:
            del data_dict[selected_key]
            deleted = True

    # Save and refresh if deletion occurred
    if deleted:
        save_json(file_path, data_dict)
        print(f"Deleted '{selected_key}' from {data_type}. Refreshing view needed.")
        # Trigger view refresh
        try:
            view = app.query_one("DataManagementView")
            view._update_list_view()
        except Exception as e:
            print(f"Could not find DataManagementView to refresh after delete: {e}")
    else:
        print(f"Error: Key/ID '{selected_key}' not found in {data_type}.")
