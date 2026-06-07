# Changelog

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
- Multi-agent orchestration (Hermes + OpenClaw bridge)
- PM2 ecosystem with 6 managed services
- 12-step Windows installer
