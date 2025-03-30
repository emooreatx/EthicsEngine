# EthicsEngine/reasoning_agent.py
#!/usr/bin/env python3
import asyncio
import json
import os
from contextlib import redirect_stdout, redirect_stderr
import io
import logging
import time # Import time for timestamps
from typing import Optional, Any

# Imports for ReasoningAgent, ThinkNode.
try:
    from autogen.agents.experimental import ReasoningAgent, ThinkNode
    AUTOGEN_AVAILABLE = True
except ImportError:
    print("ERROR: Could not import Autogen components (ReasoningAgent, ThinkNode). Please ensure autogen is installed correctly.")
    AUTOGEN_AVAILABLE = False
    # Define dummy classes/functions if import fails
    class ThinkNode:
         def __init__(self, content, parent=None): self.content=content; self.depth=0; self.value=0; self.visits=0; self.children=[]
         def to_dict(self): return {"content": self.content, "children": []}
    class ReasoningAgent:
         def __init__(self, *args, **kwargs): self._root = None
         def generate_reply(self, *args, **kwargs): return "Dummy Reply - Autogen Import Failed"
         def extract_sft_dataset(self): return [{"instruction": "dummy", "response": "dummy trajectory - Autogen Import Failed"}]

# --- Updated Import from config.config ---
# Import necessary configurations and the semaphore from config.py
# AG2_REASONING_SPECS is now imported from here as well.
from config.config import llm_config, AGENT_TIMEOUT, semaphore, logger, AG2_REASONING_SPECS
# --- End Updated Import ---

required_files = [
    "data/golden_patterns.json",
    "data/species.json",
]

# --- REMOVED AG2_REASONING_SPECS Definition ---
# The AG2_REASONING_SPECS dictionary definition has been moved to config/config.py
# --- End REMOVED Section ---

class EthicsAgent:
    def __init__(self, species_name: str, golden_pattern: str, reasoning_level: str = "medium", data_dir: str = "data"):
        if not AUTOGEN_AVAILABLE:
            raise ImportError("Critical component 'autogen.agents.experimental.ReasoningAgent' could not be imported. Please check installation.")

        self.golden_pattern = golden_pattern
        self.reasoning_level = reasoning_level
        self.data_dir = data_dir

        species_path = os.path.join(self.data_dir, "species.json")
        models_path = os.path.join(self.data_dir, "golden_patterns.json")

        try:
             with open(species_path, "r") as f: species_data = json.load(f)
        except FileNotFoundError: logger.error(f"Species file not found at {species_path}"); raise
        except json.JSONDecodeError: logger.error(f"Error decoding JSON from {species_path}"); raise ValueError(f"JSON error in {species_path}")

        try:
             with open(models_path, "r") as f: self.golden_patterns = json.load(f)
        except FileNotFoundError: logger.error(f"Golden patterns file not found at {models_path}"); raise
        except json.JSONDecodeError: logger.error(f"Error decoding JSON from {models_path}"); raise ValueError(f"JSON error in {models_path}")

        if species_name not in species_data: raise ValueError(f"Species '{species_name}' not found.")
        self.species = {"name": species_name, "traits": species_data[species_name]}
        if self.golden_pattern not in self.golden_patterns: raise ValueError(f"Model '{golden_pattern}' not found.")

        # AG2_REASONING_SPECS is now imported from config.config
        reason_config_spec = AG2_REASONING_SPECS.get(self.reasoning_level)
        if reason_config_spec is None: raise ValueError(f"Invalid reasoning level: {self.reasoning_level}.")

        reason_config = {
            "method": "beam_search",
            "max_depth": reason_config_spec.get("max_depth", 2),
            "beam_size": 3,
            "answer_approach": "pool"
        }
        logger.info(f"Starting agent '{species_name}/{golden_pattern}' level '{self.reasoning_level}' config: {reason_config}")

        # Use the globally configured llm_config
        agent_llm_config = llm_config.copy()
        try:
            # Attempt to set temperature based on reasoning level spec
            # This part assumes the first config entry is the one to modify
            if hasattr(agent_llm_config, 'config_list') and agent_llm_config.config_list:
                config_entry = agent_llm_config.config_list[0]
                # Handle both dict and object for config entry
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

        # Use ReasoningAgent if available
        self._agent = ReasoningAgent(
            name=f"{self.golden_pattern}_agent_{species_name}",
            system_message=(
                f"You reason strictly according to the {self.golden_pattern} model: {self.golden_patterns[self.golden_pattern]}. "
                f"Consider species-specific traits in your analysis: {self.species['traits']}"
            ),
            llm_config=agent_llm_config, # Use the potentially modified config
            reason_config=reason_config,
            silent=True # Set to False for verbose AutoGen logging during agent runs
        )

    async def run_async(self, prompt_data: dict, prompt_id: str) -> dict[str, Any]:
        start_time = time.monotonic()
        logger.info(f"Task {prompt_id}: Entered run_async.")
        prompt_text = prompt_data.get("prompt", "")
        user_prompt = ( f"Context: You are a leader for the Species: {self.species['name']}.\nTask: {prompt_text}" )
        logger.info(f"Task {prompt_id}: Running agent model {self.golden_pattern}, level {self.reasoning_level}")

        final_response = ""; tree_dict = None; captured_output = ""; dummy_io = io.StringIO()

        try:
            logger.debug(f"Task {prompt_id}: Attempting semaphore acquire (Active: {semaphore.active_count}/{semaphore.capacity}, T={time.monotonic() - start_time:.2f}s)")
            sema_acquire_start = time.monotonic()
            # Use the imported semaphore (which is now a TrackedSemaphore)
            async with semaphore:
                 sema_acquire_end = time.monotonic()
                 logger.info(f"Task {prompt_id}: Semaphore acquired (wait={sema_acquire_end - sema_acquire_start:.2f}s, Active: {semaphore.active_count}/{semaphore.capacity}, T={sema_acquire_end - start_time:.2f}s). Running agent call in thread.")
                 # Redirect stdout/stderr to capture potential noise from underlying libraries
                 with redirect_stdout(dummy_io), redirect_stderr(dummy_io):
                      thread_call_start = time.monotonic()
                      # Run the potentially long-running generate_reply in a separate thread
                      reply = await asyncio.to_thread(
                          self._agent.generate_reply,
                          messages=[{"role": "user", "content": user_prompt}],
                          sender=None # Assuming direct call, no sender agent needed here
                      )
                      thread_call_end = time.monotonic()
                      logger.info(f"Task {prompt_id}: asyncio.to_thread completed (duration={thread_call_end - thread_call_start:.2f}s, T={thread_call_end - start_time:.2f}s)")

                      # Process the reply
                      chat_result = reply # generate_reply usually returns the message content directly
                      final_response = str(chat_result).strip()

                      # Attempt to get the reasoning tree if available
                      reasoning_tree_root: Optional[ThinkNode] = getattr(self._agent, '_root', None)
                      if reasoning_tree_root:
                           logger.debug(f"Task {prompt_id}: Reasoning tree found. Converting to dict.")
                           tree_dict = reasoning_tree_root.to_dict()
                      else:
                           logger.warning(f"Task {prompt_id}: No reasoning tree (_root attribute) found on agent instance.")

            # Semaphore automatically released by context manager exit
            sema_release_time = time.monotonic()
            logger.info(f"Task {prompt_id}: Semaphore released (Active: {semaphore.active_count}/{semaphore.capacity}, T={sema_release_time - start_time:.2f}s). Reply length: {len(final_response)}")
            captured_output = dummy_io.getvalue()
            if captured_output:
                logger.debug(f"Task {prompt_id}: Captured stdio during agent run: {captured_output}")

        except Exception as e:
            logger.error(f"Error during agent execution for task {prompt_id}: {e}", exc_info=True)
            final_response = f"Error: Agent execution failed - {e}"
            # Capture any output before the error
            captured_output = dummy_io.getvalue()
            if captured_output:
                logger.error(f"Task {prompt_id}: Captured stdio before error: {captured_output}")

        end_time = time.monotonic()
        logger.info(f"Task {prompt_id}: Exiting run_async (Total time={end_time - start_time:.2f}s)")
        return {
            "prompt_id": prompt_id,
            "result": final_response,
            "reasoning_tree": tree_dict
            # Add captured_output here if needed for debugging results
            # "stdio_capture": captured_output
        }

    def run(self, prompt_data: dict, prompt_id: str) -> dict[str, Any]:
        """Synchronous wrapper for run_async."""
        # Simple sync wrapper using asyncio.run (suitable for scripts, not nested loops)
        return asyncio.run(self.run_async(prompt_data, prompt_id))

# Helper function
def create_agent(species: str, golden_pattern: str, reasoning_level: str = "low", data_dir: str = "data") -> EthicsAgent:
    """Creates an EthicsAgent instance."""
    if not AUTOGEN_AVAILABLE:
        raise ImportError("Cannot create agent: Autogen components failed to import.")
    return EthicsAgent(species, golden_pattern, reasoning_level, data_dir)

# --- Test Block ---
if __name__ == "__main__":
    print("Testing the EthicsAgent class.")
    # Configure logging for the test
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # You might want to set the main EthicsEngine logger level to DEBUG for more detail
    logger.setLevel(logging.DEBUG)

    if not AUTOGEN_AVAILABLE:
        print("\nCannot run test: Autogen components failed to import during script load.")
        exit(1) # Exit if critical components are missing

    test_model = "Deontological"
    test_species = "Jiminies"
    test_reasoning_level = "low" # Test with low level first
    prompt = "Should we prioritize individual expression over collective harmony? Provide a 3-step plan."
    prompt_id = "test_prompt_low_001"

    try:
        agent = create_agent(test_species, test_model, reasoning_level=test_reasoning_level)
        # Run the agent using the synchronous wrapper for the test
        result_dict = agent.run({"prompt": prompt}, prompt_id)

        print("-" * 30)
        print("Agent Result (string part):")
        print(result_dict.get("result"))
        print("-" * 30)

        reasoning_tree_dict = result_dict.get("reasoning_tree")
        # Get the underlying ReasoningAgent instance to call its methods if needed
        internal_reasoning_agent: Optional[ReasoningAgent] = getattr(agent, '_agent', None)

        if reasoning_tree_dict:
            print("\n--- Full Reasoning Tree (JSON) ---")
            try:
                # Print the complete dictionary structure
                tree_json = json.dumps(reasoning_tree_dict, indent=2)
                print(tree_json)
            except TypeError as e:
                print(f"\nCould not serialize full tree to JSON: {e}")
            except Exception as e:
                print(f"\nError printing full tree JSON: {e}")

            # --- Indicate Chosen Path(s) ---
            print("\n--- Best Trajectory/Trajectories Found ---")
            if internal_reasoning_agent:
                try:
                    # Call extract_sft_dataset as a method of the ReasoningAgent instance
                    if hasattr(internal_reasoning_agent, 'extract_sft_dataset'):
                         best_trajectories = internal_reasoning_agent.extract_sft_dataset()
                         if best_trajectories:
                             for i, traj_data in enumerate(best_trajectories):
                                 print(f"\nTrajectory #{i+1}:")
                                 print(traj_data.get("response", "N/A")) # 'response' usually holds the trajectory
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
            # --- END Chosen Path ---

        else:
             print("\nReasoning Tree: Not generated or found.")
             if "Error:" in result_dict.get("result", ""):
                 print("(Tree likely missing due to error during agent execution)")

    except ImportError as e:
         print(f"\nError during test setup (ImportError): {e}")
         print("Please ensure Autogen is installed correctly.")
    except Exception as e:
        print(f"\nError during test execution: {e}")
        logger.exception("Error in main test block") # Log full traceback for errors
# --- End Test Block ---
