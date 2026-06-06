"""共享操作日志 — Hermes↔OpenClaw 双Agent通信黑盒透明化

用法:
    from scripts.agent_log import log_action, tail_log, get_recent

    log_action("Hermes", "analyze", "评估用户意图为商品搜索", "OK")
    log_action("OpenClaw", "browser.open", "打开 Fiverr 卖家中心", "RUNNING")
    log_action("OpenClaw", "browser.fill", "填写商品标题: Test Product", "DONE")

    # 实时查看最近操作
    print(tail_log(10))          # 最近 10 条
    print(get_recent("FAILED"))  # 所有失败的操作

日志文件: ~/Desktop/framework_log.md (自动根据当前用户生成)
格式: | 时间 | Agent | 操作 | 状态 | 详情 |
"""
import os
import sys
import threading
from datetime import datetime, timezone


_LOG_PATH = os.path.join(os.path.expanduser("~"), "Desktop", "framework_log.md")

_LOCK = threading.Lock()

HEADER = """# Hermes + OpenClaw 共享操作日志

> 自动生成 — 记录 Hermes（推理/主控）与 OpenClaw（执行引擎）之间的每一步操作。
> 格式: | 时间 | Agent | 操作 | 状态 | 详情 |

| 时间 | Agent | 操作 | 状态 | 详情 |
|------|-------|------|------|------|
"""


def _ensure_header():
    """确保日志文件存在并包含表头"""
    if not os.path.exists(_LOG_PATH):
        with open(_LOG_PATH, "w", encoding="utf-8") as f:
            f.write(HEADER)


def _now():
    """返回北京时间格式字符串"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def log_action(agent, action, detail="", status="OK"):
    """记录一次操作到共享日志

    Args:
        agent: 执行者 — "Hermes" 或 "OpenClaw"
        action: 操作名，如 "analyze", "browser.open", "qdrant.search"
        detail: 操作详情，如 "搜索关键词: TikTok 商品"
        status: 操作状态 — "OK", "FAILED", "RUNNING", "PENDING", "DONE", "SKIPPED"

    Returns:
        str: 写入的日志行
    """
    _ensure_header()

    timestamp = _now()
    # 截断过长详情
    detail_clean = str(detail).replace("|", "/").replace("\n", " ")[:120]
    line = f"| {timestamp} | {agent} | {action} | {status} | {detail_clean} |\n"

    with _LOCK:
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)

    return line.strip()


def get_recent(status_filter=None, limit=20):
    """获取最近的日志条目

    Args:
        status_filter: 可选状态筛选，如 "FAILED", "RUNNING"
        limit: 最大返回条数

    Returns:
        list[dict]: 日志条目列表
    """
    if not os.path.exists(_LOG_PATH):
        return []

    entries = []
    with open(_LOG_PATH, "r", encoding="utf-8") as f:
        in_table = False
        for line in f:
            line = line.strip()
            if line.startswith("|") and "Agent" not in line and "---" not in line:
                parts = [p.strip() for p in line.split("|")[1:-1]]
                if len(parts) >= 5:
                    entry = {
                        "time": parts[0],
                        "agent": parts[1],
                        "action": parts[2],
                        "status": parts[3],
                        "detail": parts[4],
                    }
                    if status_filter and entry["status"] != status_filter:
                        continue
                    entries.append(entry)

    return entries[-limit:]


def tail_log(n=10):
    """返回最近 n 条日志（人类可读格式）

    Args:
        n: 返回条数

    Returns:
        str: 格式化的最近日志
    """
    entries = get_recent(limit=n)
    if not entries:
        return "(暂无日志)"

    lines = ["| 时间 | Agent | 操作 | 状态 | 详情 |",
             "|------|-------|------|------|------|"]
    for e in entries:
        lines.append(f"| {e['time']} | {e['agent']} | {e['action']} | {e['status']} | {e['detail']} |")
    return "\n".join(lines)


def clear_log():
    """清空日志文件并重建表头"""
    with _LOCK:
        with open(_LOG_PATH, "w", encoding="utf-8") as f:
            f.write(HEADER)
    return {"status": "cleared", "path": _LOG_PATH}


def log_path():
    """返回日志文件的完整路径"""
    return _LOG_PATH


# ── 命令行 tail -f 模式 ──────────────────────────────────────


def _watch_mode(interval=2):
    """tail -f 风格的实时日志监控"""
    print(f"Watching {_LOG_PATH} (Ctrl+C to stop)...")
    print()

    last_size = 0
    try:
        while True:
            if os.path.exists(_LOG_PATH):
                size = os.path.getsize(_LOG_PATH)
                if size > last_size:
                    with open(_LOG_PATH, "r", encoding="utf-8") as f:
                        f.seek(last_size)
                        new_lines = f.read()
                        if new_lines.strip():
                            sys.stdout.write(new_lines)
                            sys.stdout.flush()
                    last_size = size
            else:
                print("(等待日志文件创建...)")
                _ensure_header()
                last_size = 0

            import time
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n停止监控。")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "watch":
        interval = float(sys.argv[2]) if len(sys.argv) > 2 else 2
        _watch_mode(interval)
    elif len(sys.argv) > 1 and sys.argv[1] == "clear":
        print(clear_log())
    elif len(sys.argv) > 1 and sys.argv[1] == "tail":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        print(tail_log(n))
    else:
        # 交互模式：写一条测试日志
        log_action("Hermes", "test", "agent_log.py 模块加载测试", "OK")
        print(f"日志文件: {_LOG_PATH}")
        print(f"最近 5 条:")
        print(tail_log(5))
