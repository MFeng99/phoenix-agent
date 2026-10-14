# AgentOS — Agent Governance Framework

A framework for running autonomous agents **under control**: every operation passes through a permission gate, a risk assessment, a scoring step, and a review step before its result is kept.

It ships with an installer that wires the framework together with a pluggable agent runtime, vector memory, browser automation, and a self-healing supervisor.

---

## Components

| Component | Port | Role |
|---|---|---|
| Framework API | 18888 | REST service exposing the governance pipeline |
| Orchestrator Web UI | 8648 | Chat / control interface *(runtime backend)* |
| Orchestrator Gateway | 9090 | API gateway *(runtime backend)* |
| Executor | 18789 | Agent execution engine *(runtime backend)* |
| Qdrant | 6333 | Vector memory |
| Chrome CDP | 9333 | Browser automation |
| Phoenix | — | Self-healing supervisor (PM2-managed) |

> The three entries marked *runtime backend* are provided by a pluggable runtime.
> The installer ships presets for a default stack; see `install.bat → Runtime backend packages`.

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│  Framework API  :18888  (FastAPI / uvicorn)      │
│                                                  │
│   layers/permission  ──►  layers/risk_assessment │
│            │                       │             │
│            └────►  layers/pipeline ◄┘            │
│                        │                         │
│            layers/scoring ─► layers/reviewer     │
│                        │                         │
│              layers/task_state (resumable)       │
└───────┬───────────────────────────┬──────────────┘
        │                           │
        ▼                           ▼
   Orchestrator                 Executor
  (LLM runtime)             (agent runtime CLI)
        │                           │
        └─────────────┬─────────────┘
                      ▼
     Qdrant :6333   Chrome CDP :9333   Phoenix (PM2)
```

### Pipeline

```
Agent Input → Permission → Risk Assessment → Scoring → Execution → Review → Store
```

Each stage lives in `framework/layers/` and is independently unit-tested.

---

## Prerequisites

- **Windows 10/11**
- **Python 3.8+** (with `pip`)
- **Node.js 18+** (with `npm`)
- **Git** (optional, for updates)
- An **agent runtime backend** exposing the documented CLI / HTTP contract
  (the installer can set up the default presets for you)

---

## Installation

### One-click install

```batch
cd agent-os
install.bat
```

The installer will:

1. Check prerequisites (Python, Node.js, Git, Chrome)
2. Create a Python virtual environment
3. Install Python dependencies from `requirements.txt`
4. Install the Node.js dependencies (`pm2` + runtime backend packages)
5. Configure environment variables (`.env`)
6. Generate `ecosystem.config.js` from the template
7. Initialize Qdrant with seed knowledge
8. Start all services via PM2
9. Verify the health of every endpoint

### Manual setup

```batch
# 1. Python venv + dependencies
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 2. Node.js
npm install -g pm2

# 3. Configure
copy .env.example .env
REM Edit .env with your settings

# 4. Start
cd framework
python run.py
```

---

## Quick start

```batch
install.bat                                  REM full install + start
pm2 status                                   REM list running services
pm2 logs framework-service                   REM tail framework logs
python framework\scripts\phoenix\phoenix.py --check-once   REM health check
```

---

## Configuration

Copy `.env.example` to `.env` and adjust:

```env
# Runtime backend
EXECUTOR_CLI=executor
EXECUTOR_GATEWAY_URL=http://127.0.0.1:18789

# Vector memory
QDRANT_URL=http://127.0.0.1:6333
EMBEDDING_MODEL=all-MiniLM-L6-v2

# Browser automation
CHROME_CDP_PORT=9333

# Service ports
SERVICE_QDRANT=6333
SERVICE_EXECUTOR=18789
SERVICE_ORCHESTRATOR_WEBUI=8648
SERVICE_CHROME_CDP=9333
```

All PM2-managed services and their placeholders are documented at the bottom of
`ecosystem.config.template.js`.

---

## Services reference

| Command | Description |
|---|---|
| `install.bat` | Full installation |
| `pm2 status` | List all running services |
| `pm2 logs` | View all logs |
| `pm2 stop all` | Stop everything |
| `pm2 restart framework-service` | Restart one service |
| `python framework\scripts\health_check.py` | Check every service port |
| `python framework\scripts\phoenix\phoenix.py` | Start the self-healing watcher |

---

## Extending

AgentOS is built around a layered pipeline:

```
Agent Input → Permission Check → Risk Assessment → Scoring → Execution → Response
```

- **New tool / operation** → declare it in `framework/config/permissions.example.json`
- **New risk rule** → add it to `framework/layers/risk_assessment.py`
- **New service** → add an entry to `ecosystem.config.template.js`

Tests live in `framework/tests/` and run with `pytest`.

---

## Phoenix (standalone)

If you only need the self-healing daemon without the full stack, use
[Phoenix](../phoenix/README.md) — zero dependencies, single directory.

---

## License

MIT — see [LICENSE](../LICENSE).
