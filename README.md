# Decision models

Practical demos exploring where decision models fit alongside LLMs.
Each demo has its own application, prerequisites and getting-started guide.

## Start here: AI Switchboard

The simplest demo: choose an editable classification example and compare
**MD1, Astra, Sol and Luna** side by side. Eight fictional cases cover ticket
routing, complaint classification and agent selection.

**[Open the live demo](https://ai-switchboard.example.invalid)** |
**[Source and setup](demos/ai-switchboard/README.md)**

No installation or sign-in is needed to try the hosted demo. Selecting
**Run comparison** makes four billable model requests; use fictional inputs only.

[![AI Switchboard: one case, four models, side by side. The animation is illustrative, not a benchmark.](demos/ai-switchboard/docs/switchboard.svg)](https://ai-switchboard.example.invalid)

## Demos

| Demo | What it explores | Status |
| --- | --- | --- |
| **[AI Switchboard](demos/ai-switchboard/README.md)** | Start here: compare MD1 with three LLMs on predefined classification tasks, with answers, latency and tokens. | Working demo |
| **[Graph Switchboard](demos/graph-switchboard/README.md)** | MD1 and Sol independently use a PostgreSQL / Apache AGE troubleshooting graph to recommend what to do next. | Working demo |

## Get the source

```powershell
git clone https://github.com/Jbetts05/decision-models.git
Set-Location decision-models
```

Start with **[AI Switchboard](demos/ai-switchboard/README.md)**, then explore
**[Graph Switchboard](demos/graph-switchboard/README.md)** for graph traversal.
There is no shared root install: each demo owns its dependencies and configuration.

## Repository layout

```text
demos/
  ai-switchboard/       Basic classification comparison: start here
  graph-switchboard/    Application, data, tests, infrastructure and setup guide
docs/
  proposals/           Ideas that are not implemented demos
```

Future demos belong in their own `demos/<name>/` directory. Keep setup,
dependencies, configuration examples and tests with the demo; add it to the
catalogue when it is runnable. Do not present proposals as working applications.

The [live vision proposal](docs/proposals/live-vision.md) is design-only.

## Before sharing or running

AI Switchboard was imported from
[its original public repository](https://github.com/Jbetts05/decision-model-demo),
which remains intact and continues to host the existing deployment workflow.
The copy here is maintained independently; it does not replace that repository.

These are experiments, not production products. Use synthetic inputs only.
Live model calls incur charges; check each demo's prerequisites and limits.
Credentials, local configuration, deployment state and run artifacts are
excluded from Git. Never add them to a commit.

This repository is currently private. Colleagues need repository access to
clone it; sharing a link does not grant access.
