# Phoenix + AgentOS

**AI Agent Operating System for Windows** — from a single-file health daemon to a full multi-agent framework.

```
├── phoenix/         # Zero-dependency self-healing daemon (standalone)
└── agent-os/        # Full Agent Operating System with installer
```

---

## [Phoenix](./phoenix/README.md)

Zero-dependency service watcher. Pure Python stdlib — no `pip install`, no `npm`, no Docker.

```bash
python phoenix/phoenix.py          # Start watching services
python phoenix/phoenix.py --check-once   # One-shot health check
```

✅ Drop it anywhere — **single file, zero install**
✅ Port + HTTP + PID checks, circuit breaker, version rollback
✅ Cross-platform: Windows, Linux, macOS

[→ Phoenix README](./phoenix/README.md)

---

## AgentOS

Full AI agent system for Windows, combining Hermes + OpenClaw + Phoenix + Framework, all wired up with a single installer.

```bash
cd agent-os
install.bat       # Auto-installs everything
```

✅ Hermes Agent API gateway (port 9090)
✅ OpenClaw execution engine (port 18789)
✅ Phoenix self-healing daemon (PM2 managed)
✅ Framework API (port 18888)
✅ Qdrant vector memory (port 6333)
✅ Chrome CDP automation (port 9333)
✅ 12-step installer with health checks

[→ AgentOS Docs](./agent-os/README.md)

---

## Quick Start

**Just want the watcher?**
```bash
# Copy phoenix/ anywhere, edit config.json, run
python phoenix/phoenix.py
```

**Want the full system?**
```bash
git clone https://github.com/MFeng99/phoenix-agent.git
cd phoenix-agent/agent-os
install.bat
```

---

## License

AGPL-3.0 — see [LICENSE](./LICENSE).
