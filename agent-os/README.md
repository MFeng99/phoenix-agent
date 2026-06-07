# AgentOS — AI Agent Operating System

A complete AI agent platform for **Windows**, combining:

- **Hermes Agent** — LLM-powered orchestrator with tool execution
- **OpenClaw** — Lightweight agent execution engine
- **Phoenix** — Self-healing daemon (PM2-managed)
- **Framework API** — REST API gateway for agents
- **Qdrant** — Vector memory for persistent agent knowledge
- **Chrome CDP** — Browser automation for web tasks

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  Hermes Agent                    │
│         (Planning, Risk Assessment, Dispatch)     │
└────────────────┬────────────────────────────────┘
                 │ API Gateway :9090
    ┌────────────┼────────────┬──────────────────┐
    ▼            ▼            ▼                  ▼
┌────────┐ ┌──────────┐ ┌─────────┐ ┌──────────────┐
│OpenClaw│ │Framework │ │ Phoenix │ │  Chrome CDP  │
│:18789  │ │:18888    │ │ (PM2)   │ │   :9333      │
└────────┘ └──────────┘ └─────────┘ └──────────────┘
                  │
                  ▼
            ┌──────────┐
            │  Qdrant  │
            │  :6333   │
            └──────────┘
```

### Components

| Component | Port | Role |
|-----------|------|------|
| Hermes Web UI | 8648 | Chat interface |
| Hermes Gateway | 9090 | API gateway |
| Framework API | 18888 | REST agent services |
| OpenClaw | 18789 | Agent execution engine |
| Qdrant | 6333 | Vector memory database |
| Chrome CDP | 9333 | Browser automation |
| Phoenix | — | Self-healing (PM2) |

---

## Prerequisites

- **Windows 10/11**
- **Python 3.8+** (with `pip`)
- **Node.js 18+** (with `npm`)
- **Git** (optional, for updates)

---

## Installation

### One-Click Install

```batch
cd agent-os
install.bat
```

The installer will:
1. ✅ Check prerequisites (Python, Node.js, Git)
2. ✅ Create Python virtual environment
3. ✅ Install Python dependencies (FastAPI, qdrant-client, etc.)
4. ✅ Install Node.js dependencies (PM2, OpenClaw, etc.)
5. ✅ Configure environment variables
6. ✅ Initialize Qdrant with seed knowledge
7. ✅ Start all services via PM2
8. ✅ Verify health of all endpoints

### Manual Setup

```batch
# 1. Python venv
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 2. Node.js
npm install -g pm2 openclaw hermes-web-ui

# 3. Configure
copy .env.example .env
REM Edit .env with your settings

# 4. Start
cd framework
python run.py          # Starts all services
```

---

## Quick Start

### Start Everything

```batch
install.bat
```

Or if already installed:

```batch
pm2 start ecosystem.config.js
```

### Check Health

```batch
python framework\scripts\phoenix\phoenix.py --check-once
```

### Monitor

```batch
pm2 status             # All processes
pm2 logs framework-api # Tail framework logs
```

---

## Configuration

Edit `.env` in the `agent-os/` directory:

```env
# API Keys
HERMES_API_KEY=change_me
OPENCLAW_API_KEY=change_me

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Chrome
CDP_PORT=9333
CDP_USER_DATA_DIR=C:\chrome-cdp-profile

# Application
LOG_LEVEL=INFO
```  

See `ecosystem.config.template.js` for all PM2-managed services.

---

## Services Reference

| Command | Description |
|---------|-------------|
| `install.bat` | Full installation |
| `pm2 status` | List all running services |
| `pm2 logs` | View all logs |
| `pm2 stop all` | Stop everything |
| `pm2 restart framework-api` | Restart one service |
| `python framework/scripts/phoenix/phoenix.py --check-once` | Health check |
| `python framework/scripts/phoenix/phoenix.py` | Phoenix watcher |  

---

## Extending

AgentOS uses a layered pipeline architecture:

```
Agent Input → Permission Check → Risk Assessment → Scoring → Execution → Response
```

Add new tools, permissions, or risk rules in `framework/layers/`.
Add new services in `framework/scripts/`.

---

## Phoenix (Standalone)

If you only need the self-healing daemon without the full system, use [Phoenix](../phoenix/README.md) — zero dependencies, single file.

---

## License

AGPL-3.0 — see [LICENSE](../LICENSE).
