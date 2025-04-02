# dashboard/dashboard_utils.py
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

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
    """Loads JSON data from a file path, using the configured logger."""
    if default_data is None:
        default_data = {}
    try:
        if file_path.exists():
            with open(file_path, "r") as f:
                return json.load(f)
        logger.warning(f"File not found - {file_path}")
        return default_data
    except json.JSONDecodeError:
        logger.error(f"Could not decode JSON from {file_path}")
        return default_data
    except Exception as e:
        logger.error(f"Error loading {file_path}: {e}", exc_info=True)
        return default_data

def save_json(file_path: Path, data: Any) -> bool:
    """Saves data to a JSON file path, using the configured logger. Returns True on success, False on failure."""
    success = False
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True) # Ensure directory exists
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
        # If we reach here without error, the file should be saved and closed.
        success = True
    except Exception as e:
        logger.error(f"Error saving to {file_path}: {e}", exc_info=True)
        success = False # Explicitly set to False on error

    if success:
        logger.info(f"Data successfully saved to {file_path}") # Log only on confirmed success

    return success

# --- NEW Utility Functions for Refactoring ---

def load_metadata_dependencies(data_dir: Path) -> Dict[str, Any]:
    """Loads species and model data required for metadata generation."""
    species_file = data_dir / "species.json"
    models_file = data_dir / "golden_patterns.json"

    species_data = load_json(species_file, {})
    model_data = load_json(models_file, {})

    # Basic validation
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
    """Generates the standard metadata dictionary for results files."""
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Extract species traits safely
    species_traits_raw = species_data.get(species, f"Unknown species '{species}'")
    if "Error" in species_data:
        species_traits = [f"Error loading species data: {species_data['Error']}"]
    else:
        species_traits = species_traits_raw.split(', ') if isinstance(species_traits_raw, str) else species_traits_raw
        if not isinstance(species_traits, list):
            species_traits = [str(species_traits)] # Ensure list

    # Extract model description safely
    model_description = model_data.get(model, f"Unknown model '{model}'")
    if "Error" in model_data:
        model_description = f"Error loading model data: {model_data['Error']}"

    # Determine agent reasoning config based on level
    reason_config_spec = reasoning_specs.get(reasoning_level, {})
    agent_reason_config = {
        "method": "beam_search", # Assuming this is standard
        "max_depth": reason_config_spec.get("max_depth", 2),
        "beam_size": 3, # Assuming standard
        "answer_approach": "pool" # Assuming standard
    }

    # Process LLM Config for Metadata (Safer handling)
    safe_llm_config = []
    if llm_config:
        try:
            config_list = getattr(llm_config, 'config_list', [])
            if config_list:
                for config_item in config_list:
                     try:
                         model_name = config_item.get('model') if isinstance(config_item, dict) else getattr(config_item, 'model', None)
                         if model_name:
                             temp = reason_config_spec.get("temperature", "N/A")
                             safe_llm_config.append({"model": model_name, "temperature": temp})
                         else: logger.warning(f"Metadata: Item lacks 'model' attribute/key: {config_item}")
                     except AttributeError: logger.warning(f"Metadata: Cannot access attributes/keys on item. Type: {type(config_item)}")
                     except Exception as item_e: logger.warning(f"Metadata: Error processing config item: {item_e}. Item: {config_item}")
            else: logger.warning("Metadata: llm_config.config_list empty/not found.")
        except AttributeError: logger.warning("Metadata: Could not access llm_config.config_list attribute.")
        except Exception as e: logger.error(f"Metadata: Error processing llm_config: {e}")
    else:
        logger.warning("Metadata: llm_config object not available for processing.")


    # Define evaluation criteria based on run type
    evaluation_criteria = {}
    if run_type == "benchmark":
        evaluation_criteria = {
            "positive": ["BENCHMARK_CORRECT"],
            "negative": ["BENCHMARK_INCORRECT", "BENCHMARK_ERROR"]
        }
    elif run_type == "scenario_pipeline":
        # Scenarios might have criteria defined per-item, leave top-level empty
        evaluation_criteria = {}

    # Final Metadata Dictionary
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
    item_id: Optional[str] = None, # For single runs
    timestamp: Optional[str] = None # Allow overriding timestamp from metadata
) -> Optional[str]:
    """
    Constructs a standard filename, saves the results using save_json,
    and returns the filename string on success, None on failure.
    """
    output_filename = None
    try:
        if not timestamp:
            # Ensure metadata exists and get timestamp from it
            metadata = data_to_save.get("metadata", {})
            timestamp = metadata.get("run_timestamp", datetime.now().strftime("%Y%m%d_%H%M%S"))

        # Construct filename based on run_type
        species_lower = species.lower()
        model_lower = model.lower()
        level_lower = level.lower()

        if run_type == "scenario_pipeline":
            filename = f"scenarios_pipeline_{species_lower}_{model_lower}_{level_lower}_{timestamp}.json"
        elif run_type == "scenario_pipeline_single" and item_id:
            safe_item_id = str(item_id).replace(" ", "_").replace("/", "-")
            filename = f"scenario_single_{safe_item_id}_{species_lower}_{model_lower}_{level_lower}_{timestamp}.json"
        elif run_type == "benchmark":
            filename = f"bench_{species_lower}_{model_lower}_{level_lower}_{timestamp}.json"
        elif run_type == "benchmark_single" and item_id:
            safe_item_id = str(item_id).replace(" ", "_").replace("/", "-")
            filename = f"bench_single_{safe_item_id}_{species_lower}_{model_lower}_{level_lower}_{timestamp}.json"
        else:
            logger.error(f"Cannot determine filename for run_type '{run_type}' (item_id: {item_id})")
            return None

        output_filename = results_dir / filename

        # Call the modified save_json
        if save_json(output_filename, data_to_save):
            # save_json already logs success, just return the path
            return str(output_filename)
        else:
            # save_json already logged the error
            return None

    except Exception as e:
        # Catch any unexpected errors during filename generation or the call itself
        logger.error(f"Error in save_results_with_standard_name: {e}", exc_info=True)
        return None

# --- END NEW Utility Functions ---
