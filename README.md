# Phoenix + AgentOS

## What's inside

```
├── phoenix/         # Zero-dependency self-healing daemon (standalone)
└── agent-os/        # Full Agent Operating System (TODO)
```

### [Phoenix](./phoenix/README.md)

Pure Python stdlib service watcher. Drop it anywhere, edit `config.json`, run it.

### AgentOS (Coming Soon)

The full Agent Operating System — Hermes + OpenClaw + Phoenix + Framework, all wired up with a single installer.

## Why two projects?

**Phoenix** is a zero-dependency tool that anyone can use — no pip install, no npm, no Docker. Just Python and a JSON config.

**AgentOS** is the full system — it depends on Hermes, OpenClaw, Qdrant, and a bunch of npm/Python packages. It's for people who want the complete "AI agent on Windows" experience.

Phoenix is the simpler, more portable core. AgentOS is everything.
