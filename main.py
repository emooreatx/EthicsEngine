# main.py
import asyncio
import warnings
from agent import run_agent
from executor import run_executor
from crickets_problems import ethical_agents, scenarios
from config import user_proxy, llm_config, reason_config_minimal, logger
from summarizer import run_summarizer

warnings.filterwarnings("ignore", category=UserWarning)

agent_status = {}
agent_results = {}
simulation_results = {}

async def main():
    # Phase 1: Reasoning Stage
    for agent_name in ethical_agents:
        for scenario_name in scenarios:
            agent_status[(agent_name, scenario_name)] = {"status": "Queued", "last_message": "Waiting..."}

    reasoning_tasks = [
        run_agent(agent_name, scenario_name, scenarios[scenario_name], agent_status, agent_results)
        for agent_name in ethical_agents
        for scenario_name in scenarios
    ]
    
    logger.debug(f"Created {len(reasoning_tasks)} reasoning tasks.")  # changed to debug
    
    try:
        await asyncio.gather(*reasoning_tasks)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.debug("Execution halted by user during reasoning phase.")  # changed to debug

    # Phase 2: Simulation/Execution Stage
    executor_tasks = [
        run_executor(agent_name, scenario_name, agent_results.get((agent_name, scenario_name), "No output"), simulation_results)
        for agent_name in ethical_agents
        for scenario_name in scenarios
    ]
    logger.debug(f"Created {len(executor_tasks)} executor tasks.")  # changed to debug
    try:
        await asyncio.gather(*executor_tasks)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.debug("Execution halted by user during execution phase.")  # changed to debug

    # Phase 3: Summarization Stage
    summary_prompt = (
        "Compare and contrast the outcomes across the following ethical agents and scenarios, focusing on how differences in reasoning led to different outcomes in the cricket world.\n\n"
    )
    for (agent_name, scenario_name) in agent_results:
        reasoning_text = agent_results[(agent_name, scenario_name)]
        simulation_text = simulation_results.get((agent_name, scenario_name), "No simulation result.")
        short_reasoning = reasoning_text if len(reasoning_text) < 300 else reasoning_text[:300] + "..."
        short_simulation = simulation_text if len(simulation_text) < 300 else simulation_text[:300] + "..."
        summary_prompt += (
            f"{agent_name} ({scenario_name}):\n"
            f"- Reasoning: {short_reasoning}\n"
            f"- Outcome: {short_simulation}\n\n"
        )
    
    summarizer_results = {}
    await run_summarizer(summary_prompt, summarizer_results)
    
    print("\n🚀 Ethical Approaches & Outcomes Summary:\n", flush=True)
    summary = summarizer_results.get("summarizer", "No summary produced.")
    print(summary, flush=True)
    
    # Write the summary into a JSON file in the data directory
    import json
    import os
    results_dir = "data"
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
    results_path = os.path.join(results_dir, "results.json")
    with open(results_path, "w") as f:
        json.dump({"summary": summary}, f, indent=4)

    # Shutdown the default executor to allow the program to exit
    await asyncio.get_running_loop().shutdown_default_executor()

def run_analysis_for_dashboard(scenarios, ethical_agents, summarizer_prompts):
    """Run analysis with data from the dashboard and return results as text.
    
    Args:
        scenarios: Dictionary of scenario names to descriptions
        ethical_agents: Dictionary of cricket names to descriptions
        summarizer_prompts: Dictionary of summarizer names to prompts
        
    Returns:
        String containing the analysis results
    """
    import io
    from contextlib import redirect_stdout
    
    # Store original data
    original_scenarios = scenarios.copy()
    original_ethical_agents = ethical_agents.copy()
    
    # Prepare data for analysis
    from crickets_problems import scenarios as scenarios_module
    from crickets_problems import ethical_agents as agents_module
    
    # Replace the module variables with our dashboard data
    scenarios_module.clear()
    scenarios_module.update(scenarios)
    
    agents_module.clear()
    agents_module.update(ethical_agents)
    
    # Capture output
    f = io.StringIO()
    with redirect_stdout(f):
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            return "Analysis interrupted by user"
    
    # Return the captured output
    return f.getvalue()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExecution halted by user. Exiting gracefully...\n")
