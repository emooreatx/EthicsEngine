# config.py
import os
import asyncio
import logging
from autogen import LLMConfig, UserProxyAgent

# Setup structured logging.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EthicsEngine")

llm_config = LLMConfig(
    config_list=[
        {
            "model": "gpt-4o-mini",
            "api_key": os.environ["OPENAI_API_KEY"],
        }
    ]
)

reason_config_minimal = {"method": "beam_search", "beam_size": 1, "max_depth": 2}

user_proxy = UserProxyAgent(
    name="user_proxy",
    human_input_mode="NEVER",
    code_execution_config=False,
    max_consecutive_auto_reply=1000
)

# Global semaphore to limit concurrent tasks.
semaphore = asyncio.Semaphore(5)
AGENT_TIMEOUT = 300
