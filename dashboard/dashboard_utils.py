# dashboard/dashboard_utils.py
import json
import os
from pathlib import Path

# --- File Path Constants ---
# Define these relative to the project root (EthicsEngine)
DATA_DIR = Path("data")
RESULTS_DIR = Path("results")
SCENARIOS_FILE = DATA_DIR / "scenarios.json"
GOLDEN_PATTERNS_FILE = DATA_DIR / "golden_patterns.json"
SPECIES_FILE = DATA_DIR / "species.json"
BENCHMARKS_FILE = DATA_DIR / "simple_bench_public.json"
# Add other data files if needed

# --- Helper Functions ---
def load_json(file_path: Path, default_data=None):
    """Loads JSON data from a file path."""
    if default_data is None:
        default_data = {}
    try:
        if file_path.exists():
            with open(file_path, "r") as f:
                return json.load(f)
        # Use logging instead of print for better practice in utils
        # import logging
        # logging.warning(f"File not found - {file_path}")
        print(f"Warning: File not found - {file_path}")
        return default_data
    except json.JSONDecodeError:
        # logging.error(f"Could not decode JSON from {file_path}")
        print(f"Error: Could not decode JSON from {file_path}")
        return default_data
    except Exception as e:
        # logging.error(f"Error loading {file_path}: {e}")
        print(f"Error loading {file_path}: {e}")
        return default_data

def save_json(file_path: Path, data):
    """Saves data to a JSON file path."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True) # Ensure directory exists
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
        # logging.info(f"Data saved to {file_path}")
        print(f"Data saved to {file_path}")
    except Exception as e:
        # logging.error(f"Error saving to {file_path}: {e}")
        print(f"Error saving to {file_path}: {e}")