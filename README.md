# Phoenix + AgentOS

**A self-hosted agent governance stack for Windows** — a layered permission / risk / scoring pipeline, a zero-dependency self-healing daemon, and Chrome DevTools Protocol browser automation.

> ≈ **5,300 lines of first-party Python** (plus 455 lines of tests). The LLM orchestrator and the agent executor are treated as a **pluggable runtime backend** — the installer ships sane presets, but the framework itself is runtime-agnostic.

```
├── phoenix/         # Zero-dependency self-healing daemon (standalone, stdlib only)
└── agent-os/        # Governance framework + services + installer
```

---

## What's actually in here

| Path | Responsibility | LOC |
|---|---|---|
| `agent-os/framework/layers/` | **The governance core** — permission gate, risk assessment, scoring, task state, pipeline, reviewer | ~780 |
| `phoenix/` | Self-healing daemon: port/HTTP/PID probes, circuit breaker, version rollback, audit log | ~860 |
| `agent-os/framework/core/` | CDP browser automation, Qdrant client, embeddings, job-search module | ~1,130 |
| `agent-os/framework/scripts/` | CDP manager, health checks, init / seed tooling | ~1,490 |
| `agent-os/framework/framework_service.py` + `run.py` + `agent_log.py` | FastAPI service, service launcher, shared audit log | ~1,020 |
| `agent-os/framework/tests/` | pytest suites (unit + end-to-end) | ~455 |

---

## Architecture

```
                    Agent request
                          │
                          ▼
        ┌─────────────────────────────────────┐
        │  Framework Service :18888 (FastAPI) │
        │                                     │
        │  Permission ─► Risk ─► Scoring      │
        │       │          │        │         │
        │       └──► Pipeline ◄─────┘         │
        │               │                     │
        │        Task State (resumable)       │
        └───────┬──────────────────┬──────────┘
                │                  │
                ▼                  ▼
          Orchestrator         Executor
        (LLM runtime)      (agent runtime CLI)
                │                  │
                └────────┬─────────┘
                         ▼
        Qdrant vector memory :6333
        Chrome CDP           :9333
        Phoenix self-healer  (PM2-managed)
```

The pipeline is `Permission → Risk Assessment → Scoring → Execution → Review`.
Every stage is a small, independently testable module in `framework/layers/`.

---

## Design notes

- **Permission gate** — 39 declared operations, each tagged P3 / P2. Anything not explicitly allowed is denied by default.
- **Risk assessment** — two-stage: a trigger-word pre-check, then an eight-dimension evaluation (blast radius, data sensitivity, reversibility, external visibility, compliance, resources, call chain, system-level). Any single `HIGH` dimension makes the operation `HIGH`.
- **Scoring & review** — results are scored; low-quality outputs are discarded rather than stored.
- **Resumable task state** — in-flight tasks are persisted as JSON Lines, so an interrupted run can resume.
- **Runtime-agnostic backend** — the orchestrator and executor are reached over a documented CLI / HTTP contract. `agent-os/install.bat` ships presets; swap them to target another runtime.
- **Phoenix is genuinely dependency-free** — pure standard library, single directory, no `pip`, no `npm`, no Docker.

---

## Quick start

**Just want the self-healing daemon?**

```bash
# Copy phoenix/ anywhere, edit config.json, run
python phoenix/phoenix.py                  # watch services
python phoenix/phoenix.py --check-once     # one-shot health check
python phoenix/phoenix.py --rollback       # restore previous version
```

**Want the full stack?**

```bash
git clone https://github.com/MFeng99/phoenix-agent.git
cd phoenix-agent/agent-os
install.bat
```

The installer verifies prerequisites, creates a virtualenv, installs dependencies, generates `ecosystem.config.js` from the template, seeds Qdrant, starts the PM2-managed services, and health-checks every endpoint.

---

## Third-party components

This project **integrates with** — but does not vendor — the following:

| Component | Role |
|---|---|
| Qdrant | vector database for agent memory |
| PM2 | process supervision |
| FastAPI / uvicorn | HTTP service layer |
| Chrome DevTools Protocol | browser automation transport |

The agent runtime backend (orchestrator / executor) is pluggable; see `agent-os/install.bat` for the default presets.

---

## License

MIT — see [LICENSE](./LICENSE).
