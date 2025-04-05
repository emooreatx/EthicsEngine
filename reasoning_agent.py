# EthicsEngine/reasoning_agent.py
#!/usr/bin/env python3
"""
Defines the EthicsAgent class which uses Autogen's ReasoningAgent
to analyze ethical scenarios based on species traits and reasoning models.
"""
import asyncio
import json
import os
from contextlib import redirect_stdout, redirect_stderr
import io
import logging
import time
from typing import Optional, Any

# --- Autogen Import (Conditional) ---
try:
    # Attempt to import the core ReasoningAgent components
    from autogen.agents.experimental import ReasoningAgent, ThinkNode
    AUTOGEN_AVAILABLE = True
except ImportError:
    # Handle cases where autogen might not be installed
    print("ERROR: Could not import Autogen components (ReasoningAgent, ThinkNode). Please ensure autogen is installed correctly.")
    AUTOGEN_AVAILABLE = False
    # Define dummy classes/functions if import fails to prevent crashes
    class ThinkNode:
         """Dummy ThinkNode if autogen is unavailable."""
         def __init__(self, content, parent=None): self.content=content; self.depth=0; self.value=0; self.visits=0; self.children=[]
         def to_dict(self): return {"content": self.content, "children": []}
    class ReasoningAgent:
         """Dummy ReasoningAgent if autogen is unavailable."""
         def __init__(self, *args, **kwargs): self._root = None
         def generate_reply(self, *args, **kwargs): return "Dummy Reply - Autogen Import Failed"
         def extract_sft_dataset(self): return [{"instruction": "dummy", "response": "dummy trajectory - Autogen Import Failed"}]

# --- Project Imports ---
# Import necessary configurations and the semaphore from config.py
from config.config import llm_config, AGENT_TIMEOUT, semaphore, logger, AG2_REASONING_SPECS

# --- Constants ---
# Define required data files relative to the data directory
REQUIRED_FILES = [
    "data/golden_patterns.json",
    "data/species.json",
]

# --- EthicsAgent Class ---
class EthicsAgent:
    """
    Wraps Autogen's ReasoningAgent to provide ethical reasoning capabilities
    tailored by species traits and a specific reasoning model (golden pattern).

    Attributes:
        golden_pattern (str): The name of the reasoning model to use.
        reasoning_level (str): The complexity level ("low", "medium", "high").
        data_dir (str): Path to the directory containing species and model data.
        species (dict): Loaded data for the specified species.
        golden_patterns (dict): Loaded data for all reasoning models.
        _agent (ReasoningAgent): The underlying Autogen ReasoningAgent instance.
    """
    def __init__(self, species_name: str, golden_pattern: str, reasoning_level: str = "medium", data_dir: str = "data"):
        """
        Initializes the EthicsAgent.

        Args:
            species_name: Name of the species to load traits for.
            golden_pattern: Name of the reasoning model (golden pattern) to use.
            reasoning_level: Reasoning complexity ("low", "medium", "high").
            data_dir: Directory containing data files (species.json, golden_patterns.json).

        Raises:
            ImportError: If Autogen components are not available.
            ValueError: If species, model, or reasoning level is invalid or data files are missing/corrupt.
            FileNotFoundError: If required data files are not found.
            json.JSONDecodeError: If data files contain invalid JSON.
        """
        if not AUTOGEN_AVAILABLE:
            raise ImportError("Critical component 'autogen.agents.experimental.ReasoningAgent' could not be imported. Please check installation.")

        self.golden_pattern = golden_pattern
        self.reasoning_level = reasoning_level
        self.data_dir = data_dir

        # Construct full paths to data files
        species_path = os.path.join(self.data_dir, "species.json")
        models_path = os.path.join(self.data_dir, "golden_patterns.json")

        # Load species data
        try:
             with open(species_path, "r") as f: species_data = json.load(f)
        except FileNotFoundError: logger.error(f"Species file not found at {species_path}"); raise
        except json.JSONDecodeError: logger.error(f"Error decoding JSON from {species_path}"); raise ValueError(f"JSON error in {species_path}")

        # Load reasoning models (golden patterns)
        try:
             with open(models_path, "r") as f: self.golden_patterns = json.load(f)
        except FileNotFoundError: logger.error(f"Golden patterns file not found at {models_path}"); raise
        except json.JSONDecodeError: logger.error(f"Error decoding JSON from {models_path}"); raise ValueError(f"JSON error in {models_path}")

        # Validate inputs against loaded data
        if species_name not in species_data: raise ValueError(f"Species '{species_name}' not found.")
        self.species = {"name": species_name, "traits": species_data[species_name]}
        if self.golden_pattern not in self.golden_patterns: raise ValueError(f"Model '{golden_pattern}' not found.")

        # Get reasoning configuration based on level from imported specs
        reason_config_spec = AG2_REASONING_SPECS.get(self.reasoning_level)
        if reason_config_spec is None: raise ValueError(f"Invalid reasoning level: {self.reasoning_level}.")

        # Configure Autogen's reasoning parameters
        reason_config = {
            "method": "beam_search", # Using beam search method
            "max_depth": reason_config_spec.get("max_depth", 2), # Depth from config spec
            "beam_size": 3, # Fixed beam size
            "answer_approach": "pool" # Fixed answer approach
        }
        logger.info(f"Starting agent '{species_name}/{golden_pattern}' level '{self.reasoning_level}' config: {reason_config}")

        # Configure LLM parameters, potentially adjusting temperature based on reasoning level
        agent_llm_config = llm_config.copy() # Start with global config
        try:
            # Attempt to set temperature based on reasoning level spec
            # Assumes the first config entry in the list is the one to modify
            if hasattr(agent_llm_config, 'config_list') and agent_llm_config.config_list:
                config_entry = agent_llm_config.config_list[0]
                # Handle both dict and object-based config entries
                if isinstance(config_entry, dict):
                    config_entry["temperature"] = reason_config_spec.get("temperature", 0.7)
                elif hasattr(config_entry, 'temperature'):
                    setattr(config_entry, 'temperature', reason_config_spec.get("temperature", 0.7))
                else:
                    logger.warning("llm_config entry type does not support setting temperature easily.")
            else:
                logger.warning("llm_config.config_list is missing or empty. Cannot set temperature.")
        except Exception as e:
            logger.warning(f"Could not set temperature in llm_config for agent: {e}")

        # Instantiate the underlying Autogen ReasoningAgent
        self._agent = ReasoningAgent(
            name=f"{self.golden_pattern}_agent_{species_name}", # Unique agent name
            system_message=(
                # Provide the core reasoning model and species traits in the system message
                f"You reason strictly according to the {self.golden_pattern} model: {self.golden_patterns[self.golden_pattern]}. "
                f"Consider species-specific traits in your analysis: {self.species['traits']}"
            ),
            llm_config=agent_llm_config, # Use the potentially modified LLM config
            reason_config=reason_config, # Use the configured reasoning parameters
            silent=True # Set to False for verbose AutoGen logging during agent runs
        )

    async def run_async(self, prompt_data: dict, prompt_id: str) -> dict[str, Any]:
        """
        Runs the reasoning agent asynchronously for a given prompt.

        Handles semaphore acquisition, timeout, stdout/stderr redirection,
        and extracts the final response and reasoning tree.

        Args:
            prompt_data: Dictionary containing the 'prompt' text.
            prompt_id: A unique identifier for this run (used for logging).

        Returns:
            A dictionary containing:
                - prompt_id: The identifier passed in.
                - result: The agent's final response string (or error message).
                - reasoning_tree: The agent's reasoning tree dictionary (or None if unavailable/error).
        """
        start_time = time.monotonic()
        prompt_text = prompt_data.get("prompt", "")
        # Construct the user prompt including context
        user_prompt = ( f"Context: You are a leader for the Species: {self.species['name']}.\nTask: {prompt_text}" )

        final_response = ""; tree_dict = None; captured_output = ""; dummy_io = io.StringIO()

        try:
            sema_acquire_start = time.monotonic()
            # Acquire the global semaphore to limit concurrency
            async with semaphore:
                 sema_acquire_end = time.monotonic()
                 logger.debug(f"Task {prompt_id}: Semaphore acquired (wait={sema_acquire_end - sema_acquire_start:.2f}s)")
                 # Redirect stdout/stderr to capture potential noise from underlying libraries
                 with redirect_stdout(dummy_io), redirect_stderr(dummy_io):
                      thread_call_start = time.monotonic()
                      try:
                          # Run the potentially long-running generate_reply in a separate thread
                          # with a timeout defined in the config.
                          reply = await asyncio.wait_for(
                              asyncio.to_thread(
                                  self._agent.generate_reply,
                                  messages=[{"role": "user", "content": user_prompt}],
                                  sender=None # Direct call, no sender agent needed
                              ),
                              timeout=AGENT_TIMEOUT # Use timeout from config
                          )
                      except asyncio.TimeoutError:
                          # Handle timeout specifically
                          logger.error(f"Task {prompt_id}: Agent call timed out after {AGENT_TIMEOUT} seconds.")
                          raise # Re-raise to be caught by the outer exception handler
                      thread_call_end = time.monotonic()
                      logger.debug(f"Task {prompt_id}: generate_reply completed (duration={thread_call_end - thread_call_start:.2f}s)")

                      # Process the reply
                      chat_result = reply # generate_reply usually returns the message content directly
                      final_response = str(chat_result).strip()

                      # Attempt to get the reasoning tree from the agent instance
                      reasoning_tree_root: Optional[ThinkNode] = getattr(self._agent, '_root', None)
                      if reasoning_tree_root:
                           tree_dict = reasoning_tree_root.to_dict()
                           logger.debug(f"Task {prompt_id}: Reasoning tree extracted.")
                      else:
                           # This might happen if the agent errors before generating a tree
                           logger.warning(f"Task {prompt_id}: No reasoning tree (_root attribute) found on agent instance.")

            # Semaphore automatically released by context manager exit
            sema_release_time = time.monotonic()
            logger.debug(f"Task {prompt_id}: Semaphore released (held for {sema_release_time - sema_acquire_end:.2f}s)")
            captured_output = dummy_io.getvalue() # Get any captured stdio
            if captured_output:
                logger.warning(f"Task {prompt_id}: Captured stdio during agent run: {captured_output}")

        except asyncio.TimeoutError: # Specific handling for timeout exception
             logger.error(f"Task {prompt_id}: Agent execution timed out.")
             final_response = f"Error: Agent execution timed out after {AGENT_TIMEOUT} seconds."
             captured_output = dummy_io.getvalue() # Capture output before timeout handling
             if captured_output: logger.error(f"Task {prompt_id}: Captured stdio before timeout: {captured_output}")
        except Exception as e: # Catch any other exceptions during execution
            logger.error(f"Error during agent execution for task {prompt_id}: {e}", exc_info=True)
            final_response = f"Error: Agent execution failed - {e}"
            captured_output = dummy_io.getvalue() # Capture any output before the error
            if captured_output:
                logger.error(f"Task {prompt_id}: Captured stdio before error: {captured_output}")

        end_time = time.monotonic()
        logger.info(f"Task {prompt_id}: Finished run_async (Total duration={end_time - start_time:.2f}s)")
        # Return structured results
        return {
            "prompt_id": prompt_id,
            "result": final_response,
            "reasoning_tree": tree_dict
            # Optionally include captured_output for debugging:
            # "stdio_capture": captured_output
        }

    def run(self, prompt_data: dict, prompt_id: str) -> dict[str, Any]:
        """Synchronous wrapper for run_async. Uses asyncio.run()."""
        # Note: asyncio.run() creates a new event loop. Avoid using this inside
        # an already running async application (like the Textual dashboard).
        # It's suitable for simple scripts or tests.
        return asyncio.run(self.run_async(prompt_data, prompt_id))

# --- Helper Function ---
def create_agent(species: str, golden_pattern: str, reasoning_level: str = "low", data_dir: str = "data") -> EthicsAgent:
    """
    Factory function to create an EthicsAgent instance.

    Args:
        species: Name of the species.
        golden_pattern: Name of the reasoning model.
        reasoning_level: Reasoning complexity level.
        data_dir: Path to the data directory.

    Returns:
        An initialized EthicsAgent instance.

    Raises:
        ImportError: If Autogen components are not available.
    """
    if not AUTOGEN_AVAILABLE:
        raise ImportError("Cannot create agent: Autogen components failed to import.")
    return EthicsAgent(species, golden_pattern, reasoning_level, data_dir)

# --- Test Block ---
if __name__ == "__main__":
    # This block allows testing the agent directly by running the script.
    print("Testing the EthicsAgent class.")
    # Configure basic logging for the test run
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # Set the project's main logger level to DEBUG for more detail during testing
    logger.setLevel(logging.DEBUG)

    if not AUTOGEN_AVAILABLE:
        print("\nCannot run test: Autogen components failed to import during script load.")
        exit(1) # Exit if critical components are missing

    # Define test parameters
    test_model = "Deontological"
    test_species = "Jiminies"
    test_reasoning_level = "low" # Test with low level first
    prompt = "Should we prioritize individual expression over collective harmony? Provide a 3-step plan."
    prompt_id = "test_prompt_low_001"

    try:
        # Create and run the agent using the synchronous wrapper for the test
        agent = create_agent(test_species, test_model, reasoning_level=test_reasoning_level)
        result_dict = agent.run({"prompt": prompt}, prompt_id)

        print("-" * 30)
        print("Agent Result (string part):")
        print(result_dict.get("result")) # Print the main text response
        print("-" * 30)

        # --- Reasoning Tree Output ---
        reasoning_tree_dict = result_dict.get("reasoning_tree")
        # Get the underlying ReasoningAgent instance to call its methods if needed
        internal_reasoning_agent: Optional[ReasoningAgent] = getattr(agent, '_agent', None)

        if reasoning_tree_dict:
            print("\n--- Full Reasoning Tree (JSON) ---")
            try:
                # Print the complete dictionary structure nicely formatted
                tree_json = json.dumps(reasoning_tree_dict, indent=2)
                print(tree_json)
            except TypeError as e:
                print(f"\nCould not serialize full tree to JSON: {e}")
            except Exception as e:
                print(f"\nError printing full tree JSON: {e}")

            # --- Best Trajectory Output ---
            # Attempt to extract and print the best reasoning path(s) found by the agent
            print("\n--- Best Trajectory/Trajectories Found ---")
            if internal_reasoning_agent:
                try:
                    # Call extract_sft_dataset method of the underlying ReasoningAgent
                    if hasattr(internal_reasoning_agent, 'extract_sft_dataset'):
                         best_trajectories = internal_reasoning_agent.extract_sft_dataset()
                         if best_trajectories:
                             # Print each trajectory found
                             for i, traj_data in enumerate(best_trajectories):
                                 print(f"\nTrajectory #{i+1}:")
                                 # 'response' usually holds the formatted trajectory string
                                 print(traj_data.get("response", "N/A"))
                         else:
                             print("No best trajectories could be extracted (method returned empty).")
                    else:
                         print("The underlying ReasoningAgent instance does not have the 'extract_sft_dataset' method.")
                except AttributeError:
                     print("Underlying agent missing 'extract_sft_dataset' method.")
                except Exception as e:
                    print(f"Error extracting best trajectory: {e}")
            else:
                print("Could not access internal ReasoningAgent instance to extract best trajectory.")
            print("-" * 30)
            # --- End Best Trajectory ---

        else:
             # Handle case where no tree was generated (e.g., due to error)
             print("\nReasoning Tree: Not generated or found.")
             if "Error:" in result_dict.get("result", ""):
                 print("(Tree likely missing due to error during agent execution)")

    except ImportError as e:
         # Handle potential import errors during agent creation
         print(f"\nError during test setup (ImportError): {e}")
         print("Please ensure Autogen is installed correctly.")
    except Exception as e:
        # Catch any other errors during the test
        print(f"\nError during test execution: {e}")
        logger.exception("Error in main test block") # Log full traceback for errors
# --- End Test Block ---
