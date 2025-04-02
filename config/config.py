# config.py
import os
import json # Added for loading settings
import asyncio
import os # Already imported, but ensure it's used for rename
import json # Added for loading settings
import asyncio
import logging
# import logging.handlers # No longer needed for RotatingFileHandler
import threading # Added for TrackedSemaphore's lock
import sys # Added for stderr printing
# import atexit # Removed for shutdown hook
from autogen import LLMConfig # Keep LLMConfig import

# --- Default Settings ---
DEFAULT_SETTINGS = {
    "llm_config_list": [
        {
            "model": "gpt-4o-mini",
            "api_key": "env:OPENAI_API_KEY" # Default to checking env var
        }
    ],
    "concurrency": 10,
    "log_level": "INFO",
    "agent_timeout": 300,
    "reasoning_specs": {
        "low": {
            "description": "Low detail reasoning configuration",
            "max_depth": 1,
            "max_tokens": 50,
            "temperature": 0.3,
        },
        "medium": {
            "description": "Medium detail reasoning configuration",
            "max_depth": 2,
            "max_tokens": 100,
            "temperature": 0.5,
        },
        "high": {
            "description": "High detail reasoning configuration",
            "max_depth": 3,
            "max_tokens": 150,
            "temperature": 0.7,
        },
    }
}
SETTINGS_FILE_PATH = "config/settings.json"
LOG_FILE_PATH = "app.log" # Define log path early

# Define logger instance for use by this module and for export.
# Configuration will be applied after settings are loaded.
logger = logging.getLogger("EthicsEngine_Logger") # Use a distinct name or just get root logger? Let's use a name.

# --- Settings Loading Function ---
def load_settings():
    """Loads settings from settings.json, falling back to defaults."""
    settings = DEFAULT_SETTINGS.copy() # Start with defaults
    try:
        with open(SETTINGS_FILE_PATH, 'r') as f:
            loaded_settings = json.load(f)
            # Deep merge would be better for nested dicts like reasoning_specs,
            # but for now, simple update is okay for top-level keys.
            # We'll specifically handle llm_config_list later.
            settings.update(loaded_settings)
            # logger.info(f"Successfully loaded settings from {SETTINGS_FILE_PATH}") # Removed

    except FileNotFoundError:
        # logger.warning(f"{SETTINGS_FILE_PATH} not found. Using default settings.") # Removed
        # Save defaults if file doesn't exist to make it discoverable
        try:
            with open(SETTINGS_FILE_PATH, 'w') as f:
                json.dump(DEFAULT_SETTINGS, f, indent=2)
            # logger.info(f"Created default {SETTINGS_FILE_PATH}.") # Removed
        except Exception as e:
            # logger.error(f"Could not create default {SETTINGS_FILE_PATH}: {e}") # Removed
            # Optionally re-raise or handle differently if logging is removed
            print(f"ERROR: Could not create default {SETTINGS_FILE_PATH}: {e}", file=sys.stderr) # Print critical error

    except json.JSONDecodeError:
        # logger.error(f"Error decoding JSON from {SETTINGS_FILE_PATH}. Using default settings.", exc_info=True) # Removed
        # Keep using the initial default settings
        print(f"ERROR: Error decoding JSON from {SETTINGS_FILE_PATH}. Using default settings.", file=sys.stderr) # Print critical error

    # Process llm_config_list for environment variables
    processed_llm_config_list = []
    raw_llm_list = settings.get("llm_config_list", DEFAULT_SETTINGS["llm_config_list"]) # Use loaded or default
    for config_item in raw_llm_list:
        processed_item = config_item.copy()
        api_key_setting = processed_item.get("api_key")
        if isinstance(api_key_setting, str) and api_key_setting.startswith("env:"):
            env_var_name = api_key_setting.split(":", 1)[1]
            api_key = os.environ.get(env_var_name)
            if api_key:
                processed_item["api_key"] = api_key
                # logger.debug(f"Loaded API key from environment variable {env_var_name}") # Removed
            else:
                # logger.warning(f"Environment variable {env_var_name} specified in settings but not found. API key may be missing for model: {processed_item.get('model', 'N/A')}") # Removed
                # Keep the original "env:..." string or remove? Let's remove for safety.
                del processed_item["api_key"] # Or set to None, depending on autogen needs
        processed_llm_config_list.append(processed_item)

    # Update settings dict with processed list
    settings["llm_config_list"] = processed_llm_config_list

    # Validate log level
    log_level_str = settings.get("log_level", DEFAULT_SETTINGS["log_level"]).upper()
    if log_level_str not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        # logger.warning(f"Invalid log_level '{log_level_str}' in settings. Falling back to INFO.") # Removed
        settings["log_level"] = "INFO"
    else:
        settings["log_level"] = log_level_str # Store the validated upper-case version

    # Validate concurrency
    concurrency_val = settings.get("concurrency", DEFAULT_SETTINGS["concurrency"])
    if not isinstance(concurrency_val, int) or concurrency_val <= 0:
        # logger.warning(f"Invalid concurrency '{concurrency_val}' in settings. Falling back to {DEFAULT_SETTINGS['concurrency']}.") # Removed
        settings["concurrency"] = DEFAULT_SETTINGS["concurrency"]

    # Validate agent_timeout
    timeout_val = settings.get("agent_timeout", DEFAULT_SETTINGS["agent_timeout"])
    if not isinstance(timeout_val, (int, float)) or timeout_val <= 0:
        # logger.warning(f"Invalid agent_timeout '{timeout_val}' in settings. Falling back to {DEFAULT_SETTINGS['agent_timeout']}.") # Removed
        settings["agent_timeout"] = DEFAULT_SETTINGS["agent_timeout"]

    # Validate reasoning_specs (basic structure check)
    specs = settings.get("reasoning_specs", DEFAULT_SETTINGS["reasoning_specs"])
    if not isinstance(specs, dict):
         # logger.warning(f"Invalid reasoning_specs format in settings. Falling back to defaults.") # Removed
         settings["reasoning_specs"] = DEFAULT_SETTINGS["reasoning_specs"]
    else:
        # Could add more detailed validation per spec level if needed
        pass


    return settings

# --- Load Settings ---
settings = load_settings()
# --- End Load Settings ---


# --- Reasoning Specifications ---
# Loaded from settings
AG2_REASONING_SPECS = settings["reasoning_specs"]
# --- End Reasoning Specifications ---


# --- LLM Configuration (Moved Up) ---
# Configure the Large Language Model(s) AutoGen will use based on loaded settings.
llm_config = LLMConfig(
    config_list=settings["llm_config_list"]
    # Optional: Add other LLMConfig parameters like 'temperature' if you want a default
    # temperature applied to all models in the list unless overridden elsewhere.
    # "temperature": 0.5, # Example: Could also be loaded from settings if needed
)

# Define logger early for use in API key check - MOVED UP

# Check if the primary API key (assuming first entry needs one) was actually found
# This check is now less direct as the key is processed in load_settings
primary_config = settings["llm_config_list"][0] if settings["llm_config_list"] else {}
if "api_key" not in primary_config and "env:OPENAI_API_KEY" in str(DEFAULT_SETTINGS["llm_config_list"]): # Check if default expected an env var
     # Warning is now logged during load_settings if env var is missing
     pass # logger.warning("Primary API key (e.g., OPENAI_API_KEY) might be missing based on settings.")

# --- End LLM Configuration ---


# --- Logger Setup ---
# The logger instance ('logger') is defined earlier.
# File handler configuration is removed. Logging handlers (like console)
# will be managed conditionally in the main script (ethicsengine.py).
# The logger's level is set based on settings during basicConfig in ethicsengine.py.
# --- End Logger Setup ---

# --- TrackedSemaphore Class Definition ---
# No changes needed inside the class itself, but its instantiation below will change.
class TrackedSemaphore:
    """
    A wrapper around asyncio.Semaphore that tracks the number of active acquirers.
    Uses threading.Lock for thread-safe counter updates.
    """
    def __init__(self, value: int):
        if not isinstance(value, int) or value < 0:
            raise ValueError("Semaphore initial value must be a non-negative integer")
        self._capacity = value
        self._semaphore = asyncio.Semaphore(value)
        self._active_count = 0
        self._count_lock = threading.Lock()
        # Use the specific config logger for this message
        # config_logger.info(f"Initialized TrackedSemaphore with capacity {self._capacity}") # Removed

    @property
    def capacity(self) -> int:
        """Returns the total capacity of the semaphore."""
        return self._capacity

    @property
    def active_count(self) -> int:
        """Returns the current number of active acquirers (thread-safe)."""
        with self._count_lock:
            return self._active_count

    async def acquire(self) -> bool:
        await self._semaphore.acquire()
        with self._count_lock:
            self._active_count += 1
            # Use config_logger for debug messages internal to this class if desired
            # config_logger.debug(f"Task acquired, active count now: {self._active_count}") # Removed
        return True

    def release(self) -> None:
        should_release_sema = False
        with self._count_lock:
            if self._active_count <= 0:
                # config_logger.warning("Release called when active_count is already zero or negative.") # Removed
                pass # Keep block valid
            else:
                self._active_count -= 1
                should_release_sema = True
                # config_logger.debug(f"Task released, active count now: {self._active_count}") # Removed
        if should_release_sema:
            self._semaphore.release()
        else:
            pass # Add pass to create a valid empty block

    async def __aenter__(self):
        """Acquires the semaphore when entering an async context."""
        await self.acquire()
        # Return self or the underlying semaphore if needed by the context
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Releases the semaphore when exiting an async context."""
        self.release()
        # Return False to propagate exceptions, True to suppress
        return False
# --- End TrackedSemaphore Class Definition ---


# --- Global Semaphore Instantiation ---
# Use concurrency value from loaded settings
SEMAPHORE_CAPACITY = settings["concurrency"]
# Ensure TrackedSemaphore class definition is ABOVE this line
semaphore = TrackedSemaphore(SEMAPHORE_CAPACITY)
# config_logger.info(f"Semaphore initialized with capacity: {SEMAPHORE_CAPACITY}") # Log with config_logger # Removed
# --- End Semaphore Instantiation ---


# --- Other Constants ---
# Use agent_timeout value from loaded settings
AGENT_TIMEOUT = settings["agent_timeout"]
# config_logger.info(f"Agent timeout set to: {AGENT_TIMEOUT}") # Log with config_logger # Removed
# --- End Other Constants ---

# config_logger.info("Configuration loading process complete.") # Log with config_logger # Removed
