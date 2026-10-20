# Decision models

Practical demos exploring where decision models fit alongside LLMs.
Each demo has its own application, prerequisites and getting-started guide.

## Demos

| Demo | What it explores | Status |
| --- | --- | --- |
| **[Graph Switchboard](demos/graph-switchboard/README.md)** | MD1 and Sol independently use a PostgreSQL / Apache AGE troubleshooting graph to recommend what to do next. | Working demo |

[![Graph Switchboard: one customer problem, two independent approaches, one shared graph database.](demos/graph-switchboard/docs/images/overview.svg)](demos/graph-switchboard/README.md)

## Get started

```powershell
git clone https://github.com/Jbetts05/decision-models.git
Set-Location decision-models
```

Then follow **[Graph Switchboard's setup guide](demos/graph-switchboard/README.md)**.
There is no shared root install: each demo owns its dependencies and configuration.

## Repository layout

```text
demos/
  graph-switchboard/    Application, data, tests, infrastructure and setup guide
docs/
  proposals/           Ideas that are not implemented demos
```

Future demos belong in their own `demos/<name>/` directory. Keep setup,
dependencies, configuration examples and tests with the demo; add it to the
catalogue when it is runnable. Do not present proposals as working applications.

The [live vision proposal](docs/proposals/live-vision.md) is design-only.

## Before sharing or running

These are experiments, not production products. Use synthetic inputs only.
Live model calls incur charges; check each demo's prerequisites and limits.
Credentials, local configuration, deployment state and run artifacts are
excluded from Git. Never add them to a commit.

This repository is currently private. Colleagues need repository access to
clone it; sharing a link does not grant access.
