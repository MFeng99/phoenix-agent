#!/usr/bin/env python3
"""
CDP Chrome Manager — Auto-launch Chrome with remote debugging on port 9333.
Eliminates the need for the user to manually run `启动CDP浏览器.bat`.

Usage:
    python cdp_manager.py check    — Check if CDP Chrome is running
    python cdp_manager.py launch   — Launch if not running, else no-op
    python cdp_manager.py ensure   — Check, auto-launch if needed, wait for ready
    python cdp_manager.py kill     — Gracefully close CDP Chrome
"""

import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

CDP_PORT = 9333
CHROME_PATH = os.environ.get("CHROME_PATH", "")
PROFILE_DIR = r"C:\chrome-cdp-profile"
CDP_HTTP = f"http://127.0.0.1:{CDP_PORT}/json"
MAX_WAIT = 15  # seconds to wait for Chrome to become ready


def is_chrome_running():
    """Check if Chrome CDP is accepting connections on the expected port."""
    try:
        req = urllib.request.Request(CDP_HTTP, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            return isinstance(data, list) and len(data) > 0
    except (urllib.error.URLError, json.JSONDecodeError, ConnectionRefusedError, OSError):
        return False


def has_chrome_process():
    """Check if any Chrome process exists (running but maybe not on our port)."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
            capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW
        )
        return b"chrome.exe" in result.stdout
    except Exception:
        return False


def launch_chrome():
    """Launch Chrome with remote debugging enabled."""
    if is_chrome_running():
        return True

    # Kill existing Chrome processes that might block the profile
    if has_chrome_process():
        subprocess.run(
            ["taskkill", "/f", "/im", "chrome.exe"],
            capture_output=True, timeout=5
        )
        time.sleep(2)

    # Launch Chrome with CDP
    args = [
        CHROME_PATH,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        f"--remote-allow-origins=http://127.0.0.1:{CDP_PORT}",
    ]

    try:
        subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
        )
        return True
    except Exception as e:
        print(f"ERROR: Failed to launch Chrome: {e}", file=sys.stderr)
        return False


def wait_for_ready(timeout=MAX_WAIT):
    """Wait until Chrome CDP is accepting connections."""
    start = time.time()
    while time.time() - start < timeout:
        if is_chrome_running():
            return True
        time.sleep(0.5)
    return False


def kill_chrome():
    """Kill Chrome processes gracefully."""
    subprocess.run(
        ["taskkill", "/f", "/im", "chrome.exe"],
        capture_output=True, timeout=5
    )
    time.sleep(1)
    return not has_chrome_process()


def ensure_running():
    """Check → auto-launch → wait for ready. Returns True if ready."""
    if is_chrome_running():
        print("OK: CDP Chrome already running on port %d" % CDP_PORT)
        return True

    print("Launching CDP Chrome on port %d..." % CDP_PORT)
    if not launch_chrome():
        print("ERROR: Failed to launch Chrome", file=sys.stderr)
        return False

    if wait_for_ready():
        elapsed = time.time()
        print("OK: CDP Chrome ready")
        return True
    else:
        print("ERROR: Chrome did not become ready within %ds" % MAX_WAIT, file=sys.stderr)
        return False


def get_tab_info():
    """Return list of tabs with title and URL for the user to see."""
    try:
        req = urllib.request.Request(CDP_HTTP, method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            tabs = json.loads(resp.read().decode())
            result = []
            for t in tabs:
                if t.get("type") == "page":
                    result.append({
                        "id": t["id"][:12],
                        "title": t.get("title", "")[:60],
                        "url": t.get("url", "")[:100],
                    })
            return result
    except Exception:
        return []


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "check"

    if action == "check":
        if is_chrome_running():
            tabs = get_tab_info()
            print("✓ CDP Chrome is running on port %d" % CDP_PORT)
            print("  Open tabs: %d" % len(tabs))
            for t in tabs:
                print("    - %s | %s" % (t["title"], t["url"]))
        else:
            print("✗ CDP Chrome is NOT running on port %d" % CDP_PORT)

    elif action == "launch":
        if launch_chrome() and wait_for_ready():
            print("✓ Chrome launched and ready on port %d" % CDP_PORT)
        else:
            print("✗ Failed to launch Chrome", file=sys.stderr)
            sys.exit(1)

    elif action == "ensure":
        if ensure_running():
            sys.exit(0)
        else:
            sys.exit(1)

    elif action == "kill":
        if kill_chrome():
            print("✓ Chrome killed")
        else:
            print("✗ Failed to kill Chrome", file=sys.stderr)
            sys.exit(1)

    else:
        print("Usage: cdp_manager.py [check|launch|ensure|kill]")
        sys.exit(1)
