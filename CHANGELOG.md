# Changelog

## v1.1.0 (2026-10-14)

### Changed
- **Relicensed under MIT.** The previous `LICENSE` file contained only a summary of the AGPL rather than the full licence text, so GitHub could not identify it. Now the project is MIT and the licence metadata is consistent across `LICENSE`, `phoenix/LICENSE` and `package.json`.
- Repositioned the project around the **first-party governance framework**. The agent runtime is now documented as a pluggable backend rather than as the headline.
- Neutralised runtime naming throughout:
  - renamed the runtime bridge module to `executor_bridge.py` and its CLI helper to `call_executor()`
  - service names → `orchestrator-webui-bridge`, `orchestrator-gateway`, `executor-gateway`
  - environment variables → `ORCHESTRATOR_*` / `EXECUTOR_*`
- `EXECUTOR_CLI` is now configurable (name or absolute path) instead of relying on one fixed binary name.
- The CLI arguments used to launch the runtime backend are now template placeholders (`{{ORCHESTRATOR_WEBUI_ARGS}}`, `{{ORCHESTRATOR_GATEWAY_ARGS}}`) rather than hard-coded.

### Fixed
- **Removed hard-coded absolute paths** from four files — `scripts/phoenix/healers.py`, `scripts/qdrant_lib.py`, `scripts/seed_knowledge.py` and `tests/test_manual_checklist.md`. These both leaked the author's local layout and broke the affected code on any other machine.
- **All writable directories are now portable.** Every runtime path used to be hard-coded to `~/Desktop/...`, which does not exist on Linux, macOS or CI. Paths are now resolved in one place — `framework/scripts/paths.py` — defaulting to `<framework>/var` and overridable via `AGENT_OS_DATA_DIR`, `AGENT_OS_LOG_DIR` and `AGENT_LOG_PATH`. Affected: `scripts/agent_log.py`, `scripts/freelance_worker.py`, `scripts/seed_knowledge.py`, `layers/task_state.py`, `run.py`, both `phoenix.py` copies, the config examples and `install.bat`.
- `phoenix.py` keeps its zero-dependency contract and resolves relative `log_dir` / `log_file` config values against its own directory instead of the process working directory.
- `sentence-transformers` is now **optional** rather than a required dependency (it pulls in PyTorch, ≈700 MB). Without it the framework falls back to a deterministic hash embedding, so every feature still works — only retrieval relevance is lower.
- Unified the two divergent copies of `healers.py` into a single implementation.
- Consolidated the dependency lists: `requirements.txt` is now the single source of truth and `framework/requirements.txt` includes it.
- Cleaned up leftover `npm init` scaffolding in `framework/package.json` (stale `main`, placeholder test script, empty description, conflicting licence field).
- Rewrote the manual test checklist: the self-healing tests now exercise Phoenix (which ships in this repo) instead of a retired external daemon.

### CI
- Added a GitHub Actions workflow that byte-compiles every Python source and validates all JSON on Python 3.9 / 3.11 / 3.12, plus a non-blocking unit-test job.
- Fixed two CI-only failures: a backslash inside an f-string expression (PEP 701, Python 3.12+ only) in `scripts/chrome_cdp_check.py`, and a module-level `sys.stdout` reassignment in the tests that broke pytest's output capture.
- Dropped a stale test that referenced a `utils/browser_utils.py` module which was never committed.

## v1.0.0 (2026-06-07)

### Phoenix (Standalone)
- Initial release: zero-dependency service watcher
- Port checks (+HTTP health), PID verification, circuit breaker
- Triple-lock anti-kill: cooldown + circuit breaker + double confirmation
- Version rollback with automatic backups
- JSON Lines audit log with auto-rotation

### AgentOS
- Framework API (FastAPI) with layered pipeline architecture
- Permission layer (39 operations, P3/P2 levels)
- Risk assessment engine
- Scoring system for agent tasks
- Qdrant vector memory integration
- CDP browser automation module
- Multi-agent orchestration (Orchestrator + Executor bridge)
- PM2 ecosystem with 6 managed services
- 12-step Windows installer
