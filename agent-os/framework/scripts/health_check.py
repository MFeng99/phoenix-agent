"""框架健康检查 — 检查 Orchestrator+Executor 所有关键服务端口

用法:
    python scripts/health_check.py              # 完整检查，表格输出
    python scripts/health_check.py --json       # JSON 格式输出
    python scripts/health_check.py --watch 30   # 每30秒循环检查
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone

import urllib.request
import urllib.error


SERVICES = {
    "Qdrant": {
        "port": 6333,
        "url": "http://127.0.0.1:6333/healthz",
        "role": "向量知识库",
        "required": True,
    },
    "Executor": {
        "port": 18789,
        "url": "http://127.0.0.1:18789/",
        "role": "执行引擎网关",
        "required": True,
    },
    "Orchestrator WebUI": {
        "port": 8648,
        "url": "http://127.0.0.1:8648/",
        "role": "主控推理面板",
        "required": True,
    },
    "Chrome CDP": {
        "port": 9333,
        "url": "http://127.0.0.1:9333/json/version",
        "role": "浏览器自动化",
        "required": False,
    },
}


def check_service(name, info):
    """检查单个服务是否可达

    Args:
        name: 服务名称
        info: 服务配置 dict（包含 url, port, role, required）

    Returns:
        dict: {"name": str, "port": int, "role": str, "status": str, "latency_ms": float, "detail": str}
    """
    result = {
        "name": name,
        "port": info["port"],
        "role": info["role"],
        "required": info["required"],
        "status": "UNKNOWN",
        "latency_ms": 0,
        "detail": "",
    }

    start = time.perf_counter()
    try:
        req = urllib.request.Request(info["url"])
        resp = urllib.request.urlopen(req, timeout=5)
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
        result["status"] = "UP" if resp.status < 400 else "DOWN"
        result["detail"] = f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
        # HTTP 错误但端口可达
        result["status"] = "UP"
        result["detail"] = f"HTTP {e.code} (端口可达)"
    except (urllib.error.URLError, ConnectionRefusedError, OSError) as e:
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
        result["status"] = "DOWN"
        result["detail"] = _error_summary(e)
    except Exception as e:
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)
        result["status"] = "DOWN"
        result["detail"] = str(e)[:60]

    return result


def _error_summary(e):
    """提取错误摘要"""
    msg = str(e)
    if "Connection refused" in msg or "10061" in msg or "WinError 10061" in msg:
        return "连接被拒绝 (端口未监听)"
    if "timed out" in msg.lower():
        return "连接超时"
    if "getaddrinfo" in msg.lower():
        return "DNS 解析失败"
    return msg[:60]


def check_all():
    """检查所有服务

    Returns:
        list[dict]: 各服务状态列表
    """
    return [check_service(name, info) for name, info in SERVICES.items()]


def print_table(results):
    """打印表格格式报告"""
    sep = "+" + "-" * 16 + "+" + "-" * 8 + "+" + "-" * 12 + "+" + "-" * 6 + "+" + "-" * 18 + "+" + "-" * 26 + "+"
    header = f"| {'服务':<14} | {'端口':<6} | {'角色':<10} | {'必需':<4} | {'状态':<16} | {'详情':<24} |"

    print(sep)
    print(header)
    print(sep)

    all_up = True
    for r in results:
        status_display = r["status"]
        if status_display == "UP":
            status_display = f"\033[92m{status_display:<14}\033[0m"
        elif status_display == "DOWN":
            status_display = f"\033[91m{status_display:<14}\033[0m"
            if r["required"]:
                all_up = False
        else:
            status_display = f"\033[93m{status_display:<14}\033[0m"

        required_display = "是" if r["required"] else "否"
        detail_display = r["detail"][:22] if r["detail"] else ""
        latency_display = f"{r['latency_ms']}ms" if r["latency_ms"] > 0 else ""

        display = f"{detail_display} ({latency_display})" if latency_display else detail_display
        print(f"| {r['name']:<14} | {r['port']:<6} | {r['role']:<10} | {required_display:<4} | {status_display:<22} | {display:<24} |")

    print(sep)

    if all_up:
        print("\n\033[92m全部必需服务正常运行。\033[0m")
    else:
        print("\n\033[91m有必需服务未运行，请检查。\033[0m")

    # 延迟汇总
    ups = [r for r in results if r["status"] == "UP"]
    if ups:
        avg_latency = sum(r["latency_ms"] for r in ups) / len(ups)
        print(f"平均延迟: {avg_latency:.1f}ms ({len(ups)}/{len(results)} 服务可达)")


def main():
    parser = argparse.ArgumentParser(description="Orchestrator+Executor 框架健康检查")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--watch", type=int, metavar="N", help="每 N 秒循环检查")
    parser.add_argument("--service", type=str, help="仅检查指定服务（Qdrant/Executor/WebUI/CDP）")
    args = parser.parse_args()

    if args.watch:
        interval = args.watch
        print(f"循环健康检查 (间隔 {interval}s)，Ctrl+C 停止...")
        print()
        try:
            while True:
                results = check_all()
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                print(f"\n[{timestamp}]")
                print_table(results)
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n停止监控。")
        return

    if args.service:
        name_map = {"qdrant": "Qdrant", "executor": "Executor", "webui": "Orchestrator WebUI", "cdp": "Chrome CDP"}
        svc_name = name_map.get(args.service.lower(), args.service)
        info = SERVICES.get(svc_name)
        if not info:
            print(f"未知服务: {args.service}。可用: {', '.join(SERVICES.keys())}")
            sys.exit(1)
        result = check_service(svc_name, info)
        results = [result]
    else:
        results = check_all()

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print("=" * 70)
        print("  Orchestrator + Executor 框架健康检查")
        print("=" * 70)
        print_table(results)

    # 退出码
    any_required_down = any(r["status"] != "UP" and r["required"] for r in results)
    sys.exit(1 if any_required_down else 0)


if __name__ == "__main__":
    main()
