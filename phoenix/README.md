# Phoenix — Zero-Dependency Self-Healing Daemon for Windows/Linux/macOS

**Phoenix** watches your services and auto-restarts them when they die. Pure Python stdlib — no pip install, no npm, no Docker.

```bash
python phoenix.py          # Start the watcher
python phoenix.py --check-once   # One-shot health check
python phoenix.py --rollback     # Rollback to previous version
python phoenix.py --versions     # List all backed-up versions
```

## Features

- **Multiple check modes** — port check, HTTP health check, PID verification, custom scripts
- **Triple lock anti-kill** — cooldown period + circuit breaker + double confirmation
- **Version rollback** — automatic backups, `--rollback` to restore
- **Audit log** — JSON Lines, auto-rotation at 2MB
- **Zero external dependencies** — Python 3.8+ stdlib only
- **Cross-platform** — Windows (default), Linux, macOS

## Quick Start

1. Download the `phoenix/` directory
2. Copy `config.example.json` to `config.json`
3. Edit `config.json` — set your services
4. Run `python phoenix.py`

## Config Example

```json
{
  "check_interval": 30,
  "deep_check_interval": 300,
  "cooldown_seconds": 300,
  "max_failures": 2,
  "services": {
    "my-app": {
      "type": "port_http",
      "port": 3000
    },
    "my-db": {
      "type": "port_only",
      "port": 5432
    }
  }
}
```

## Why Phoenix?

There are plenty of process managers (PM2, systemd, supervisord). But they all need installation. Phoenix is a **single Python file** you can drop anywhere — no setup, no config, no lock-in.
