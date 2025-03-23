# data_manager.py
import json
import os

DATA_DIR = "data"

def load_json(file_path, default_data):
    """
    Load JSON data from the given file_path.
    If the file doesn't exist, it is created with the provided default_data.
    """
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return json.load(f)
    else:
        with open(file_path, "w") as f:
            json.dump(default_data, f, indent=4)
        return default_data

def save_json(file_path, data):
    """
    Save the given data to file_path as JSON.
    """
    with open(file_path, "w") as f:
        json.dump(data, f, indent=4)

if __name__ == "__main__":
    # Test the data management functions independently.
    test_file = os.path.join(DATA_DIR, "test.json")
    default_data = {"test": "value"}
    
    # Load data (this will create the file if it doesn't exist)
    data = load_json(test_file, default_data)
    print("Loaded data:", data)
    
    # Modify the data and save it back
    data["new_key"] = "new_value"
    save_json(test_file, data)
    print("Data saved successfully. Check the file:", test_file)
