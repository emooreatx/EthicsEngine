# config.py
"""
Handles loading and validation of application settings from config/settings.json.

Provides default settings and manages configuration for LLMs, concurrency,
logging, agent behavior (timeout, reasoning specs), and the global semaphore.
"""
import os
import json
import asyncio
import logging
import threading
import sys
from autogen import LLMConfig # Required for LLM configuration object

# --- Default Settings ---
# These are used if settings.json is missing or invalid.
DEFAULT_SETTINGS = {
    "llm_config_list": [
        {
            "model": "gpt-4o-mini", # Default model
            "api_key": "env:OPENAI_API_KEY" # Default to checking env var OPENAI_API_KEY
        }
    ],
    "concurrency": 10, # Default max concurrent agent runs
    "log_level": "INFO", # Default logging level
    "agent_timeout": 300, # Default timeout for agent operations in seconds
    "reasoning_specs": { # Default configurations for different reasoning levels
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
SETTINGS_FILE_PATH = "config/settings.json" # Path to the user settings file
LOG_FILE_PATH = "app.log" # Path for the application log file

# --- Logger Setup ---
# Define logger instance for use by this module and for export.
# Actual configuration (level, handlers) is applied later based on loaded settings.
logger = logging.getLogger("EthicsEngine_Logger") # Use a distinct name for the project logger

# --- Settings Loading Function ---
def load_settings():
    """
    Loads settings from settings.json, falling back to defaults.
    Validates loaded settings and processes environment variables for API keys.
    Creates a default settings.json if it doesn't exist.

    Returns:
        dict: The validated settings dictionary.
    """
    settings = DEFAULT_SETTINGS.copy() # Start with defaults
    try:
        # Try to open and load the user settings file
        with open(SETTINGS_FILE_PATH, 'r') as f:
            loaded_settings = json.load(f)
            # Update the defaults with loaded settings (simple top-level merge)
            settings.update(loaded_settings)
            logger.debug(f"Successfully loaded settings from {SETTINGS_FILE_PATH}")

    except FileNotFoundError:
        logger.warning(f"{SETTINGS_FILE_PATH} not found. Creating with default settings.")
        # Save defaults if file doesn't exist to make it discoverable
        try:
            with open(SETTINGS_FILE_PATH, 'w') as f:
                json.dump(DEFAULT_SETTINGS, f, indent=2)
            logger.info(f"Created default {SETTINGS_FILE_PATH}.")
        except Exception as e:
            # Log critical error if default file cannot be created
            logger.error(f"Could not create default {SETTINGS_FILE_PATH}: {e}")
            print(f"ERROR: Could not create default {SETTINGS_FILE_PATH}: {e}", file=sys.stderr)

    except json.JSONDecodeError:
        # Handle invalid JSON in the settings file
        logger.error(f"Error decoding JSON from {SETTINGS_FILE_PATH}. Using default settings.", exc_info=True)
        print(f"ERROR: Error decoding JSON from {SETTINGS_FILE_PATH}. Using default settings.", file=sys.stderr)
        settings = DEFAULT_SETTINGS.copy() # Ensure we revert fully to defaults

    # --- Post-Load Processing and Validation ---

    # Process llm_config_list for environment variables (e.g., "env:VAR_NAME")
    processed_llm_config_list = []
    raw_llm_list = settings.get("llm_config_list", DEFAULT_SETTINGS["llm_config_list"])
    for config_item in raw_llm_list:
        processed_item = config_item.copy()
        api_key_setting = processed_item.get("api_key")
        # Check if api_key is specified as an environment variable
        if isinstance(api_key_setting, str) and api_key_setting.startswith("env:"):
            env_var_name = api_key_setting.split(":", 1)[1]
            api_key = os.environ.get(env_var_name) # Attempt to load from environment
            if api_key:
                processed_item["api_key"] = api_key # Replace "env:..." with actual key
                logger.debug(f"Loaded API key from environment variable {env_var_name}")
            else:
                # If env var not found, remove the api_key entry to avoid issues
                logger.warning(f"Environment variable {env_var_name} specified in settings but not found. API key may be missing for model: {processed_item.get('model', 'N/A')}")
                if "api_key" in processed_item:
                    del processed_item["api_key"]
        processed_llm_config_list.append(processed_item)
    settings["llm_config_list"] = processed_llm_config_list # Update settings with processed list

    # Validate log_level
    log_level_str = settings.get("log_level", DEFAULT_SETTINGS["log_level"]).upper()
    if log_level_str not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
        logger.warning(f"Invalid log_level '{log_level_str}' in settings. Falling back to INFO.")
        settings["log_level"] = "INFO"
    else:
        settings["log_level"] = log_level_str # Store the validated upper-case version

    # Validate concurrency
    concurrency_val = settings.get("concurrency", DEFAULT_SETTINGS["concurrency"])
    if not isinstance(concurrency_val, int) or concurrency_val <= 0:
        logger.warning(f"Invalid concurrency '{concurrency_val}' in settings. Falling back to {DEFAULT_SETTINGS['concurrency']}.")
        settings["concurrency"] = DEFAULT_SETTINGS["concurrency"]

    # Validate agent_timeout
    timeout_val = settings.get("agent_timeout", DEFAULT_SETTINGS["agent_timeout"])
    if not isinstance(timeout_val, (int, float)) or timeout_val <= 0:
        logger.warning(f"Invalid agent_timeout '{timeout_val}' in settings. Falling back to {DEFAULT_SETTINGS['agent_timeout']}.")
        settings["agent_timeout"] = DEFAULT_SETTINGS["agent_timeout"]

    # Validate reasoning_specs (basic structure check)
    specs = settings.get("reasoning_specs", DEFAULT_SETTINGS["reasoning_specs"])
    if not isinstance(specs, dict):
         logger.warning(f"Invalid reasoning_specs format in settings. Falling back to defaults.")
         settings["reasoning_specs"] = DEFAULT_SETTINGS["reasoning_specs"]
    else:
        # Could add more detailed validation per spec level (low/medium/high) if needed
        pass

    logger.info("Settings loaded and validated.")
    return settings

# --- Global Settings Initialization ---
# Load settings when the module is imported
settings = load_settings()

# --- Exported Configuration Variables ---

# Reasoning Specifications (loaded from settings)
AG2_REASONING_SPECS = settings["reasoning_specs"]

# LLM Configuration for Autogen
# Configures the Large Language Model(s) based on the processed settings.
llm_config = LLMConfig(
    config_list=settings["llm_config_list"]
    # Optional: Add other LLMConfig parameters like 'cache_seed' if needed globally
)

# Check if the primary API key (assuming first entry needs one) was actually found
primary_config = settings["llm_config_list"][0] if settings["llm_config_list"] else {}
if "api_key" not in primary_config and "env:OPENAI_API_KEY" in str(DEFAULT_SETTINGS["llm_config_list"]):
     # Warning is logged during load_settings if env var is missing
     logger.warning("Primary API key (e.g., OPENAI_API_KEY) might be missing based on settings and environment.")

# --- TrackedSemaphore Class Definition ---
class TrackedSemaphore:
    """
    A wrapper around asyncio.Semaphore that tracks active and waiting tasks.

    Provides properties to inspect the semaphore's state for monitoring purposes.
    Uses a threading.Lock for thread-safe updates to internal counters, making it
    suitable for use across different threads or async tasks.
    """
    def __init__(self, value: int):
        """
        Initializes the TrackedSemaphore.

        Args:
            value: The maximum number of concurrent acquisitions allowed.
        """
        if not isinstance(value, int) or value < 0:
            raise ValueError("Semaphore initial value must be a non-negative integer")
        self._capacity = value
        self._semaphore = asyncio.Semaphore(value) # The underlying asyncio semaphore
        self._active_count = 0 # Number of tasks currently holding the semaphore
        self._waiting_count = 0 # Number of tasks currently waiting to acquire
        self._count_lock = threading.Lock() # Lock for thread-safe counter updates
        logger.info(f"Initialized TrackedSemaphore with capacity {self._capacity}")

    @property
    def capacity(self) -> int:
        """Returns the total capacity of the semaphore."""
        return self._capacity

    @property
    def active_count(self) -> int:
        """Returns the current number of active acquirers (thread-safe)."""
        with self._count_lock:
             return self._active_count

    @property
    def waiting_count(self) -> int:
        """Returns the current number of waiting tasks (thread-safe)."""
        with self._count_lock:
            return self._waiting_count

    async def acquire(self) -> bool:
         """Acquires the semaphore, tracking waiting and active counts."""
         # Increment waiting count *before* potentially blocking on await
         with self._count_lock:
             self._waiting_count += 1
             logger.debug(f"Task waiting. Waiting: {self._waiting_count}, Active: {self._active_count}")
         try:
             await self._semaphore.acquire() # Wait to acquire the underlying semaphore
             # Once acquired, decrement waiting and increment active count
             with self._count_lock:
                 self._waiting_count -= 1
                 self._active_count += 1
                 logger.debug(f"Task acquired. Waiting: {self._waiting_count}, Active: {self._active_count}")
         except Exception:
             # Ensure waiting count is decremented if acquire fails or is cancelled
             with self._count_lock:
                 self._waiting_count -= 1
                 logger.debug(f"Acquire failed/cancelled. Waiting: {self._waiting_count}, Active: {self._active_count}")
             raise # Re-raise the exception

         return True # Indicate successful acquisition

    def release(self) -> None:
        """Releases the semaphore, decrementing the active count."""
        should_release_sema = False
        with self._count_lock:
            if self._active_count <= 0:
                # Log a warning if release is called more times than acquire
                logger.warning("Release called when active_count is already zero or negative.")
            else:
                self._active_count -= 1
                should_release_sema = True # Mark that the underlying semaphore should be released
                logger.debug(f"Task released. Waiting: {self._waiting_count}, Active: {self._active_count}")
        if should_release_sema:
            self._semaphore.release() # Release the underlying asyncio semaphore
        else:
            # If active_count was already zero, do nothing to the underlying semaphore
            pass

    async def __aenter__(self):
        """Acquires the semaphore when entering an 'async with' block."""
        await self.acquire()
        return self # Return self to allow access to semaphore properties within the block

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Releases the semaphore when exiting an 'async with' block."""
        self.release()
        # Return False to propagate any exceptions that occurred within the block
        return False

# --- Global Semaphore Instantiation ---
# Create a single instance of the TrackedSemaphore using the concurrency value from settings
SEMAPHORE_CAPACITY = settings["concurrency"]
semaphore = TrackedSemaphore(SEMAPHORE_CAPACITY)
logger.info(f"Global semaphore initialized with capacity: {SEMAPHORE_CAPACITY}")

# --- Other Exported Constants ---
# Agent timeout value from settings
AGENT_TIMEOUT = settings["agent_timeout"]
logger.info(f"Agent timeout set to: {AGENT_TIMEOUT} seconds")
