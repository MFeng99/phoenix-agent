@echo off
setlocal enabledelayedexpansion

:: ==========================================================================
:: AgentOS — Windows Installer (install.bat)
:: ==========================================================================
:: This script performs a full local installation of AgentOS including
:: prerequisite checks, dependency installation, and service startup.
:: ==========================================================================

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "FRAMEWORK_DIR=%ROOT%\framework"
set "VENV_DIR=%ROOT%\venv"

set "PASS_COLOR=92"
set "FAIL_COLOR=91"
set "INFO_COLOR=96"
set "HEAD_COLOR=95"

echo.
echo [%HEAD_COLOR%m================================================================================[0m
echo [%HEAD_COLOR%m                     AgentOS — Windows Installer[0m
echo [%HEAD_COLOR%m================================================================================[0m
echo.

:: ---------- helper: check.exe ----------
set "EXE_CHECKED="
for %%X in (findstr.exe) do set "EXE_CHECKED=%%~$PATH:X"
if not defined EXE_CHECKED (
    echo [%FAIL_COLOR%m[FAIL][0m findstr.exe not found — cannot continue.
    exit /b 1
)

:: ---------- helper: pass/fail ----------
set "ERR_COUNT=0"

:pass_echo
    echo [%PASS_COLOR%m  [PASS][0m %~1
    exit /b 0

:fail_echo
    echo [%FAIL_COLOR%m  [FAIL][0m %~1
    set /a ERR_COUNT+=1
    exit /b 0

:info_echo
    echo [%INFO_COLOR%m  [INFO][0m %~1
    exit /b 0

:: ==========================================================================
echo.
echo [%HEAD_COLOR%m--- Step 1/12: Checking Node.js ------------------------------------------------[0m
echo.

where node >nul 2>nul
if %ERRORLEVEL% neq 0 (
    call :fail_echo "Node.js is not installed or not in PATH. Download from https://nodejs.org/"
) else (
    for /f "tokens=*" %%i in ('node --version') do set "NODE_VER=%%i"
    call :pass_echo "Node.js found — !NODE_VER!"
)

where npm >nul 2>nul
if %ERRORLEVEL% neq 0 (
    call :fail_echo "npm is not installed or not in PATH."
) else (
    for /f "tokens=*" %%i in ('npm --version') do set "NPM_VER=%%i"
    echo [%INFO_COLOR%m  [INFO][0m npm found — v!NPM_VER!
)

if %ERR_COUNT% gtr 0 (
    echo.
    echo [%FAIL_COLOR%mAborting: Node.js/npm is required.[0m
    exit /b 1
)

:: ==========================================================================
echo.
echo [%HEAD_COLOR%m--- Step 2/12: Checking Python 3.10+ ---------------------------------------------[0m
echo.

set "PYTHON_EXE="
python --version >nul 2>nul
if %ERRORLEVEL% equ 0 (
    for /f "tokens=2 delims= " %%i in ('python --version 2^>^&1') do set "PY_VER=%%i"
    for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
        set "PY_MAJOR=%%a"
        set "PY_MINOR=%%b"
    )
    if !PY_MAJOR! geq 3 (
        if !PY_MINOR! geq 10 (
            set "PYTHON_EXE=python"
            call :pass_echo "Python found — !PY_VER! (^>=3.10)"
        ) else (
            call :fail_echo "Python !PY_VER! is too old. 3.10+ required."
        )
    ) else (
        call :fail_echo "Python !PY_VER! is too old. 3.10+ required."
    )
) else (
    call :fail_echo "Python is not installed or not in PATH. Download from https://python.org"
)

if not defined PYTHON_EXE (
    :: Fallback: try py launcher
    py --version >nul 2>nul
    if !ERRORLEVEL! equ 0 (
        for /f "tokens=2 delims= " %%i in ('py --version 2^>^&1') do set "PY_VER=%%i"
        for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
            set "PY_MAJOR=%%a"
            set "PY_MINOR=%%b"
        )
        if !PY_MAJOR! geq 3 (
            if !PY_MINOR! geq 10 (
                set "PYTHON_EXE=py"
                call :pass_echo "Python (py launcher) found — !PY_VER!"
            )
        )
    )
)

if not defined PYTHON_EXE (
    echo.
    echo [%FAIL_COLOR%mAborting: Python 3.10+ is required.[0m
    exit /b 1
)

:: ==========================================================================
echo.
echo [%HEAD_COLOR%m--- Step 3/12: Checking Chrome / Edge -------------------------------------------[0m
echo.

set "CHROME_PATH="
set "EDGE_PATH="

:: Chrome — common install locations
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe"
) else if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
) else if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_PATH=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
) else (
    :: Check via where command
    where chrome >nul 2>nul
    if !ERRORLEVEL! equ 0 (
        for /f "tokens=*" %%i in ('where chrome') do (
            set "CHROME_PATH=%%i"
            goto :chrome_found
        )
    )
)
:chrome_found

:: Edge — common install locations
if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
    set "EDGE_PATH=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
) else if exist "C:\Program Files\Microsoft\Edge\Application\msedge.exe" (
    set "EDGE_PATH=C:\Program Files\Microsoft\Edge\Application\msedge.exe"
) else (
    where msedge >nul 2>nul
    if !ERRORLEVEL! equ 0 (
        for /f "tokens=*" %%i in ('where msedge') do (
            set "EDGE_PATH=%%i"
            goto :edge_found
        )
    )
)
:edge_found

if defined CHROME_PATH (
    call :pass_echo "Chrome found — !CHROME_PATH!"
) else if defined EDGE_PATH (
    call :pass_echo "Edge found — !EDGE_PATH!"
) else (
    call :fail_echo "Neither Chrome nor Edge was found. CDP browser features may not work."
    echo [%INFO_COLOR%m  [INFO][0m Install Chrome from https://google.com/chrome or Edge from https://microsoft.com/edge
)

:: ==========================================================================
echo.
echo [%HEAD_COLOR%m--- Step 4/12: Installing npm global packages ------------------------------------[0m
echo.

echo [%INFO_COLOR%m  [INFO][0m Checking/installing: pm2, orchestrator-web-ui, executor ...

npm list -g pm2 >nul 2>nul
if %ERRORLEVEL% equ 0 (
    call :pass_echo "pm2 already installed globally"
) else (
    echo [%INFO_COLOR%m  [INFO][0m Installing pm2 globally ...
    npm install -g pm2
    if %ERRORLEVEL% neq 0 (
        call :fail_echo "Failed to install pm2"
    ) else (
        call :pass_echo "pm2 installed globally"
    )
)

:: ---------------------------------------------------------------------------
:: Runtime backend packages (default presets).
::
:: The framework orchestrates an external agent runtime. These two npm
:: packages are the default presets this installer ships with; change them
:: to target a different runtime that exposes the same CLI / HTTP contract.
:: ---------------------------------------------------------------------------
set "RUNTIME_UI_PKG=hermes-web-ui"
set "RUNTIME_EXEC_PKG=openclaw"
set "RUNTIME_WEBUI_ARGS=-m hermes.webui_bridge"
set "RUNTIME_GATEWAY_ARGS=-m hermes.gateway run"

npm list -g !RUNTIME_UI_PKG! >nul 2>nul
if %ERRORLEVEL% equ 0 (
    call :pass_echo "orchestrator UI package already installed globally"
) else (
    echo [%INFO_COLOR%m  [INFO][0m Installing orchestrator UI package ...
    npm install -g !RUNTIME_UI_PKG!
    if %ERRORLEVEL% neq 0 (
        call :fail_echo "Failed to install orchestrator UI package"
    ) else (
        call :pass_echo "orchestrator UI package installed globally"
    )
)

npm list -g !RUNTIME_EXEC_PKG! >nul 2>nul
if %ERRORLEVEL% equ 0 (
    call :pass_echo "executor package already installed globally"
) else (
    echo [%INFO_COLOR%m  [INFO][0m Installing executor package ...
    npm install -g !RUNTIME_EXEC_PKG!
    if %ERRORLEVEL% neq 0 (
        call :fail_echo "Failed to install executor package"
    ) else (
        call :pass_echo "executor package installed globally"
    )
)

:: ==========================================================================
echo.
echo [%HEAD_COLOR%m--- Step 5/12: Creating Python virtual environment -------------------------------[0m
echo.

if exist "%VENV_DIR%\Scripts\python.exe" (
    call :pass_echo "Virtual environment already exists at !VENV_DIR!"
) else (
    echo [%INFO_COLOR%m  [INFO][0m Creating Python virtual environment ...
    "%PYTHON_EXE%" -m venv "%VENV_DIR%"
    if %ERRORLEVEL% neq 0 (
        call :fail_echo "Failed to create virtual environment"
    ) else (
        call :pass_echo "Virtual environment created at !VENV_DIR!"
    )
)

echo [%INFO_COLOR%m  [INFO][0m Installing Python dependencies from requirements.txt ...
"%VENV_DIR%\Scripts\pip" install --upgrade pip >nul 2>nul

"%VENV_DIR%\Scripts\pip" install -r "%ROOT%\requirements.txt"
if %ERRORLEVEL% neq 0 (
    call :fail_echo "Failed to install some Python packages. Check errors above."
) else (
    call :pass_echo "Python dependencies installed successfully"
)

:: ==========================================================================
echo.
echo [%HEAD_COLOR%m--- Step 6/12: Copying .env.example to .env --------------------------------------[0m
echo.

if exist "%ROOT%\.env" (
    call :pass_echo ".env already exists — skipping"
) else (
    if exist "%ROOT%\.env.example" (
        copy "%ROOT%\.env.example" "%ROOT%\.env" >nul
        if %ERRORLEVEL% equ 0 (
            call :pass_echo ".env created from .env.example"
        ) else (
            call :fail_echo "Failed to copy .env.example to .env"
        )
    ) else (
        call :fail_echo ".env.example not found — creating minimal .env"
        :: Create a minimal .env
        (
            echo # AgentOS Environment
            echo AGENTOS_ROOT=!ROOT!
            echo FRAMEWORK_DIR=!FRAMEWORK_DIR!
        ) > "%ROOT%\.env"
        call :pass_echo "Minimal .env created"
    )
)

:: ==========================================================================
echo.
echo [%HEAD_COLOR%m--- Step 7/12: Copying config/env.example.json to config/env.json ----------------[0m
echo.

set "TARGET_ENV_JSON=%FRAMEWORK_DIR%\config\env.json"
set "SOURCE_ENV_JSON=%FRAMEWORK_DIR%\config\env.example.json"

if exist "%TARGET_ENV_JSON%" (
    call :pass_echo "config/env.json already exists — skipping"
) else (
    if exist "%SOURCE_ENV_JSON%" (
        copy "%SOURCE_ENV_JSON%" "%TARGET_ENV_JSON%" >nul
        if %ERRORLEVEL% equ 0 (
            call :pass_echo "config/env.json created from env.example.json"
        ) else (
            call :fail_echo "Failed to copy env.example.json to env.json"
        )
    ) else (
        call :fail_echo "Source file not found: %SOURCE_ENV_JSON%"
    )
)

:: ==========================================================================
echo.
echo [%HEAD_COLOR%m--- Step 8/12: Copying config/permissions.example.json to config/permissions.json -[0m
echo.

set "TARGET_PERM_JSON=%FRAMEWORK_DIR%\config\permissions.json"
set "SOURCE_PERM_JSON=%FRAMEWORK_DIR%\config\permissions.example.json"

if exist "%TARGET_PERM_JSON%" (
    call :pass_echo "config/permissions.json already exists — skipping"
) else (
    if exist "%SOURCE_PERM_JSON%" (
        copy "%SOURCE_PERM_JSON%" "%TARGET_PERM_JSON%" >nul
        if %ERRORLEVEL% equ 0 (
            call :pass_echo "config/permissions.json created from permissions.example.json"
        ) else (
            call :fail_echo "Failed to copy permissions.example.json to permissions.json"
        )
    ) else (
        call :fail_echo "Source file not found: %SOURCE_PERM_JSON%"
    )
)

:: ==========================================================================
echo.
echo [%HEAD_COLOR%m--- Step 9/12: Creating ecosystem.config.js from template ------------------------[0m
echo.

set "ECOSYSTEM_TEMPLATE=%ROOT%\ecosystem.config.template.js"
set "ECOSYSTEM_FILE=%ROOT%\ecosystem.config.js"

if exist "%ECOSYSTEM_FILE%" (
    call :pass_echo "ecosystem.config.js already exists — skipping"
) else (
    if not exist "%ECOSYSTEM_TEMPLATE%" (
        call :fail_echo "Template not found: %ECOSYSTEM_TEMPLATE%"
    ) else (
        :: Build all variable values for template replacement
        set "VAL_ORCHESTRATOR_DIR=%ROOT%\orchestrator"
        set "VAL_ORCHESTRATOR_HOME=%USERPROFILE%\.agent-os"
        set "VAL_ORCHESTRATOR_VENV_PY=%VENV_DIR%\Scripts\python.exe"
        set "VAL_ORCHESTRATOR_WEBUI_PORT=8648"
        set "VAL_ORCHESTRATOR_GATEWAY_PORT=9090"
        set "VAL_ORCHESTRATOR_API_KEY=change-me-orchestrator-api-key"
        set "VAL_ORCHESTRATOR_WEBUI_ARGS=!RUNTIME_WEBUI_ARGS!"
        set "VAL_ORCHESTRATOR_GATEWAY_ARGS=!RUNTIME_GATEWAY_ARGS!"

        set "VAL_FRAMEWORK_DIR=%FRAMEWORK_DIR%"
        set "VAL_FRAMEWORK_VENV_PY=%VENV_DIR%\Scripts\python.exe"
        set "VAL_FRAMEWORK_PORT=18888"
        set "VAL_FRAMEWORK_API_KEY=change-me-framework-api-key"
        set "VAL_FRAMEWORK_AGENT_DIR=%ROOT%\data\agents"
        set "VAL_FRAMEWORK_CDP_DIR=%FRAMEWORK_DIR%\scripts"

        set "VAL_EXECUTOR_DIR=%APPDATA%\npm\node_modules\!RUNTIME_EXEC_PKG!"
        set "VAL_EXECUTOR_BIN=%APPDATA%\npm\!RUNTIME_EXEC_PKG!"
        set "VAL_EXECUTOR_PORT=18789"
        set "VAL_EXECUTOR_CONFIG_DIR=%ROOT%\config"
        set "VAL_EXECUTOR_API_KEY=change-me-executor-api-key"
        set "VAL_EXECUTOR_CLI=%RUNTIME_EXEC_PKG%"

        if defined CHROME_PATH (
            set "VAL_CHROME_PATH=!CHROME_PATH!"
        ) else if defined EDGE_PATH (
            set "VAL_CHROME_PATH=!EDGE_PATH!"
        ) else (
            set "VAL_CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe"
        )
        set "VAL_CHROME_USER_DIR=%ROOT%\data\chrome-user-data"
        set "VAL_CDP_PORT=9333"

        set "VAL_QDRANT_PATH=%ROOT%\qdrant\qdrant.exe"
        set "VAL_QDRANT_HTTP_PORT=6333"
        set "VAL_QDRANT_GRPC_PORT=6334"
        set "VAL_QDRANT_STORAGE=%ROOT%\data\qdrant"

        set "VAL_PHOENIX_DIR=%FRAMEWORK_DIR%\scripts\phoenix"
        set "VAL_PHOENIX_LOG_DIR=%USERPROFILE%\Desktop\agent-os-logs"

        set "VAL_LOG_DIR=%USERPROFILE%\Desktop\agent-os-logs"
        set "VAL_PM2_HOME=%USERPROFILE%\.pm2"

        :: Use PowerShell for robust multi-variable template replacement
        powershell -Command ^
            "$c = Get-Content '%ECOSYSTEM_TEMPLATE%' -Raw; " ^
            "$c = $c -replace '\{\{ORCHESTRATOR_DIR\}\}',       '!VAL_ORCHESTRATOR_DIR:\=\\!'; " ^
            "$c = $c -replace '\{\{ORCHESTRATOR_HOME\}\}',      '!VAL_ORCHESTRATOR_HOME:\=\\!'; " ^
            "$c = $c -replace '\{\{ORCHESTRATOR_VENV_PYTHON\}\}', '!VAL_ORCHESTRATOR_VENV_PY:\=\\!'; " ^
            "$c = $c -replace '\{\{ORCHESTRATOR_WEBUI_ARGS\}\}', '!VAL_ORCHESTRATOR_WEBUI_ARGS!'; " ^
            "$c = $c -replace '\{\{ORCHESTRATOR_GATEWAY_ARGS\}\}', '!VAL_ORCHESTRATOR_GATEWAY_ARGS!'; " ^
            "$c = $c -replace '\{\{ORCHESTRATOR_WEBUI_PORT\}\}', '!VAL_ORCHESTRATOR_WEBUI_PORT!'; " ^
            "$c = $c -replace '\{\{ORCHESTRATOR_GATEWAY_PORT\}\}', '!VAL_ORCHESTRATOR_GATEWAY_PORT!'; " ^
            "$c = $c -replace '\{\{ORCHESTRATOR_API_KEY\}\}',   '!VAL_ORCHESTRATOR_API_KEY!'; " ^
            "$c = $c -replace '\{\{FRAMEWORK_DIR\}\}',    '!VAL_FRAMEWORK_DIR:\=\\!'; " ^
            "$c = $c -replace '\{\{FRAMEWORK_VENV_PYTHON\}\}', '!VAL_FRAMEWORK_VENV_PY:\=\\!'; " ^
            "$c = $c -replace '\{\{FRAMEWORK_PORT\}\}',   '!VAL_FRAMEWORK_PORT!'; " ^
            "$c = $c -replace '\{\{FRAMEWORK_API_KEY\}\}', '!VAL_FRAMEWORK_API_KEY!'; " ^
            "$c = $c -replace '\{\{FRAMEWORK_AGENT_DIR\}\}', '!VAL_FRAMEWORK_AGENT_DIR:\=\\!'; " ^
            "$c = $c -replace '\{\{FRAMEWORK_CDP_DIR\}\}', '!VAL_FRAMEWORK_CDP_DIR:\=\\!'; " ^
            "$c = $c -replace '\{\{EXECUTOR_DIR\}\}',     '!VAL_EXECUTOR_DIR:\=\\!'; " ^
            "$c = $c -replace '\{\{EXECUTOR_BIN\}\}',     '!VAL_EXECUTOR_BIN:\=\\!'; " ^
            "$c = $c -replace '\{\{EXECUTOR_PORT\}\}',    '!VAL_EXECUTOR_PORT!'; " ^
            "$c = $c -replace '\{\{EXECUTOR_CONFIG_DIR\}\}', '!VAL_EXECUTOR_CONFIG_DIR:\=\\!'; " ^
            "$c = $c -replace '\{\{EXECUTOR_API_KEY\}\}', '!VAL_EXECUTOR_API_KEY!'; " ^
            "$c = $c -replace '\{\{EXECUTOR_CLI\}\}',     '!VAL_EXECUTOR_CLI!'; " ^
            "$c = $c -replace '\{\{CHROME_PATH\}\}',      '!VAL_CHROME_PATH:\=\\!'; " ^
            "$c = $c -replace '\{\{CHROME_USER_DATA_DIR\}\}', '!VAL_CHROME_USER_DIR:\=\\!'; " ^
            "$c = $c -replace '\{\{CDP_PORT\}\}',         '!VAL_CDP_PORT!'; " ^
            "$c = $c -replace '\{\{QDRANT_PATH\}\}',      '!VAL_QDRANT_PATH:\=\\!'; " ^
            "$c = $c -replace '\{\{QDRANT_HTTP_PORT\}\}', '!VAL_QDRANT_HTTP_PORT!'; " ^
            "$c = $c -replace '\{\{QDRANT_GRPC_PORT\}\}', '!VAL_QDRANT_GRPC_PORT!'; " ^
            "$c = $c -replace '\{\{QDRANT_STORAGE_DIR\}\}', '!VAL_QDRANT_STORAGE:\=\\!'; " ^
            "$c = $c -replace '\{\{PHOENIX_DIR\}\}',      '!VAL_PHOENIX_DIR:\=\\!'; " ^
            "$c = $c -replace '\{\{PHOENIX_LOG_DIR\}\}',  '!VAL_PHOENIX_LOG_DIR:\=\\!'; " ^
            "$c = $c -replace '\{\{LOG_DIR\}\}',          '!VAL_LOG_DIR:\=\\!'; " ^
            "$c = $c -replace '\{\{PM2_HOME\}\}',         '!VAL_PM2_HOME:\=\\!'; " ^
            "Set-Content '%ECOSYSTEM_FILE%' -Value $c -Encoding UTF8"

        if %ERRORLEVEL% equ 0 (
            call :pass_echo "ecosystem.config.js created from template"
        ) else (
            call :fail_echo "Failed to create ecosystem.config.js from template"
        )
    )
)

:: ==========================================================================
echo.
echo [%HEAD_COLOR%m--- Step 10/12: npm install in framework/ ----------------------------------------[0m
echo.

if exist "%FRAMEWORK_DIR%\node_modules" (
    call :pass_echo "framework/node_modules already exists — skipping npm install"
) else (
    if exist "%FRAMEWORK_DIR%\package.json" (
        echo [%INFO_COLOR%m  [INFO][0m Running npm install in framework/ ...
        pushd "%FRAMEWORK_DIR%"
        npm install
        set "INSTALL_ERR=%ERRORLEVEL%"
        popd
        if !INSTALL_ERR! equ 0 (
            call :pass_echo "npm install completed in framework/"
        ) else (
            call :fail_echo "npm install failed in framework/"
        )
    ) else (
        call :fail_echo "No package.json found in framework/"
    )
)

:: ==========================================================================
echo.
echo [%HEAD_COLOR%m--- Step 11/12: Starting services via PM2 ----------------------------------------[0m
echo.

if not exist "%ECOSYSTEM_FILE%" (
    call :fail_echo "ecosystem.config.js not found — cannot start services"
) else (
    where pm2 >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        call :fail_echo "pm2 not found in PATH — cannot start services"
    ) else (
        echo [%INFO_COLOR%m  [INFO][0m Stopping any existing AgentOS PM2 processes ...
        for %%S in (orchestrator-webui-bridge orchestrator-gateway framework-service executor-gateway chrome-cdp qdrant phoenix-watcher) do (
            pm2 delete %%S 2>nul
        )

        pushd "%ROOT%"
        echo [%INFO_COLOR%m  [INFO][0m Starting services with PM2 ...
        pm2 start "%ECOSYSTEM_FILE%"
        set "PM2_ERR=%ERRORLEVEL%"
        popd

        if !PM2_ERR! equ 0 (
            echo [%PASS_COLOR%m  [PASS][0m Services started via PM2
            echo [%INFO_COLOR%m  [INFO][0m Save PM2 process list for auto-restart ...
            pm2 save >nul 2>nul
        ) else (
            call :fail_echo "PM2 failed to start services"
        )
    )
)

:: ==========================================================================
echo.
echo [%HEAD_COLOR%m--- Step 12/12: Success ---------------------------------------------------------[0m
echo.

echo [%PASS_COLOR%m================================================================================[0m
echo [%PASS_COLOR%m                  AgentOS installation complete![0m
echo [%PASS_COLOR%m================================================================================[0m
echo.
echo [%INFO_COLOR%m  Summary:[0m
echo [%INFO_COLOR%m    Root dir:     [0m%ROOT%
echo [%INFO_COLOR%m    Python venv:  [0m%VENV_DIR%
if defined CHROME_PATH echo [%INFO_COLOR%m    Chrome:       [0m%CHROME_PATH%
if defined EDGE_PATH echo   [%INFO_COLOR%m    Edge:         [0m%EDGE_PATH%
echo [%INFO_COLOR%m    Framework:    [0m%FRAMEWORK_DIR%
echo [%INFO_COLOR%m    PM2 config:   [0m%ECOSYSTEM_FILE%
echo.
echo [%INFO_COLOR%m  Common commands:[0m
echo [%INFO_COLOR%m    pm2 status                    [0m— View running services
echo [%INFO_COLOR%m    pm2 logs                      [0m— View service logs
echo [%INFO_COLOR%m    pm2 stop all                  [0m— Stop all services
echo [%INFO_COLOR%m    pm2 restart all               [0m— Restart all services
echo [%INFO_COLOR%m    pm2 delete all                [0m— Delete all services from PM2
echo [%INFO_COLOR%m    %VENV_DIR%\Scripts\python     [0m— Python interpreter
echo.
echo [%INFO_COLOR%m  Services managed by PM2:[0m
echo [%INFO_COLOR%m    orchestrator-webui-bridge   [0m— Orchestrator Web UI (port 8648)
echo [%INFO_COLOR%m    orchestrator-gateway        [0m— Orchestrator API Gateway (port 9090)
echo [%INFO_COLOR%m    framework-service     [0m— FastAPI Framework (port 18888)
echo [%INFO_COLOR%m    executor-gateway      [0m— Executor Agent Gateway (port 18789)
echo [%INFO_COLOR%m    chrome-cdp            [0m— Headless Chrome CDP (port 9333)
echo [%INFO_COLOR%m    qdrant                [0m— Vector Database (port 6333)
echo [%INFO_COLOR%m    phoenix-watcher       [0m— Self-Healing Daemon
echo.
echo [%INFO_COLOR%m  To get started:[0m
echo [%INFO_COLOR%m    1. Activate venv:  [0m%VENV_DIR%\Scripts\activate
echo [%INFO_COLOR%m    2. Check status:   [0mpm2 status
echo [%INFO_COLOR%m    3. View logs:      [0mpm2 logs
echo [%INFO_COLOR%m    4. Open Web UI:    [0mhttp://localhost:8648
echo.
if %ERR_COUNT% gtr 0 (
    echo [%FAIL_COLOR%m  WARNING: %ERR_COUNT% step(s) reported failures above.[0m
    echo [%FAIL_COLOR%m  Review the output and resolve issues before using AgentOS.[0m
    echo.
)

endlocal
exit /b %ERR_COUNT%
