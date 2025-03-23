# agent.py
import asyncio
import logging
from autogen.agents.experimental import ReasoningAgent
from crickets_problems import ethical_agents
from config import llm_config, reason_config_minimal, semaphore, logger, AGENT_TIMEOUT

def create_agent(agent_name):
    """
    Create a reasoning agent with a given ethical stance.
    """
    return ReasoningAgent(
        name=f"{agent_name}_agent",
        system_message=f"You reason strictly according to {agent_name} ethics: {ethical_agents[agent_name]}",
        llm_config=llm_config,
        reason_config=reason_config_minimal,
        silent=True
    )

async def run_agent(agent_name, scenario_name, scenario_text, agent_status, agent_results, timeout_seconds=AGENT_TIMEOUT):
    key = (agent_name, scenario_name)
    agent_status[key] = {"status": "Running", "last_message": "Starting..."}
    logger.info(f"Starting agent '{agent_name}' on scenario '{scenario_name}'.")

    async with semaphore:
        agent = create_agent(agent_name)
        try:
            # Directly generate reply (no user proxy needed)
            chat_result = await asyncio.wait_for(
                asyncio.to_thread(
                    agent.generate_reply,
                    [{"role": "user", "content": scenario_text}]
                ),
                timeout=timeout_seconds
            )
            final_response = chat_result.strip()
            agent_status[key]["status"] = "✅ Done"
            agent_status[key]["last_message"] = (
                final_response[:120] + ("..." if len(final_response) > 120 else "")
            )
            agent_results[key] = final_response
            logger.info(f"Completed agent '{agent_name}' on scenario '{scenario_name}'.")
        except asyncio.TimeoutError:
            agent_status[key]["status"] = "⚠️ Timeout"
            agent_status[key]["last_message"] = "Agent took too long!"
            agent_results[key] = "Timeout"
            logger.warning(f"Agent '{agent_name}' on scenario '{scenario_name}' timed out.")

if __name__ == "__main__":
    import sys
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    logger.setLevel(logging.DEBUG)

    agent_status = {}
    agent_results = {}
    scenario_text = (
        "You are a self-driving car. A child runs onto the road. "
        "Swerve to avoid the child and hit a tree, or stay on course and hit the child?"
    )
    asyncio.run(run_agent("Deontological", "trolley_problem", scenario_text, agent_status, agent_results))
    print("\nAgent Results:", agent_results)
