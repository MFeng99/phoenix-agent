"""Framework v5.0 — 一键启动入口

用法:
    python run.py               # 启动框架服务 + 健康检查
    python run.py --service-only  # 只启动框架服务
    python run.py --check        # 只检查服务健康状态
"""

import sys
import os
import time
import subprocess
import signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BANNER = r"""
╔══════════════════════════════════════════════╗
║     Framework v5.0 Service                   ║
║     Orchestrator + Executor 双Agent 框架服务化      ║
║     Port: 18888                              ║
╚══════════════════════════════════════════════╝
"""

SERVICES = {
    "Qdrant": {"port": 6333, "url": "http://127.0.0.1:6333/healthz"},
    "Executor": {"port": 18789, "url": "http://127.0.0.1:18789/"},
    "WebUI": {"port": 8648, "url": "http://127.0.0.1:8648/"},
    "CDP": {"port": 9333, "url": "http://127.0.0.1:9333/json/version"},
}


def check_services(verbose=True):
    """检查所有底层服务状态"""
    import urllib.request
    import urllib.error

    results = {}
    all_ok = True

    for name, info in SERVICES.items():
        try:
            req = urllib.request.Request(info["url"], method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                results[name] = ("UP", resp.status)
        except Exception as e:
            results[name] = ("DOWN", str(e)[:50])
            all_ok = False

    if verbose:
        print(f"\n{'='*50}")
        print("  服务健康检查")
        print(f"{'='*50}")
        for name, (status, detail) in results.items():
            icon = "✅" if status == "UP" else "❌"
            port = SERVICES[name]["port"]
            print(f"  {icon} {name:<12} :{port}  {status:<6} {detail}")
        print(f"{'='*50}")
        print(f"  总体: {'✅ ALL UP' if all_ok else '❌ 部分服务离线'}")
        print(f"{'='*50}")

    return all_ok, results


def start_framework_service():
    """启动框架 FastAPI 服务"""
    log_path = os.path.join(os.path.expanduser("~"), "Desktop", "framework_log.md")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    print("\n  启动 Framework Service...")

    code = [
        sys.executable, "-c",
        "import sys;"
        "for k in list(sys.modules.keys()):"
        "  if 'embedding' in k or 'sentence_transformers' in k: del sys.modules[k];"
        "import uvicorn; import framework_service;"
        "uvicorn.run(framework_service.app, host='0.0.0.0', port=18888, log_level='info')"
    ]
    proc = subprocess.Popen(code)

    # 等待服务就绪
    wait_seconds = 15
    for i in range(wait_seconds):
        try:
            import urllib.request
            req = urllib.request.Request("http://127.0.0.1:18888/health")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    print(f"  ✅ Framework Service 启动成功! (pid={proc.pid})")
                    print(f"\n  {'='*50}")
                    print(f"  端点列表:")
                    print(f"  🌐 Health:      http://127.0.0.1:18888/health")
                    print(f"  ⚡ Execute:     POST http://127.0.0.1:18888/execute")
                    print(f"  📖 Knowledge:   POST http://127.0.0.1:18888/knowledge/search")
                    print(f"  📝 Knowledge:   POST http://127.0.0.1:18888/knowledge/store")
                    print(f"  📋 Tasks:       GET  http://127.0.0.1:18888/tasks/{{task_id}}")
                    print(f"  {'='*50}")
                    print(f"  日志文件: {log_path}")
                    print(f"  {'='*50}\n")
                    return proc
        except Exception:
            time.sleep(1)

    print("  ❌ Framework Service 启动超时!")
    proc.kill()
    return None


def main():
    print(BANNER)

    args = sys.argv[1:]
    service_only = "--service-only" in args
    check_only = "--check" in args
    with_worker = "--worker" in args or "--all" in args

    if check_only:
        check_services()
        return

    # 检查底层服务
    all_ok, _ = check_services()

    if service_only:
        start_framework_service()
        print("\n  Ctrl+C 停止服务\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n  服务已停止")
        return

    # 完整模式：检查 + 启动
    if not all_ok:
        print("\n  ⚠️  部分服务离线，框架服务仍可启动但功能受限\n")

    proc = start_framework_service()

    # 启动数字打工人（可选）
    worker_proc = None
    if with_worker and proc:
        print("\n  启动 Freelance Worker...")
        worker_script = os.path.join(
            os.path.dirname(__file__), "scripts", "freelance_worker.py"
        )
        worker_proc = subprocess.Popen(
            [sys.executable, worker_script, "--interval", "300", "--notify", "feishu"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        print(f"  ✅ Digital Worker 已启动 (pid={worker_proc.pid})\n")

    if proc:
        print("  后台服务运行中 (pid=%d)" % proc.pid)
        print("  按 Ctrl+C 停止所有服务\n")
        try:
            # 保持进程存活
            proc.wait()
        except KeyboardInterrupt:
            print("\n  正在停止服务...")
            proc.terminate()
            proc.wait()
            print("  ✅ 服务已停止")
    else:
        print("  ❌ 启动失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
