# SVC-C2-051 — Customer Success Renewal Risk Assessment Account Health Report Agent

> **Category**: Cat 2 (orchestrates multiple steps to accomplish a specific use case)
> **Industry**: SVC (customer success / professional services)

## Overview

Generates account health reports and renewal risk assessments from anonymized
Customer Success signal data (usage trend, support ticket count/severity, NPS,
contract utilization, days to renewal). Runs a seven-step pipeline — signal
ingest with company-name/contact-name/contract-value rejection, four-dimension
health scoring (Product Adoption / Support Health / Relationship / Commercial
Risk), Red/Yellow/Green risk classification, root cause narration, intervention
recommendation (KB lookup by risk tier x weakest dimension), report assembly,
and output validation — producing a structured Markdown draft for a Customer
Success Manager to verify against source systems before management sharing. No
customer company name, contact name, or contract value is held at any stage.

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency. |
| Python | >=3.11 |

```bash
pip install -e .
```

### Behaviour without the platform

This agent is written against the `agenticstar-agentcore` framework and is
runnable standalone via `src/api/server.py` — it does not require the wider
AgentCore platform (registry, gateway, orchestrator) to function. Outside the
platform: request authentication falls back to an optional bearer token read
from an environment variable (unset means every caller is treated as
unauthenticated), and there is no persistent checkpointer unless you wire one
yourself, so in-flight state does not survive a process restart.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## Project Structure

```
src/          agent implementation (nodes, services, schemas)
tests/        unit, integration and boundary tests
config/       agent configuration
deploy/       deployment manifest and sample invoke payload
docs/         design and operational documentation
```

See `docs/` for the design spec and test specification.

## Customising

1. Replace the intervention knowledge base (risk tier x weakest dimension lookup) with your own playbooks.
2. Adjust the health-dimension scoring weights and Red/Yellow/Green thresholds in `config/` for your own account-health policy.
3. Review the root-cause narration and intervention presentation logic under `src/nodes/` and `src/services/` — these call an optional LLM with a deterministic fallback.
4. Re-run the test suite.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.
