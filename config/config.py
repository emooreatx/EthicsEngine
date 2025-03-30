# config.py
import os
import asyncio
import logging
import threading # Added for TrackedSemaphore's lock
from autogen import LLMConfig # Keep LLMConfig import

# --- Reasoning Specifications ---
# Moved from reasoning_agent.py
AG2_REASONING_SPECS = {
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
# --- End Reasoning Specifications ---


# --- LLM Configuration (Moved Up) ---
# Configure the Large Language Model(s) AutoGen will use.
# The config_list allows defining multiple models/endpoints.
llm_config = LLMConfig(
    config_list=[
        # == Configuration Option 1: OpenAI ==
        # Uses the OPENAI_API_KEY environment variable.
        
        {
            "model": "gpt-4o-mini",
            # Ensure the API key environment variable is set
            "api_key": os.environ.get("OPENAI_API_KEY", "YOUR_API_KEY_HERE"),
            # "base_url": "YOUR_OPENAI_COMPATIBLE_ENDPOINT", # Optional: For Azure OpenAI or other compatible endpoints
        },

        #Ollama configuration - replace model name accordingly
        #{
        #"model": "openthinker:7b",
        #    "api_type": "ollama",
        #    "client_host": "http://127.0.0.1:11434"
        #},
        
        # == Add other configurations as needed ==
    ]
    # Optional: Add other LLMConfig parameters like 'temperature' if you want a default
    # temperature applied to all models in the list unless overridden elsewhere.
    # "temperature": 0.5,
)

# Define logger early for use in API key check
logger = logging.getLogger("EthicsEngine_Config_Check")

# Check if the primary API key (OpenAI in this default config) was actually found
# Modify this check if you primarily use a different provider.
if not os.environ.get("OPENAI_API_KEY"):
    logger.warning("OPENAI_API_KEY environment variable not set. OpenAI models may not work.")
# --- End LLM Configuration ---


# --- Logger Setup ---
# Setup structured logging.
logging.basicConfig(level=logging.INFO)
# Remove default stream handlers from root logger
root_logger = logging.getLogger()
for handler in root_logger.handlers[:]:
    if isinstance(handler, logging.StreamHandler):
        root_logger.removeHandler(handler)

# Main application logger
logger = logging.getLogger("EthicsEngine")
logger.propagate = False # Prevent double logging to console if root handler exists

# Add file handler for INFO level messages to go to app.log
try:
    log_file_path = "app.log"
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except Exception as e:
    print(f"Error setting up file logging: {e}")
    if not logger.hasHandlers():
         logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
         logger = logging.getLogger("EthicsEngine_Fallback")
# --- End Logger Setup ---


# --- TrackedSemaphore Class Definition ---
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
        # Use the main logger defined above
        logger.info(f"Initialized TrackedSemaphore with capacity {self._capacity}")

    async def acquire(self) -> bool:
        await self._semaphore.acquire()
        with self._count_lock:
            self._active_count += 1
            logger.debug(f"Task acquired, active count now: {self._active_count}")
        return True

    def release(self) -> None:
        should_release_sema = False
        with self._count_lock:
            if self._active_count <= 0:
                logger.warning("Release called when active_count is already zero or negative.")
            else:
                self._active_count -= 1
                should_release_sema = True
                logger.debug(f"Task released, active count now: {self._active_count}")
        if should_release_sema:
            self._semaphore.release()
        else:
             logger.warning("Underlying semaphore release skipped due to count inconsistency.")

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False # Propagate exceptions

    @property
    def active_count(self) -> int:
        with self._count_lock:
            return self._active_count

    @property
    def capacity(self) -> int:
        return self._capacity

    def locked(self) -> bool:
        with self._count_lock:
            return self._active_count >= self._capacity

    def __repr__(self) -> str:
        # Access active_count via property to ensure lock is used if needed
        return f"<TrackedSemaphore capacity={self._capacity} active={self.active_count}>"
# --- End TrackedSemaphore Class Definition ---


# --- Global Semaphore Instantiation ---
SEMAPHORE_CAPACITY = 10
# Ensure TrackedSemaphore class definition is ABOVE this line
semaphore = TrackedSemaphore(SEMAPHORE_CAPACITY)
# --- End Semaphore Instantiation ---


# --- Other Constants ---
AGENT_TIMEOUT = 300
# --- End Other Constants ---

logger.info("Configuration loaded.")
