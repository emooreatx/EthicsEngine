"""
Utility functions and constants for the EthicsEngine dashboard and CLI tools.

Includes helpers for loading/saving JSON, path definitions, metadata generation,
and standardized result file naming.
"""
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import argparse

# --- Logger and Config Import ---
# Attempt to import logger and config elements for use in utils
try:
    from config.config import logger, llm_config as llm_config_obj, AG2_REASONING_SPECS
except ImportError:
    # Fallback logger if config is not available (e.g., running utils standalone)
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("dashboard_utils_fallback")
    llm_config_obj = None # Indicate config is unavailable
    AG2_REASONING_SPECS = {} # Empty specs

# --- Helper Class ---
class ArgsNamespace(argparse.Namespace):
    """
    A simple Namespace class, inheriting from argparse.Namespace,
    to hold arguments passed between dashboard components and run functions.
    Ensures paths are stored as strings.
    """
    def __init__(self, data_dir, results_dir, species, model, reasoning_level, bench_file=None, scenarios_file=None):
        super().__init__() # Initialize base class
        # Store arguments, ensuring paths are strings
        self.data_dir = str(data_dir)
        self.results_dir = str(results_dir)
        self.species = species
        self.model = model
        self.reasoning_level = reasoning_level
        self.bench_file = str(bench_file) if bench_file else None
        self.scenarios_file = str(scenarios_file) if scenarios_file else None

# --- File Path Constants ---
# Define standard directory and file paths relative to the project root
DATA_DIR = Path("data") # Main data directory
RESULTS_DIR = Path("results") # Directory for saving run results
SCENARIOS_FILE = DATA_DIR / "scenarios.json" # Default scenarios file
GOLDEN_PATTERNS_FILE = DATA_DIR / "golden_patterns.json" # Reasoning models file
SPECIES_FILE = DATA_DIR / "species.json" # Species traits file
BENCHMARKS_FILE = DATA_DIR / "simple_bench_public.json" # Default benchmark file

# --- Helper Functions ---

def load_json(file_path: Path, default_data=None):
    """
    Loads JSON data from a file path with error handling.

    Args:
        file_path: The Path object representing the JSON file.
        default_data: The data to return if loading fails (defaults to {}).

    Returns:
        The loaded JSON data (usually dict or list), or default_data on error.
    """
    if default_data is None:
        default_data = {} # Default to empty dict if not specified
    try:
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f: # Specify encoding
                return json.load(f)
        # Log warning if file doesn't exist
        logger.warning(f"File not found - {file_path}")
        return default_data
    except json.JSONDecodeError:
        # Log error if JSON is invalid
        logger.error(f"Could not decode JSON from {file_path}")
        return default_data
    except Exception as e:
        # Log any other unexpected errors during loading
        logger.error(f"Error loading {file_path}: {e}", exc_info=True)
        return default_data

def save_json(file_path: Path, data: Any) -> bool:
    """
    Saves data to a JSON file path with error handling and directory creation.

    Args:
        file_path: The Path object representing the target JSON file.
        data: The data (e.g., dict, list) to save.

    Returns:
        True if saving was successful, False otherwise.
    """
    success = False
    try:
        # Ensure the parent directory exists before trying to write
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f: # Specify encoding
            json.dump(data, f, indent=2) # Use indent for readability
        success = True # Mark success only if no exceptions occurred
    except Exception as e:
        # Log any errors during saving
        logger.error(f"Error saving to {file_path}: {e}", exc_info=True)
        success = False # Ensure success is False on error

    if success:
        # Log success only after the file is presumably closed and written
        logger.info(f"Data successfully saved to {file_path}")

    return success


def load_metadata_dependencies(data_dir: Path) -> Dict[str, Any]:
    """
    Loads species and model (golden patterns) data needed for metadata generation.

    Args:
        data_dir: The Path object for the data directory.

    Returns:
        A dictionary containing 'species' and 'models' data, or error indicators.
    """
    species_file = data_dir / "species.json"
    models_file = data_dir / "golden_patterns.json"

    # Load data using the robust load_json helper
    species_data = load_json(species_file, {})
    model_data = load_json(models_file, {})

    # Basic validation of loaded data structure
    if not isinstance(species_data, dict):
        logger.error(f"Invalid format for {species_file}. Expected dict.")
        species_data = {"Error": f"Invalid format for {species_file}"}
    if not isinstance(model_data, dict):
        logger.error(f"Invalid format for {models_file}. Expected dict.")
        model_data = {"Error": f"Invalid format for {models_file}"}

    return {"species": species_data, "models": model_data}

def generate_run_metadata(
    run_type: str,
    species: str,
    model: str,
    reasoning_level: str,
    species_data: Dict[str, Any],
    model_data: Dict[str, Any],
    llm_config: Optional[Any] = llm_config_obj, # Use imported config by default
    reasoning_specs: Dict[str, Any] = AG2_REASONING_SPECS # Use imported specs by default
) -> Dict[str, Any]:
    """
    Generates the standard metadata dictionary included in results files.

    Args:
        run_type: Type of run (e.g., "benchmark", "scenario_pipeline").
        species: Name of the species used.
        model: Name of the reasoning model (golden pattern) used.
        reasoning_level: Reasoning complexity level used ("low", "medium", "high").
        species_data: The loaded dictionary of all species data.
        model_data: The loaded dictionary of all model (golden pattern) data.
        llm_config: The Autogen LLMConfig object (optional, defaults to imported).
        reasoning_specs: The dictionary of reasoning specifications (optional, defaults to imported).

    Returns:
        A dictionary containing structured metadata for the run.
    """
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") # Current timestamp

    # Extract species traits safely, handling potential errors or missing data
    species_traits_raw = species_data.get(species, f"Unknown species '{species}'")
    if "Error" in species_data:
        species_traits = [f"Error loading species data: {species_data['Error']}"]
    else:
        # Ensure traits are stored as a list of strings
        species_traits = species_traits_raw.split(', ') if isinstance(species_traits_raw, str) else species_traits_raw
        if not isinstance(species_traits, list):
            species_traits = [str(species_traits)] # Force into a list if not already

    # Extract model description safely
    model_description = model_data.get(model, f"Unknown model '{model}'")
    if "Error" in model_data:
        model_description = f"Error loading model data: {model_data['Error']}"

    # Determine agent reasoning config based on level from specs
    reason_config_spec = reasoning_specs.get(reasoning_level, {})
    agent_reason_config = {
        "method": "beam_search", # Assuming this is standard for the agent
        "max_depth": reason_config_spec.get("max_depth", 2), # Get from spec or default
        "beam_size": 3, # Assuming standard
        "answer_approach": "pool" # Assuming standard
    }

    # Process LLM Config for Metadata (extract relevant info safely)
    safe_llm_config = []
    if llm_config:
        try:
            # Access the config_list attribute if it exists
            config_list = getattr(llm_config, 'config_list', [])
            if config_list:
                # Extract model name and configured temperature for metadata
                for config_item in config_list:
                     try:
                         model_name = config_item.get('model') if isinstance(config_item, dict) else getattr(config_item, 'model', None)
                         if model_name:
                             # Get temperature specific to this reasoning level
                             temp = reason_config_spec.get("temperature", "N/A")
                             safe_llm_config.append({"model": model_name, "temperature": temp})
                         else: logger.warning(f"Metadata: LLM config item lacks 'model' attribute/key: {config_item}")
                     except AttributeError: logger.warning(f"Metadata: Cannot access attributes/keys on LLM config item. Type: {type(config_item)}")
                     except Exception as item_e: logger.warning(f"Metadata: Error processing LLM config item: {item_e}. Item: {config_item}")
            else: logger.warning("Metadata: llm_config.config_list empty or not found.")
        except AttributeError: logger.warning("Metadata: Could not access llm_config.config_list attribute.")
        except Exception as e: logger.error(f"Metadata: Error processing llm_config: {e}")
    else:
        logger.warning("Metadata: llm_config object not available for processing.")

    # Define top-level evaluation criteria based on run type (can be overridden per item)
    evaluation_criteria = {}
    if run_type == "benchmark":
        # Standard criteria for benchmarks
        evaluation_criteria = {
            "positive": ["BENCHMARK_CORRECT"],
            "negative": ["BENCHMARK_INCORRECT", "BENCHMARK_ERROR"]
        }
    elif run_type == "scenario_pipeline":
        # Scenarios might have criteria defined per-item, leave top-level empty
        evaluation_criteria = {}
        # Example: Could add default scenario criteria here if applicable

    # Assemble the final metadata dictionary
    metadata = {
        "run_timestamp": run_timestamp,
        "run_type": run_type,
        "species_name": species,
        "species_traits": species_traits,
        "reasoning_model": model,
        "model_description": model_description,
        "reasoning_level": reasoning_level,
        "agent_reasoning_config": agent_reason_config,
        "llm_config": safe_llm_config,
        "tags": [], # Placeholder for potential future top-level tags
        "evaluation_criteria": evaluation_criteria
    }
    return metadata


def save_results_with_standard_name(
    results_dir: Path,
    run_type: str,
    species: str,
    model: str,
    level: str,
    data_to_save: Dict[str, Any],
    item_id: Optional[str] = None, # Optional ID for single item runs
    timestamp: Optional[str] = None # Optional timestamp override
) -> Optional[str]:
    """
    Constructs a standardized filename based on run parameters, handles potential
    filename collisions by appending sequence numbers, saves the data using save_json,
    and returns the final filename string on success, None on failure.

    Args:
        results_dir: Path object for the directory to save results.
        run_type: Type of run (e.g., "benchmark", "scenario_pipeline_single").
        species: Species name used.
        model: Model name used.
        level: Reasoning level used.
        data_to_save: The dictionary (metadata + results) to save.
        item_id: The specific ID of the item run (for single runs).
        timestamp: An optional timestamp string (YYYYMMDD_HHMMSS), defaults to current time via metadata.

    Returns:
        The absolute path string of the saved file on success, or None on failure.
    """
    output_filename = None # Initialize
    try:
        # Get timestamp from metadata or generate if needed/overridden
        if not timestamp:
            metadata = data_to_save.get("metadata", {})
            timestamp = metadata.get("run_timestamp", datetime.now().strftime("%Y%m%d_%H%M%S"))

        # Standardize components for filename
        species_lower = species.lower()
        model_lower = model.lower()
        level_lower = level.lower()

        # Construct base filename based on run type
        if run_type == "scenario_pipeline":
            filename = f"scenarios_pipeline_{species_lower}_{model_lower}_{level_lower}_{timestamp}.json"
        elif run_type == "scenario_pipeline_single" and item_id:
            safe_item_id = str(item_id).replace(" ", "_").replace("/", "-") # Sanitize ID
            filename = f"scenario_single_{safe_item_id}_{species_lower}_{model_lower}_{level_lower}_{timestamp}.json"
        elif run_type == "benchmark":
            filename = f"bench_{species_lower}_{model_lower}_{level_lower}_{timestamp}.json"
        elif run_type == "benchmark_single" and item_id:
            safe_item_id = str(item_id).replace(" ", "_").replace("/", "-") # Sanitize ID
            filename = f"bench_single_{safe_item_id}_{species_lower}_{model_lower}_{level_lower}_{timestamp}.json"
        else:
            # Log error if filename cannot be determined
            logger.error(f"Cannot determine filename for run_type '{run_type}' (item_id: {item_id})")
            return None

        # --- Handle potential filename collisions ---
        base_filename_part = filename.rsplit('.', 1)[0] # Filename without extension
        extension = filename.rsplit('.', 1)[1] if '.' in filename else 'json' # Assume .json if no ext
        output_filepath = results_dir / filename # Initial proposed path
        sequence = 1

        # Check for existing file and append sequence number (e.g., _001, _002) if needed
        while output_filepath.exists():
            new_filename = f"{base_filename_part}_{sequence:03d}.{extension}"
            output_filepath = results_dir / new_filename
            sequence += 1
            if sequence > 999: # Safety break to prevent infinite loop
                 logger.error(f"Could not find unique filename after 999 attempts for base: {base_filename_part}")
                 return None
        # --- End collision handling ---

        # Call save_json with the determined unique filepath
        if save_json(output_filepath, data_to_save):
            # save_json already logs success, just return the absolute path string
            return str(output_filepath.absolute())
        else:
            # save_json already logged the error
            return None

    except Exception as e:
        # Catch any unexpected errors during filename generation or saving
        logger.error(f"Error in save_results_with_standard_name: {e}", exc_info=True)
        return None
