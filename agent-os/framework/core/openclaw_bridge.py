"""OpenClaw Bridge — Python封装，让Hermes调用OpenClaw模块能力

融合模块:
1. Computer Use — 桌面GUI自动化（截图、点击、输入）
2. Canvas — WebView可视化渲染仪表盘
3. Sandbox — Docker隔离执行（需要Docker）
4. Agent — 通过OpenClaw调度多Agent
"""

import subprocess
import os
import tempfile
import time
import json
from datetime import datetime

try:
    from scripts.agent_log import log_action
except ImportError:
    def log_action(source, action, detail, status):
        pass


def call_oc(args, timeout=60):
    """调 openclaw CLI（Windows需shell=True因为它是sh脚本）"""
    cmd = "openclaw " + " ".join(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=timeout, shell=True)
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }
    except FileNotFoundError:
        return {"success": False, "error": "openclaw CLI not found"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Timeout ({timeout}s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def gateway_alive():
    """快速检查Gateway是否在运行"""
    try:
        r = subprocess.run(
            "curl -s -o /dev/null -w %{http_code} http://127.0.0.1:18789/",
            capture_output=True, text=True, timeout=5, shell=True)
        return r.stdout.strip() in ("200", "302", "301")
    except Exception:
        return False


# ─── Agent ──────────────────────────────────────────────────

def agent(message, agent_id="main"):
    """调度OpenClaw Agent执行任务"""
    return call_oc(
        ["agent", "--agent", agent_id, "--json", "--message", message],
        timeout=120,
    )


# ─── Computer Use ───────────────────────────────────────────

def screenshot(save_to=None):
    """桌面截图"""
    if not save_to:
        save_to = os.path.join(tempfile.gettempdir(),
                               f"shot_{int(time.time())}.png")
    r = agent(f"take a desktop screenshot and save to {save_to}")
    if r["success"] and os.path.exists(save_to):
        return {"success": True, "path": save_to, "size": os.path.getsize(save_to)}
    return {"success": False, "error": r.get("stderr", "no file")[:200]}


def click_at(x, y, button="left"):
    """点击桌面坐标"""
    return agent(f"click at ({x},{y}) with {button} button")


def type_text(text):
    """桌面级键盘输入"""
    return agent(f"type: {text}")


# ─── Canvas 可视化 ──────────────────────────────────────────

class Canvas:
    """WebView仪表盘和可视化"""

    def __init__(self):
        self._n = 0

    def _full_html(self, body, title):
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  background:#0d1117; color:#c9d1d9; padding:20px; }}
</style></head>
<body>{body}</body></html>"""

    def show(self, html, title="Hermes Canvas"):
        """渲染HTML到Canvas"""
        self._n += 1
        d = os.path.join(tempfile.gettempdir(), "hermes-canvas")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"c{self._n}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(self._full_html(html, title))
        r = agent(f"display canvas: {path}")
        return {"success": r["success"], "file": path}

    def dashboard(self, data):
        """渲染实时仪表盘"""
        title = data.get("title", "Dashboard")
        status = data.get("status", "unknown")
        color = "#3fb950" if status == "OK" else "#f85149"

        metrics = ""
        for m in data.get("metrics", []):
            metrics += f"""<div style="background:#161b22;border-radius:8px;padding:16px;
  min-width:140px"><div style="color:#8b949e;font-size:12px">{m['label']}</div>
  <div style="color:{m.get('color','#58a6ff')};font-size:28px;font-weight:700">{m['value']}</div></div>"""

        alerts = ""
        for a in data.get("alerts", []):
            alerts += f"""<div style="background:#3d1f1f;border:1px solid #f85149;
  border-radius:4px;padding:8px 12px;margin:4px 0;font-size:13px">⚠ {a}</div>"""

        rows = ""
        for a in data.get("recent_actions", []):
            si = {"OK": "✅", "FAILED": "❌", "RUNNING": "🔄", "TODO": "📝"}.get(
                a.get("status", ""), "⚪")
            rows += f"<tr><td style='padding:6px 12px;color:#8b949e;font-size:12px'>{a.get('time','')}</td><td style='padding:6px 12px'>{a.get('action','')}</td><td style='padding:6px 12px'>{si}</td><td style='padding:6px 12px;color:#8b949e;font-size:12px'>{a.get('detail','')}</td></tr>\n"

        html = f"""<div style="max-width:900px;margin:0 auto">
  <h1 style="font-size:24px;margin-bottom:8px">{title}</h1>
  <div style="color:#8b949e;margin-bottom:24px">
    状态: <span style="color:{color}">{status}</span>
    | 更新: {datetime.now().strftime('%H:%M:%S')}
  </div>
  <div style="display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap">{metrics}</div>
  {alerts}
  <h2 style="font-size:18px;margin:20px 0 12px">最近操作</h2>
  <table style="width:100%;border-collapse:collapse">
    <thead><tr style="background:#1c2128">
      <th style="padding:8px 12px;text-align:left;color:#8b949e">时间</th>
      <th style="padding:8px 12px;text-align:left;color:#8b949e">操作</th>
      <th style="padding:8px 12px;text-align:left;color:#8b949e">状态</th>
      <th style="padding:8px 12px;text-align:left;color:#8b949e">详情</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""
        return self.show(html, title)


# ─── Sandbox ────────────────────────────────────────────────

def docker_ready():
    """Docker是否可用"""
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        return r.returncode == 0
    except FileNotFoundError:
        return False


# ─── 统一查询 ──────────────────────────────────────────────

def health():
    return {
        "gateway": gateway_alive(),
        "docker": docker_ready(),
        "openclaw_cli": call_oc(["--version"], timeout=5).get("stdout", "").strip(),
    }
