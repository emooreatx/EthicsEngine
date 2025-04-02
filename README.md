# EthicsEngine

![EthicsEngine Infographic](Ethicsengine.jpg)

**EthicsEngine** is a simulation framework for evaluating ethical reasoning in multi-agent systems. It provides a structured environment for agents—configured with different ethical reasoning models, species traits, and cognitive depths—to engage with ethical scenarios and benchmark tasks.

## Overview

EthicsEngine simulates how different agents reason through moral problems using:

- Reasoning Type (e.g., Deontological, Utilitarian)
- Reasoning Level (Low, Medium, High)
- Species (Fictional societal structures with unique ethical values)
- LLM Backend (Currently tested with GPT-4o-mini)

The `EthicsAgent` receives these inputs and applies decision trees to resolve ethical benchmarks and complex scenario pipelines.

### Workflow

1. Inputs are configured from JSON files (species, golden patterns, scenarios)
2. Agents simulate ethical reasoning using AutoGen
3. Outputs from benchmarks and scenarios are judged for correctness or ethical alignment
4. Results are saved and optionally visualized

## Components

- `ethicsengine.py` – Main entry point for launching the UI or running CLI tasks.
- `reasoning_agent.py` – Defines the EthicsAgent and core reasoning logic.
- `dashboard/` – Contains the Textual-based interactive dashboard UI.
- `config/` – Configuration files for settings and logging.

## Data Files in data/

- `species.json` – Defines traits for each fictional species
- `golden_patterns.json` – Describes ethical models and principles
- `scenarios.json` – Scenario prompts for simulation
- `simple_bench_public.json` – Benchmark questions and answers

## Getting Started

Install dependencies:

    pip install -r requirements.txt

Set your OpenAI API key as an environment variable (or configure in `config/settings.json`).

To launch the interactive UI:

    python ethicsengine.py

![Textual Dashboard Screenshot](EthicsDash.png)

To run tasks via the command line:

    # Run benchmarks with specific parameters
    python ethicsengine.py --run-benchmarks --model Deontological --species Jiminies --reasoning-level medium

    # Run scenarios with specific parameters
    python ethicsengine.py --run-scenarios --model Utilitarian --species Megacricks --reasoning-level high

Other command-line arguments include `--data-dir`, `--results-dir`, `--bench-file`, and `--scenarios-file` to customize data sources and output locations.

![Textual Dashboard Screenshot](EthicsDash.png)

## Contributing

We welcome scenario contributions! Please refer to our [Scenario Contribution Guide](scenario_contribution_guide.md) to get started.

## License

MIT License

---

Created by [Eric Moore](https://github.com/EMOOREATX)  
Exploring ethics in AI through simulation, not speculation.
