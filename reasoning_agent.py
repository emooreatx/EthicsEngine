#!/usr/bin/env python3
import asyncio
import json
import os
from contextlib import redirect_stdout, redirect_stderr
import io

from autogen.agents.experimental import ReasoningAgent
from config.config import llm_config, AGENT_TIMEOUT, semaphore, logger

required_files = [
    "data/golden_patterns.json",
    "data/species.json",
]
for file_path in required_files:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Required file not found: {file_path}")

with open("data/golden_patterns.json", "r") as f:
    GOLDEN_PATTERNS = json.load(f)
with open("data/species.json", "r") as f:
    SPECIES_DATA = json.load(f)

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

class EthicsAgent:
    def __init__(self, species_name: str, golden_pattern: str, reasoning_level: str = "medium", data_dir: str = "data"):
        self.golden_pattern = golden_pattern
        self.reasoning_level = reasoning_level
        self.data_dir = data_dir

        species_path = os.path.join(data_dir, "species.json")
        with open(species_path, "r") as f:
            species_data = json.load(f)
        if species_name not in species_data:
            raise ValueError(f"Species '{species_name}' not found in species data.")
        self.species = {"name": species_name, "traits": species_data[species_name]}

        if self.golden_pattern not in GOLDEN_PATTERNS:
            raise ValueError(f"Model '{golden_pattern}' not found in golden patterns.")
        self.golden_patterns = GOLDEN_PATTERNS

        reason_config = AG2_REASONING_SPECS.get(self.reasoning_level)
        if reason_config is None:
            raise ValueError(f"Invalid reasoning spec level: {self.reasoning_level}. Choose from low, medium, or high.")
        logger.info(f"Starting agent for model '{self.golden_pattern}' with spec level '{self.reasoning_level}'")
        self._agent = ReasoningAgent(
            name=f"{self.golden_pattern}_agent",
            system_message=(
                f"You reason strictly according to the {self.golden_pattern} model: {self.golden_patterns[self.golden_pattern]}. "
                "Consider species-specific traits in your analysis."
            ),
            llm_config=llm_config,
            reason_config=reason_config,
            silent=True
        )

    def generate_reply(self, messages):
        return self._agent.generate_reply(messages)

    async def run_async(self, prompt, prompt_id):
        logger.info(f"Starting EthicsAgent execution (async) for prompt_id: {prompt_id}")

        if isinstance(prompt, dict):
            prompt_text = prompt.get("prompt", "")
        else:
            prompt_text = prompt

        combined_prompt = (
            f"You are a leader for the Species: {self.species['name']} - Traits: {self.species['traits']}\n"
            f"{prompt_text}"
        )

        logger.info(f"Running agent for species '{self.species['name']}' with prompt: {prompt_text}")
        logger.info(f"Using underlying agent for model {self.golden_pattern} and level {self.reasoning_level}")

        dummy = io.StringIO()
        try:
            logger.info("Awaiting reply from the underlying agent.")
            async with semaphore:
                with redirect_stdout(dummy), redirect_stderr(dummy):
                    reply = self.generate_reply([{"role": "user", "content": combined_prompt}])
                    if asyncio.iscoroutine(reply):
                        chat_result = await asyncio.wait_for(reply, timeout=AGENT_TIMEOUT)
                    else:
                        chat_result = reply
            final_response = chat_result.strip()
            logger.info(f"Reply received with length: {len(final_response)}")
            captured = dummy.getvalue()
            if captured:
                logger.debug(f"Captured output: {captured}")
        except Exception as e:
            logger.error(f"Error during execution: {str(e)}")
            final_response = f"Error: {str(e)}"

        logger.info("EthicsAgent execution completed (async).")
        return {"prompt_id": prompt_id, "result": final_response}

    def run(self, prompt, prompt_id):
        return asyncio.run(self.run_async(prompt, prompt_id))

def create_agent(species: str, golden_pattern: str, reasoning_level: str = "low", data_dir: str = "data"):
    return EthicsAgent(species, golden_pattern, reasoning_level, data_dir)

if __name__ == "__main__":
    print("Testing the EthicsAgent class.")
    logger.setLevel(10)

    test_model = "Deontological"
    test_species = "Megacricks"
    test_reasoning_level = "low"
    prompt = "What is 2+2?"
    prompt_id = "test_prompt_001"

    agent = create_agent(test_species, test_model, reasoning_level=test_reasoning_level)
    result = agent.run({"prompt": prompt}, prompt_id)
    print("\nAgent Result:", result)