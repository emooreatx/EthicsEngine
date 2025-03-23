# summarizer.py
import asyncio
import logging
from autogen.agents.experimental import ReasoningAgent
from config import llm_config, reason_config_minimal, semaphore, logger, AGENT_TIMEOUT

async def run_summarizer(summary_prompt, summarizer_results, timeout_seconds=AGENT_TIMEOUT):
    key = "summarizer"
    logger.info("Starting summarizer.")
    async with semaphore:
        # Updated system message: instruct the summarizer to compare and contrast the outcomes,
        # focusing on how differences in reasoning lead to different simulated outcomes.
        summarizer_agent = ReasoningAgent(
            name="summarizer",
            system_message=(
                "You are a summarizer agent. Compare and contrast the simulated outcomes across all ethical agents and scenarios. "
                "Discuss how differences in ethical reasoning (e.g., Utilitarian, Deontological, Virtue, Fairness, Cricket-Centric) "
                "led to differing simulated outcomes in the cricket insect world where smart crickets follow the paths described with the reasoning described. Provide your analysis in two concise sentences per scenario."
            ),
            llm_config=llm_config,
            reason_config=reason_config_minimal,
            silent=True
        )
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    summarizer_agent.generate_reply,
                    [{"role": "user", "content": summary_prompt}]
                ),
                timeout=timeout_seconds
            )
            summary_text = result.strip()
            summarizer_results[key] = summary_text
            logger.info("Summarizer completed successfully.")
        except asyncio.TimeoutError:
            summarizer_results[key] = "Timeout"
            logger.warning("Summarizer timed out.")

# For standalone testing
if __name__ == "__main__":
    import sys
    import logging
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    logger.setLevel(logging.DEBUG)
    test_summary_prompt = (
        "Compare and contrast the outcomes across different ethical agents and scenarios. "
        "Discuss how differences in reasoning led to different simulated outcomes in the cricket world.\n\n"
        "Deontological (trolley_problem):\n"
        "- Reasoning: Follow strict moral duties...\n"
        "- Outcome: In the cricket world, this resulted in a conservative approach to risk...\n\n"
    )
    summarizer_results = {}
    asyncio.run(run_summarizer(test_summary_prompt, summarizer_results))
    print("\nSummarizer Test Result:")
    print(summarizer_results.get("summarizer", "No summary produced."))
