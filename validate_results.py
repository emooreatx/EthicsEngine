import json
import os
from jsonschema import validate, ValidationError

RESULTS_DIR = "results"
SCHEMA_FILE = "output_schema.json"

def load_json(filepath):
    """Loads JSON data from a file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {filepath}: {e}")
        return None
    except FileNotFoundError:
        print(f"Error: File not found {filepath}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred loading {filepath}: {e}")
        return None

def validate_results():
    """Validates all JSON files in the results directory against the schema."""
    schema = load_json(SCHEMA_FILE)
    if schema is None:
        print(f"Could not load schema file {SCHEMA_FILE}. Exiting.")
        return

    if not os.path.isdir(RESULTS_DIR):
        print(f"Error: Results directory '{RESULTS_DIR}' not found. Exiting.")
        return

    print(f"Validating files in '{RESULTS_DIR}' against '{SCHEMA_FILE}'...")
    print("-" * 30)

    found_files = False
    invalid_files = 0

    for filename in os.listdir(RESULTS_DIR):
        if filename.endswith(".json"):
            found_files = True
            filepath = os.path.join(RESULTS_DIR, filename)
            data = load_json(filepath)

            if data is not None:
                try:
                    validate(instance=data, schema=schema)
                    print(f"✅ {filename}: VALID")
                except ValidationError as e:
                    invalid_files += 1
                    print(f"❌ {filename}: INVALID")
                    # Print a concise version of the error
                    print(f"   Error: {e.message} (Path: {'/'.join(map(str, e.path))})")
                except Exception as e:
                    invalid_files += 1
                    print(f"❌ {filename}: ERROR during validation")
                    print(f"   Unexpected error: {e}")

    print("-" * 30)
    if not found_files:
        print(f"No JSON files found in '{RESULTS_DIR}'.")
    elif invalid_files == 0:
        print("All found JSON files are valid.")
    else:
        print(f"{invalid_files} file(s) failed validation.")

if __name__ == "__main__":
    validate_results()
