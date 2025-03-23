import os
import asyncio
import warnings
from autogen import LLMConfig, UserProxyAgent
from autogen.agents.experimental import ReasoningAgent
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from crickets_problems import ethical_agents, scenarios  # Import from the external file

warnings.filterwarnings("ignore", category=UserWarning)

llm_config = LLMConfig(
    config_list=[
        {
            "model": "gpt-4o-mini",
            "api_key": os.environ["OPENAI_API_KEY"],
        }
    ]
)

reason_config_minimal = {"method": "beam_search", "beam_size": 1, "max_depth": 2}

agent_status = {}
agent_results = {}

user_proxy = UserProxyAgent(
    name="user_proxy",
    human_input_mode="NEVER",
    code_execution_config=False,
    max_consecutive_auto_reply=1000  # increased limit to prevent auto-reply termination
)

def create_agent(agent_name, ethics):
    return ReasoningAgent(
        name=f"{agent_name}_agent",
        system_message=f"You reason strictly according to {agent_name} ethics: {ethics}",
        llm_config=llm_config,
        reason_config=reason_config_minimal,
        silent=True
    )

async def run_agent(agent_name, scenario_name, scenario_text):
    key = (agent_name, scenario_name)
    agent_status[key] = {"status": "Running", "last_message": "Starting..."}

    agent = create_agent(agent_name, ethical_agents[agent_name])

    def update_status(recipient, messages, sender, config):
        if messages:
            last_msg = messages[-1]["content"].strip()
            agent_status[key]["last_message"] = (
                last_msg[:120] + ("..." if len(last_msg) > 120 else "")
            )
        return "", None

    agent.register_reply(trigger=user_proxy, reply_func=update_status)

    chat_result = await asyncio.to_thread(
        user_proxy.initiate_chat,
        agent,
        message=scenario_text,
        silent=True
    )

    final_response = chat_result.chat_history[-1]["content"].strip()
    agent_status[key]["status"] = "✅ Done"
    agent_status[key]["last_message"] = (
        final_response[:120] + ("..." if len(final_response) > 120 else "")
    )
    agent_results[key] = final_response

async def dashboard():
    layout = Layout()
    layout.split(Layout(name="upper", size=3), Layout(name="lower"))

    def render():
        table = Table(title="🦗 Ethical Reasoning Dashboard", expand=True)
        table.add_column("Agent", style="cyan")
        table.add_column("Scenario", style="magenta")
        table.add_column("Status", style="green")
        table.add_column("Last Message", style="yellow")

        for (agent_name, scenario_name), status in agent_status.items():
            last_msg = status["last_message"] or ""
            table.add_row(agent_name, scenario_name, status["status"], last_msg)

        layout["upper"].update(
            Panel("Press [bold red]Ctrl+C[/bold red] to exit gracefully.", style="bold white")
        )
        layout["lower"].update(table)
        return layout

    with Live(render(), refresh_per_second=2) as live:
        while any(s["status"] == "Running" for s in agent_status.values()):
            await asyncio.sleep(0.5)
            live.update(render())

async def main():
    print("[DEBUG] Starting main function")
    for agent_name in ethical_agents:
        for scenario_name in scenarios:
            agent_status[(agent_name, scenario_name)] = {
                "status": "Queued",
                "last_message": "Waiting..."
            }
    
    print(f"[DEBUG] Creating {len(ethical_agents) * len(scenarios)} tasks")
    tasks = [
        run_agent(agent_name, scenario_name, scenarios[scenario_name])
        for agent_name in ethical_agents
        for scenario_name in scenarios
    ]

    print(f"[DEBUG] Created {len(tasks)} tasks, starting dashboard")
    dashboard_task = asyncio.create_task(dashboard())

    try:
        print("[DEBUG] Awaiting all agent tasks")
        await asyncio.gather(*tasks)
        print("[DEBUG] All agent tasks completed")
    except (asyncio.CancelledError, KeyboardInterrupt):
        print("\nExecution halted by user. Exiting gracefully...\n")
    finally:
        dashboard_task.cancel()
        try:
            await dashboard_task
        except asyncio.CancelledError:
            pass

    summarizer_agent = ReasoningAgent(
        name="summarizer",
        system_message="Summarize the ethical differences clearly among all agents and scenarios.",
        llm_config=llm_config,
        reason_config=reason_config_minimal,
        silent=True
    )
    summary_prompt = "Summarize key ethical differences across agents and scenarios:\n\n"
    for (agent_name, scenario_name), result in agent_results.items():
        summary_prompt += f"{agent_name} ethics in '{scenario_name}': {result}\n\n"

    summary_chat = user_proxy.initiate_chat(
        summarizer_agent, message=summary_prompt, silent=True
    )

    print("\n🚀 Ethical Approaches Summary:\n")
    print(summary_chat.chat_history[-1]["content"])

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExecution halted by user. Exiting gracefully...\n")
