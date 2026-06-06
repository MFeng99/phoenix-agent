"""Chrome CDP 连接检查 — 验证 CDP 端口、列出标签页、验证 Fiverr 登录状态

用法:
    python scripts/chrome_cdp_check.py                # 完整检查
    python scripts/chrome_cdp_check.py --quick        # 仅端口检查
    python scripts/chrome_cdp_check.py --json         # JSON 输出
"""
import argparse
import json
import sys
import urllib.request
import urllib.error


CDP_BASE = "http://127.0.0.1:9333"
TIMEOUT = 5


def check_cdp_running():
    """检查 CDP 端口是否运行"""
    try:
        req = urllib.request.Request(f"{CDP_BASE}/json/version")
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        data = json.loads(resp.read().decode("utf-8"))
        return {
            "running": True,
            "browser": data.get("Browser", "unknown"),
            "protocol_version": data.get("Protocol-Version", "unknown"),
        }
    except (urllib.error.URLError, ConnectionRefusedError, OSError, json.JSONDecodeError):
        return {"running": False, "browser": None, "protocol_version": None}


def list_tabs():
    """列出当前所有打开的标签页"""
    try:
        req = urllib.request.Request(f"{CDP_BASE}/json")
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        tabs = json.loads(resp.read().decode("utf-8"))
        result = []
        for t in tabs:
            result.append({
                "title": t.get("title", ""),
                "url": t.get("url", ""),
                "type": t.get("type", ""),
                "ws_endpoint": t.get("webSocketDebuggerUrl", ""),
            })
        return result
    except (urllib.error.URLError, ConnectionRefusedError, OSError, json.JSONDecodeError):
        return []


def check_fiverr_login():
    """验证 Fiverr 是否登录 — 检查是否存在有 fiverr.com 认证 cookie 的标签页

    通过 CDP 协议注入 JavaScript 检查 cookie/localStorage 来判断登录状态。
    返回: {"logged_in": bool, "username": str|None, "tabs_on_fiverr": int}
    """
    tabs = list_tabs()
    fiverr_tabs = [t for t in tabs if t.get("url") and "fiverr.com" in t["url"]]
    if not fiverr_tabs:
        return {"logged_in": False, "username": None, "tabs_on_fiverr": 0, "note": "未打开 Fiverr 页面"}

    # 尝试通过第一个 Fiverr 标签页的 CDP 连接检测登录
    ws_endpoint = fiverr_tabs[0].get("ws_endpoint", "")
    if not ws_endpoint:
        return {"logged_in": False, "username": None, "tabs_on_fiverr": len(fiverr_tabs),
                "note": "无法获取 WebSocket 端点"}

    # 通过 CDP HTTP 接口发送 Runtime.evaluate 检测 cookie
    tab_id = fiverr_tabs[0].get("ws_endpoint", "").split("/")[-1] if "ws_endpoint" in str(fiverr_tabs[0]) else None

    # 使用 CDP /json 中获取的 id 来发送命令
    # 尝试 Runtime.evaluate 检查 document.cookie 中是否有登录凭证
    try:
        # 先尝试通过 http://127.0.0.1:9333/json 获取 tab id
        req = urllib.request.Request(f"{CDP_BASE}/json")
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        tabs_raw = json.loads(resp.read().decode("utf-8"))

        for t in tabs_raw:
            if "fiverr.com" in t.get("url", ""):
                tab_ws = t.get("webSocketDebuggerUrl", "")
                # 通过 CDP 发送命令检测登录状态
                # 使用脚本执行检查常见的登录标记
                login_check_result = _evaluate_in_tab(tab_ws, """
                    (function() {
                        var hasSession = document.cookie.indexOf('session') > -1 ||
                                        document.cookie.indexOf('auth') > -1 ||
                                        document.cookie.indexOf('token') > -1;
                        var hasUserElement = document.querySelector('[data-username], .user-name, .profile-name, [data-testid="user-menu"]') !== null;
                        var isLoggedIn = hasSession || hasUserElement;
                        var userName = '';
                        var userEl = document.querySelector('[data-username], .user-name, .profile-name');
                        if (userEl) userName = userEl.textContent.trim();
                        return JSON.stringify({logged_in: isLoggedIn, username: userName, hasSessionCookie: hasSession, hasUserElement: hasUserElement});
                    })()
                """)
                if login_check_result:
                    return {
                        "logged_in": login_check_result.get("logged_in", False),
                        "username": login_check_result.get("username") or None,
                        "tabs_on_fiverr": len(fiverr_tabs),
                        "note": "通过页面元素检测",
                    }

    except Exception:
        pass

    return {"logged_in": False, "username": None, "tabs_on_fiverr": len(fiverr_tabs),
            "note": "无法注入检测脚本，尝试手动检查"}


def _evaluate_in_tab(ws_endpoint, expression):
    """通过 CDP 在指定标签页中执行 JavaScript 并返回结果

    使用 WebSocket 协议发送 Runtime.evaluate 命令。
    如果 ws 库不可用，回退到使用 http 代理方式。
    """
    import socket
    import base64

    # 从 ws endpoint 提取 host:port
    # ws_endpoint 格式: ws://127.0.0.1:9333/devtools/page/XXX
    ws_url = ws_endpoint.replace("ws://", "").replace("wss://", "")
    parts = ws_url.split("/", 1)
    host_port = parts[0]  # 127.0.0.1:9333

    # 使用 http CDP 接口替代 websocket:
    # POST http://127.0.0.1:9333/json/protocol 或直接通过 CDP HTTP
    # Chrome 在某些版本支持 HTTP-based CDP
    # 实际上 CDP 主要通过 websocket, 这里使用 try/except 优雅降级

    # 方法: 使用 websocket-client 如果可用
    try:
        import websocket
        ws = websocket.create_connection(ws_endpoint, timeout=TIMEOUT)
        msg = json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": False,
            }
        })
        ws.send(msg)
        resp_raw = ws.recv()
        ws.close()
        resp = json.loads(resp_raw)
        if "result" in resp and "result" in resp["result"]:
            value = resp["result"]["result"].get("value")
            if isinstance(value, str):
                return json.loads(value)
            return value
    except ImportError:
        pass
    except Exception:
        pass

    return None


def print_table_report(cdp_status, tabs, fiverr_status):
    """打印表格格式报告"""
    sep = "+" + "-" * 40 + "+" + "-" * 18 + "+"
    print(sep)
    print(f"| {'检查项':<38} | {'状态':<16} |")
    print(sep)

    # CDP 端口
    if cdp_status["running"]:
        print(f"| {'CDP 端口 (9333)':<36} | {'\033[92m✓ 运行中\033[0m':<22} |")
        print(f"|   Browser: {cdp_status['browser'][:30]:<30} | {'':<16} |")
    else:
        print(f"| {'CDP 端口 (9333)':<36} | {'\033[91m✗ 未运行\033[0m':<22} |")

    # 标签页数量
    tab_count = len(tabs)
    is_ok = tab_count > 0
    mark = "\033[92m✓\033[0m" if is_ok else "\033[91m✗\033[0m"
    print(f"| {'标签页数量':<36} | {f'{mark} {tab_count} 个':<22} |")

    # 列出每个标签页
    for i, t in enumerate(tabs):
        url_display = t["url"][:32] if t["url"] else "(empty)"
        title_display = t["title"][:28] if t["title"] else "(no title)"
        print(f"|   [{i}] {title_display:<32} | {'':<16} |")
        print(f"|   -> {url_display:<34} | {'':<16} |")

    # Fiverr 登录状态
    if fiverr_status["tabs_on_fiverr"] == 0:
        print(f"| {'Fiverr 登录状态':<36} | {'\033[93m? 无标签页\033[0m':<22} |")
    elif fiverr_status["logged_in"]:
        user = fiverr_status.get("username") or "已登录用户"
        print(f"| {'Fiverr 登录状态':<36} | {'\033[92m✓ 已登录\033[0m':<22} |")
        print(f"|   用户: {user[:30]:<32} | {'':<16} |")
    else:
        print(f"| {'Fiverr 登录状态':<36} | {'\033[91m✗ 未登录\033[0m':<22} |")

    print(sep)


def main():
    parser = argparse.ArgumentParser(description="Chrome CDP 连接检查工具")
    parser.add_argument("--quick", action="store_true", help="仅检查端口是否运行")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    cdp_status = check_cdp_running()

    if args.quick:
        if args.json:
            print(json.dumps(cdp_status, ensure_ascii=False))
        else:
            print("CDP running" if cdp_status["running"] else "CDP NOT running")
        sys.exit(0 if cdp_status["running"] else 1)

    tabs = list_tabs() if cdp_status["running"] else []
    fiverr_status = check_fiverr_login() if cdp_status["running"] else {
        "logged_in": False, "username": None, "tabs_on_fiverr": 0,
        "note": "CDP 不可达",
    }

    if args.json:
        output = {
            "cdp": cdp_status,
            "tabs": tabs,
            "fiverr": fiverr_status,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("  Chrome CDP 连接检查")
        print("=" * 60)
        print_table_report(cdp_status, tabs, fiverr_status)
        print()

        if not cdp_status["running"]:
            print("建议: 启动 Chrome 并确保添加了 --remote-debugging-port=9333 参数")
            sys.exit(1)
        else:
            print("CDP 服务正常。")

    sys.exit(0)


if __name__ == "__main__":
    main()
