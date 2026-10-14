"""Freelance Worker v1.0 — 自由职业平台消息监控 Worker

使用 core.freelance_agent.FreelanceAgent 检查 Upwork + Fiverr 消息，
检测变化并通知飞书。适合 PM2 后台长期运行。

用法:
    python scripts/freelance_worker.py                    # 默认每300秒检查
    python scripts/freelance_worker.py --interval 60      # 每60秒检查
    python scripts/freelance_worker.py --dry-run          # 只检查一次，不循环
    python scripts/freelance_worker.py --notify feishu    # 新消息发飞书通知
    python scripts/freelance_worker.py --notify none      # 不发送通知（默认）
"""

import sys
import os
import argparse
import time
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.agent_log import log_action
from core.freelance_agent import FreelanceAgent


# ── Feishu 通知 ───────────────────────────────────────────────
# 从环境变量读取，用户需在 .env 中设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
USER_OPEN_ID = os.environ.get("FEISHU_USER_OPEN_ID", "")


def notify_feishu(platform_name: str, detail: str = "") -> bool:
    """通过飞书 API 发送新消息通知给用户

    Args:
        platform_name: 平台名，如 "Upwork" / "Fiverr"
        detail: 额外详情（如消息长度）

    Returns:
        bool: 是否发送成功
    """
    import urllib.request

    text = f"[Freelance Worker] {platform_name} 新消息！{detail}"

    try:
        # 1. 获取 tenant access token
        token_req = urllib.request.Request(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            data=json.dumps({
                "app_id": FEISHU_APP_ID,
                "app_secret": FEISHU_APP_SECRET,
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(token_req, timeout=10) as resp:
            token_data = json.loads(resp.read().decode())
            token = token_data.get("tenant_access_token", "")

        if not token:
            print(f"    ❌ Failed to get Feishu token")
            return False

        # 2. 发送消息
        msg_body = json.dumps({
            "receive_id": USER_OPEN_ID,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        }).encode()

        msg_req = urllib.request.Request(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
            data=msg_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        with urllib.request.urlopen(msg_req, timeout=10) as resp:
            msg_result = json.loads(resp.read().decode())
            return msg_result.get("code") == 0

    except Exception as e:
        print(f"    ⚠️ Feishu notify error: {e}")
        return False


# ── Worker 核心 ────────────────────────────────────────────────


def run_once(agent: FreelanceAgent, notify_mode: str) -> bool:
    """执行一次全平台检查

    Args:
        agent: FreelanceAgent 实例
        notify_mode: "feishu" 或 "none"

    Returns:
        bool: 是否有新消息
    """
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] Checking all freelance platforms...")

    result = agent.check_all()
    platforms = result.get("platforms", {})
    has_new = result.get("has_new", False)

    for key, info in platforms.items():
        name = info.get("name", key)
        total_length = info.get("total_length", 0)
        is_new = info.get("is_new", False)

        if info.get("success"):
            status_icon = "🔔" if is_new else "✅"
            new_tag = " NEW" if is_new else ""
            print(f"  {status_icon} {name}: {total_length} chars{new_tag}")
        else:
            print(f"  ❌ {name}: {info.get('error', 'unknown error')}")

        log_action(
            "FreelanceWorker",
            f"{key}.check",
            f"platform={name} len={total_length} is_new={is_new}",
            "NOTIFY" if is_new else "OK",
        )

    # ── 新消息通知 ─────────────────────────────────────────
    if has_new and notify_mode == "feishu":
        print(f"  📣 Sending Feishu notifications...")
        for key, info in platforms.items():
            if info.get("is_new") and info.get("success"):
                name = info.get("name", key)
                detail = f"(len={info.get('total_length', 0)})"
                ok = notify_feishu(name, detail)
                status = "OK" if ok else "FAILED"
                print(f"    {'✅' if ok else '❌'} {name}: {status}")
                log_action(
                    "FreelanceWorker",
                    "notify.feishu",
                    f"platform={name} status={status}",
                    status,
                )

    return has_new


# ── 入口 ──────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Freelance Worker — 自由职业平台消息监控")
    parser.add_argument("--interval", type=int, default=300,
                        help="检查间隔（秒），默认300")
    parser.add_argument("--dry-run", action="store_true",
                        help="只检查一次，不循环")
    parser.add_argument("--hunt", action="store_true",
                        help="启用主动找活（周期扫描新工作机会）")
    parser.add_argument("--hunt-interval", type=int, default=1800,
                        help="找活间隔（秒），默认1800（30分钟）")
    parser.add_argument("--hunt-keywords", type=str, default="web scraping,python,AI automation,data extraction",
                        help="找活关键词，逗号分隔")
    parser.add_argument("--notify", choices=["feishu", "none"], default="none",
                        help="新消息时是否通知（默认 none）")
    args = parser.parse_args()

    STATE_FILE = os.path.join(
        os.path.expanduser("~"), "Desktop", "agent-os-logs", "freelance-state.json"
    )

    print(r"""
  ╔═══════════════════════════════════════════╗
  ║   Freelance Worker v1.0                   ║
  ║   Upwork · Fiverr 统一消息监控            ║
  ╚═══════════════════════════════════════════╝
    """)
    print(f"  Interval: {args.interval}s")
    print(f"  Notify:   {args.notify}")
    print(f"  Hunt:     {'ON (' + str(args.hunt_interval) + 's)' if args.hunt else 'OFF'}")
    print(f"  State:    {STATE_FILE}")
    print(f"  {'─' * 45}")

    agent = FreelanceAgent()

    log_action(
        "FreelanceWorker",
        "worker.start",
        f"interval={args.interval}s notify={args.notify}",
        "RUNNING",
    )

    # ── Dry-run: 只检查一次 ──────────────────────────────────
    if args.dry_run:
        print(f"\n  🏃 Dry run - checking once...\n")
        has_new = run_once(agent, args.notify)
        print(f"\n  {'─' * 45}")
        print(f"  Result: {'🔔 New message' if has_new else '✅ No change'}")
        log_action(
            "FreelanceWorker",
            "worker.dry_run",
            f"result={'new_msg' if has_new else 'no_change'}",
            "OK",
        )
        return

    # ── 循环模式 ────────────────────────────────────────────
    print(f"\n  🔄 Running... press Ctrl+C to stop\n")

    try:
        last_hunt = 0
        while True:
            try:
                run_once(agent, args.notify)

                # ── 主动找活 ──────────────────────────────
                if args.hunt:
                    now = time.time()
                    if now - last_hunt >= args.hunt_interval:
                        keywords = [k.strip() for k in args.hunt_keywords.split(",")]
                        print(f"  🔍 Hunting for jobs: {', '.join(keywords)}")
                        try:
                            hunt_result = agent.scan_opportunities(keywords=keywords, limit=10)
                            total = hunt_result.get("total", 0)
                            upwork_ok = hunt_result.get("upwork", {}).get("success", False)
                            if total > 0:
                                # 打印前3个
                                jobs = hunt_result.get("upwork", {}).get("jobs", [])
                                for i, j in enumerate(jobs[:3]):
                                    title = j.get("title", "?")
                                    budget = j.get("budget", "")
                                    print(f"    #{i + 1} {title[:80]}")
                                    if budget:
                                        print(f"       💰 {budget}")
                            print(f"    {'✅' if upwork_ok else '⚠️'} Upwork: {total} jobs found")
                            log_action("FreelanceWorker", "hunt.run",
                                       f"total={total} keywords={' '.join(keywords)[:60]}",
                                       "OK" if total > 0 else "NOT_FOUND")
                        except Exception as e:
                            print(f"    ❌ Hunt error: {e}")
                            log_action("FreelanceWorker", "hunt.run", str(e)[:100], "FAILED")
                        last_hunt = now

            except Exception as e:
                print(f"  ❌ Error: {e}")
                log_action("FreelanceWorker", "worker.error", str(e)[:100], "FAILED")

            print(f"  ⌛ Next check in {args.interval}s...\n")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(f"\n  👋 Freelance Worker stopped")
        log_action("FreelanceWorker", "worker.stop", "用户手动停止", "OK")


if __name__ == "__main__":
    main()
