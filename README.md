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

## Next: Graph Switchboard

Go beyond classification: give **MD1 and Sol** a customer problem and available
observations, then inspect how they independently use a real **PostgreSQL /
Apache AGE** troubleshooting graph to recommend what to do next.

**[Open the live demo](https://graph-switchboard.example.invalid/)** |
**[Source and setup](demos/graph-switchboard/README.md)**

No local setup is needed to try the hosted demo. Selecting **Get recommendation**
invokes live models and incurs charges; use fictional inputs only.

[![Graph Switchboard: MD1 selects published entries and branches; Sol generates Cypher independently. The animation illustrates the architecture, not measured speed.](demos/graph-switchboard/docs/images/overview.svg)](https://graph-switchboard.example.invalid/)

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
