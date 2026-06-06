"""
不死鸟 - 飞书告警模块
发送告警消息到飞书群机器人
"""

import json
import os
import time
import datetime
import urllib.request
import urllib.error


# 告警限频状态（内存，运行时重置）
_alert_cooldowns = {}
_alert_count_today = 0
_alert_day = datetime.date.today()


def _check_rate_limit(webhook_url, level, component):
    """检查告警是否应该发送。
    返回 True = 允许发送
    """
    global _alert_count_today, _alert_day

    today = datetime.date.today()
    if today != _alert_day:
        _alert_count_today = 0
        _alert_day = today

    # CRITICAL级不受限
    if level == "CRITICAL":
        return True

    # 每天上限（直接从phoenix模块取配置，或默认50）
    max_alerts = 50
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from phoenix import registry as _phoenix_registry  # noqa
        max_alerts = getattr(_phoenix_registry, "MAX_ALERTS_PER_DAY", 50)
    except (ImportError, AttributeError):
        pass
    if _alert_count_today >= max_alerts:
        return False

    # 同组件同级别冷却
    key = f"{component}:{level}"
    now = time.time()
    if key in _alert_cooldowns:
        elapsed = now - _alert_cooldowns[key]
        if elapsed < 600:  # 10分钟
            return False

    return True


def _record_alert(level, component):
    """记录告警状态"""
    global _alert_count_today
    _alert_count_today += 1
    key = f"{component}:{level}"
    _alert_cooldowns[key] = time.time()


def build_message(level, component, message, action_taken=None):
    """构建飞书消息卡片。
    返回 dict 格式
    """
    icon_map = {"INFO": "🟢", "WARN": "🟡", "ERROR": "🟠", "CRITICAL": "🔴"}
    icon = icon_map.get(level, "⚪")

    lines = [
        f"{icon} **不死鸟告警**",
        f"级别：{level}",
        f"组件：{component}",
        f"时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"详情：{message}",
    ]
    if action_taken:
        lines.append(f"操作：{action_taken}")
    return {"msg_type": "text", "content": {"text": "\n".join(lines)}}


def send_alert(webhook_url, level, component, message, action_taken=None):
    """发送飞书告警。
    webhook_url = "" 时不发送（仅记录日志）
    返回 dict {sent, reason}
    """
    if not webhook_url:
        try:
            from . import registry
            webhook_url = getattr(registry, "FEISHU_WEBHOOK_URL", "")
        except (ImportError, AttributeError):
            pass

    if not webhook_url:
        return {"sent": False, "reason": "webhook_url not configured"}

    if not _check_rate_limit(webhook_url, level, component):
        return {"sent": False, "reason": "rate limited"}

    payload = build_message(level, component, message, action_taken)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            _record_alert(level, component)
            body = resp.read().decode("utf-8")
            return {"sent": resp.status == 200, "reason": body}
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        return {"sent": False, "reason": str(e)}


if __name__ == "__main__":
    print("=== Alert Self-Test ===")
    msg = build_message("WARN", "chrome-cdp", "连接超时", "已重启")
    print(json.dumps(msg, indent=2, ensure_ascii=False))
    print("(not sending without webhook_url)")
    print("=== Done ===")
