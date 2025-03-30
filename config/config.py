# config.py
import os
import asyncio
import logging
from autogen import LLMConfig, UserProxyAgent

# Setup structured logging.
logging.basicConfig(level=logging.INFO)
# Remove default stream handlers from root logger
root_logger = logging.getLogger()
for handler in root_logger.handlers[:]:
    if isinstance(handler, logging.StreamHandler):
        root_logger.removeHandler(handler)
        
logger = logging.getLogger("EthicsEngine")

# Prevent log messages from propagating to the root logger (and thus stdout)
logger.propagate = False

# Add file handler for INFO level messages to go to app.log
file_handler = logging.FileHandler("app.log")
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

llm_config = LLMConfig(
    config_list=[
        {
            "model": "gpt-4o-mini",
            "api_key": os.environ["OPENAI_API_KEY"],
        }
    ]
)



# Global semaphore to limit concurrent tasks.
semaphore = asyncio.Semaphore(10)
AGENT_TIMEOUT = 300
