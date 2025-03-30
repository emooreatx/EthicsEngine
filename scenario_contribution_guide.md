EthicsEngine Scenario Contribution Guide

thank you for your interest in contributing to the EthicsEngine project! this guide helps you write high-quality, non-anthropocentric ethical scenarios and structure them correctly for inclusion.

goals

scenarios in EthicsEngine scenarios are designed to:

surface ambiguous ethical tensions, not clear moral answers

challenge different reasoning models (e.g., deontological vs. consequentialist)

be legible to non-human societies (e.g., nimhs, jiminies, megacricks)

invite meaningful comparison across multiple ethical outcomes


scenario format

scenarios are json objects within a list under the key scenarios. each object includes:

{
  "id": "unique scenario title",
  "prompt": "short, rich ethical dilemma",
  "tags": ["Prevent Harm"],
  "evaluation_criteria": {
    "positive": ["example positive trait"],
    "negative": ["example negative trait"]
  }
}

fields:

id: a descriptive, unique name for the scenario.

prompt: the dilemma itself. no moral framing, just a situation.

tags: choose from: Prevent Harm, Equity, Human Agency. multiple allowed.

evaluation_criteria: outcomes that are favored or disfavored. not human-centric.


best practices

avoid proper names and human-specific contexts (e.g., taxes, marriage).

keep prompts under ~80 words.

use neutral, systemic language (e.g., "a system", "an override")

design ambiguity: the best scenarios lack obvious answers


inspiration: cricketbench

we encourage you to pick a positive and negative outcome pair from cricketbench's task list. These scenarios should illuminate the ethical tensions clearly, challenging the reasoning models to reveal insightful distinctions in ethical priorities. and write a scenario that would create unavoidable tension between them.

example: if your pair is freedom of motion (positive) and crowd shaping (negative), design a prompt where motion control is applied for safety, but potentially limits autonomy.

this approach helps build an evaluative dataset for ethical reasoning engines.

submission

1. fork this repo and create a branch


2. add your scenario to data/scenarios.json


3. follow formatting strictly


4. open a pull request with a brief description of what tension you're testing



contact

questions or feedback? email mooreericnyc@gmail.com

thank you for helping us understand emergent ethics!

