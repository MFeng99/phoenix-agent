/**
 * ═══════════════════════════════════════════════════════════════
 * Agent OS — PM2 Ecosystem Config Template
 * ═══════════════════════════════════════════════════════════════
 *
 *  📋 HOW TO USE:
 *    1. Copy this file to ecosystem.config.js
 *    2. Replace ALL {{VARS}} with your actual paths/values
 *    3. Run: pm2 start ecosystem.config.js
 *
 *  🛠  AUTOMATED SETUP:
 *    Run install.bat — it will replace {{VARS}} automatically
 *    using values from your system environment.
 *
 * ═══════════════════════════════════════════════════════════════
 */

module.exports = {
  apps: [
    // ────────────────────────────────────────────────────────────
    // 1. Hermes WebUI Bridge
    // ────────────────────────────────────────────────────────────
    // Serves the Hermes Web UI (port 8648). Runs a Python script
    // from the Hermes virtual environment that bridges the web
    // interface to the Hermes backend.
    {
      name: 'hermes-webui-bridge',
      script: '{{HERMES_VENV_PYTHON}}',
      args: '-m hermes.webui_bridge',
      cwd: '{{HERMES_DIR}}',
      interpreter: '',
      env: {
        PYTHONUNBUFFERED: '1',
        HERMES_HOME: '{{HERMES_HOME}}',
        HOST: '0.0.0.0',
        PORT: '{{HERMES_WEBUI_PORT:8648}}',
      },
      watch: false,
      max_restarts: 5,
      restart_delay: 3000,
      error_file: '{{LOG_DIR}}/hermes-webui-bridge-error.log',
      out_file: '{{LOG_DIR}}/hermes-webui-bridge-out.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },

    // ────────────────────────────────────────────────────────────
    // 2. Hermes Gateway
    // ────────────────────────────────────────────────────────────
    // The Hermes API gateway. Uses the `hermes gateway run` CLI
    // command (provided by the Hermes Python package installed
    // in the venv). Handles routing and authentication.
    {
      name: 'hermes-gateway',
      script: '{{HERMES_VENV_PYTHON}}',
      args: '-m hermes.gateway run',
      cwd: '{{HERMES_DIR}}',
      interpreter: '',
      env: {
        PYTHONUNBUFFERED: '1',
        HERMES_HOME: '{{HERMES_HOME}}',
        HERMES_GATEWAY_PORT: '{{HERMES_GATEWAY_PORT:9090}}',
        HERMES_GATEWAY_HOST: '0.0.0.0',
        HERMES_API_KEY: '{{HERMES_API_KEY}}',
      },
      watch: false,
      max_restarts: 5,
      restart_delay: 5000,
      error_file: '{{LOG_DIR}}/hermes-gateway-error.log',
      out_file: '{{LOG_DIR}}/hermes-gateway-out.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },

    // ────────────────────────────────────────────────────────────
    // 3. Framework Service
    // ────────────────────────────────────────────────────────────
    // FastAPI-based framework service (port 18888). Runs
    // framework_service.py via uvicorn. Provides the core
    // pipeline execution, knowledge management (Qdrant),
    // browser automation (CDP), and task orchestration APIs.
    {
      name: 'framework-service',
      script: '{{FRAMEWORK_VENV_PYTHON}}',
      args: '-m uvicorn framework_service:app --host 0.0.0.0 --port {{FRAMEWORK_PORT:18888}} --log-level info',
      cwd: '{{FRAMEWORK_DIR}}',
      interpreter: '',
      env: {
        PYTHONUNBUFFERED: '1',
        FRAMEWORK_API_KEY: '{{FRAMEWORK_API_KEY}}',
        FRAMEWORK_AGENT_DIR: '{{FRAMEWORK_AGENT_DIR}}',
        FRAMEWORK_CDP_DIR: '{{FRAMEWORK_CDP_DIR}}',
        QDRANT_HOST: '127.0.0.1',
        QDRANT_PORT: '{{QDRANT_PORT:6333}}',
        CDP_PORT: '{{CDP_PORT:9333}}',
      },
      watch: false,
      max_restarts: 5,
      restart_delay: 5000,
      error_file: '{{LOG_DIR}}/framework-service-error.log',
      out_file: '{{LOG_DIR}}/framework-service-out.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },

    // ────────────────────────────────────────────────────────────
    // 4. OpenClaw Gateway
    // ────────────────────────────────────────────────────────────
    // OpenClaw agent gateway (port 18789). A Node.js service
    // from the `openclaw` npm package. Provides agent-based
    // task execution capabilities to the framework.
    {
      name: 'openclaw-gateway',
      script: '{{OPENCLAW_BIN}}',
      args: 'gateway --port {{OPENCLAW_PORT:18789}} --host 0.0.0.0',
      cwd: '{{OPENCLAW_DIR}}',
      interpreter: '',
      env: {
        NODE_ENV: 'production',
        OPENCLAW_CONFIG_DIR: '{{OPENCLAW_CONFIG_DIR}}',
        OPENCLAW_API_KEY: '{{OPENCLAW_API_KEY}}',
        LOG_LEVEL: 'info',
      },
      watch: false,
      max_restarts: 5,
      restart_delay: 5000,
      error_file: '{{LOG_DIR}}/openclaw-gateway-error.log',
      out_file: '{{LOG_DIR}}/openclaw-gateway-out.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },

    // ────────────────────────────────────────────────────────────
    // 5. Chrome CDP (Headless Browser)
    // ────────────────────────────────────────────────────────────
    // Headless Google Chrome instance exposing the Chrome DevTools
    // Protocol (CDP) on port 9333. Used by the framework for
    // browser automation tasks (web scraping, form filling, etc.).
    // NOTE: The --remote-debugging-port must match {{CDP_PORT}}.
    {
      name: 'chrome-cdp',
      script: '{{CHROME_PATH}}',
      args: [
        '--headless',
        '--disable-gpu',
        '--no-sandbox',
        '--disable-dev-shm-usage',
        '--disable-software-rasterizer',
        '--remote-debugging-port={{CDP_PORT:9333}}',
        '--remote-debugging-address=127.0.0.1',
        '--window-size=1920,1080',
        '--user-data-dir={{CHROME_USER_DATA_DIR}}',
        '--disable-blink-features=AutomationControlled',
        '--disable-features=IsolateOrigins,site-per-process',
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
      ],
      interpreter: 'none',  // Chrome is a binary, not a node script
      watch: false,
      max_restarts: 3,
      restart_delay: 10000,
      kill_timeout: 10000,
      error_file: '{{LOG_DIR}}/chrome-cdp-error.log',
      out_file: '{{LOG_DIR}}/chrome-cdp-out.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },

    // ────────────────────────────────────────────────────────────
    // 6. Qdrant Vector Database
    // ────────────────────────────────────────────────────────────
    // Qdrant standalone executable — vector similarity search
    // engine (port 6333 for gRPC, 6334 for HTTP). Stores and
    // retrieves embeddings for the knowledge base / semantic
    // memory system used by the framework.
    {
      name: 'qdrant',
      script: '{{QDRANT_PATH}}',
      args: [
        '--uri', 'http://127.0.0.1:{{QDRANT_HTTP_PORT:6333}}',
        '--grpc-port', '{{QDRANT_GRPC_PORT:6334}}',
        '--storage', '{{QDRANT_STORAGE_DIR}}',
      ],
      interpreter: 'none',  // Qdrant is a native binary
      watch: false,
      max_restarts: 3,
      restart_delay: 10000,
      kill_timeout: 15000,
      env: {
        RUST_LOG: 'info',
        QDRANT__SERVICE__GRPC_PORT: '{{QDRANT_GRPC_PORT:6334}}',
        QDRANT__STORAGE__STORAGE_PATH: '{{QDRANT_STORAGE_DIR}}',
      },
      error_file: '{{LOG_DIR}}/qdrant-error.log',
      out_file: '{{LOG_DIR}}/qdrant-out.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },

    // ────────────────────────────────────────────────────────────
    // 7. Phoenix Watcher (Self-Healing Daemon)
    // ────────────────────────────────────────────────────────────
    // 不死鸟 (Phoenix) — business-level self-healing daemon.
    // Periodically checks all services listed above. When a
    // service is found dead, it attempts automatic restart.
    // Features: cooldown timers, circuit breaker (after N failures),
    // version-based rollback, Feishu webhook alerts.
    //
    // Configuration file: {{PHOENIX_DIR}}/config.json
    // Logs are written to {{PHOENIX_LOG_DIR}}/phoenix.log
    {
      name: 'phoenix-watcher',
      script: '{{HERMES_VENV_PYTHON}}',
      args: '{{PHOENIX_DIR}}/phoenix.py',
      cwd: '{{PHOENIX_DIR}}',
      interpreter: '',
      env: {
        PYTHONUNBUFFERED: '1',
        PHOENIX_CONFIG: '{{PHOENIX_DIR}}/config.json',
        PHOENIX_LOG_DIR: '{{PHOENIX_LOG_DIR}}',
        PM2_HOME: '{{PM2_HOME}}',
      },
      watch: false,
      // phoenix has its own internal loop; PM2 should restart it if it crashes
      max_restarts: 10,
      restart_delay: 5000,
      kill_timeout: 5000,
      error_file: '{{LOG_DIR}}/phoenix-watcher-error.log',
      out_file: '{{LOG_DIR}}/phoenix-watcher-out.log',
      merge_logs: true,
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },
  ],
};


/**
 * ═══════════════════════════════════════════════════════════════
 *  📖 VARIABLE REFERENCE
 * ═══════════════════════════════════════════════════════════════
 *
 *  ┌──────────────────────────────┬───────────────────────────────────────────┐
 *  │ Variable                     │ Description                              │
 *  ├──────────────────────────────┼───────────────────────────────────────────┤
 *  │ {{HERMES_DIR}}               │ Path to Hermes installation directory     │
 *  │ {{HERMES_HOME}}              │ Hermes home/config directory              │
 *  │ {{HERMES_VENV_PYTHON}}       │ Full path to Hermes venv python.exe      │
 *  │ {{HERMES_WEBUI_PORT}}        │ WebUI bridge port (default: 8648)        │
 *  │ {{HERMES_GATEWAY_PORT}}      │ Gateway port (default: 9090)             │
 *  │ {{HERMES_API_KEY}}           │ API key for Hermes gateway auth          │
 *  ├──────────────────────────────┼───────────────────────────────────────────┤
 *  │ {{FRAMEWORK_DIR}}            │ Path to framework/ directory             │
 *  │ {{FRAMEWORK_VENV_PYTHON}}    │ Path to framework venv python.exe        │
 *  │ {{FRAMEWORK_PORT}}           │ Framework service port (default: 18888)  │
 *  │ {{FRAMEWORK_API_KEY}}        │ API key for framework service auth       │
 *  │ {{FRAMEWORK_AGENT_DIR}}      │ Agent memory/state directory             │
 *  │ {{FRAMEWORK_CDP_DIR}}        │ CDP script directory                     │
 *  ├──────────────────────────────┼───────────────────────────────────────────┤
 *  │ {{OPENCLAW_DIR}}             │ OpenClaw package directory               │
 *  │ {{OPENCLAW_BIN}}             │ OpenClaw CLI binary path                 │
 *  │ {{OPENCLAW_PORT}}            │ OpenClaw gateway port (default: 18789)   │
 *  │ {{OPENCLAW_CONFIG_DIR}}      │ OpenClaw config directory                │
 *  │ {{OPENCLAW_API_KEY}}         │ API key for OpenClaw auth                │
 *  ├──────────────────────────────┼───────────────────────────────────────────┤
 *  │ {{CHROME_PATH}}              │ Full path to chrome.exe / google-chrome  │
 *  │ {{CHROME_USER_DATA_DIR}}     │ Chrome user data directory               │
 *  │ {{CDP_PORT}}                 │ Chrome remote debug port (default: 9333) │
 *  ├──────────────────────────────┼───────────────────────────────────────────┤
 *  │ {{QDRANT_PATH}}              │ Full path to qdrant executable           │
 *  │ {{QDRANT_HTTP_PORT}}         │ Qdrant HTTP port (default: 6333)         │
 *  │ {{QDRANT_GRPC_PORT}}         │ Qdrant gRPC port (default: 6334)         │
 *  │ {{QDRANT_STORAGE_DIR}}       │ Qdrant data storage directory            │
 *  ├──────────────────────────────┼───────────────────────────────────────────┤
 *  │ {{PHOENIX_DIR}}              │ Phoenix watcher scripts directory        │
 *  │ {{PHOENIX_LOG_DIR}}          │ Phoenix watcher log directory            │
 *  ├──────────────────────────────┼───────────────────────────────────────────┤
 *  │ {{LOG_DIR}}                  │ Central log output directory             │
 *  │ {{PM2_HOME}}                 │ PM2 home directory (for PM2 internals)   │
 *  └──────────────────────────────┴───────────────────────────────────────────┘
 *
 * ═══════════════════════════════════════════════════════════════
 */
