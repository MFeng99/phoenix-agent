"""
不死鸟系统 (Phoenix) — 业务级自愈守护主程序
PM2管理，Python stdlib only

用法:
    python phoenix.py               # 启动守护循环
    python phoenix.py --rollback     # 回滚到上一版本
    python phoenix.py --rollback v1  # 回滚到指定版本
    python phoenix.py --versions     # 列出所有版本
    python phoenix.py --check-once   # 单次检查（不进入循环）
"""

import json
import os
import shutil
import sys
import time
import datetime
import traceback

# ── 路径 ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
REGISTRY_PATH = os.path.join(BASE_DIR, "registry.json")
VERSIONS_DIR = os.path.join(BASE_DIR, "versions")
MANIFEST_PATH = os.path.join(VERSIONS_DIR, "manifest.json")

# 默认值（会被 config.json 覆盖）
CHECK_INTERVAL = 30
DEEP_CHECK_INTERVAL = 300
COOLDOWN_SECONDS = 300
MAX_FAILURES = 2
FEISHU_WEBHOOK_URL = ""

# 日志路径默认值
_LOG_DIR_DEFAULT = os.path.join(os.path.expanduser("~"), "Desktop", "hermes-logs")
_LOG_FILE_DEFAULT = os.path.join(_LOG_DIR_DEFAULT, "phoenix.log")

# ── 运行时状态 ───────────────────────────────────────
_cooldowns = {}       # {component: expiry_timestamp}
_failure_counts = {}  # {component: count}
_last_deep_check = 0


# ── 模块导入 ──────────────────────────────────────────
def _import_modules():
    """延迟导入，避免循环引用"""
    global probes, healers, alert
    import probes as _p
    import healers as _h
    import alert as _a
    probes = _p
    healers = _h
    alert = _a


# ── 配置 ──────────────────────────────────────────────
def load_config():
    """加载配置并展开 ~ 路径"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # 展开路径中的 ~
    for key in ("log_dir", "log_file"):
        if key in cfg and isinstance(cfg[key], str) and cfg[key].startswith("~"):
            cfg[key] = os.path.expanduser(cfg[key])
    return cfg


# ── 注册表 ────────────────────────────────────────────
def load_registry():
    """加载运行状态注册表"""
    if os.path.exists(REGISTRY_PATH):
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"status": {}, "history": []}


def save_registry(registry):
    """保存运行状态注册表"""
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)


def _get_log_paths():
    """从配置获取日志路径，带默认回退"""
    try:
        cfg = load_config()
        log_dir = cfg.get("log_dir", _LOG_DIR_DEFAULT)
        log_file = cfg.get("log_file", _LOG_FILE_DEFAULT)
        return log_dir, log_file
    except Exception:
        return _LOG_DIR_DEFAULT, _LOG_FILE_DEFAULT


# ── 审计日志 ──────────────────────────────────────────
def log_audit(entry):
    """记录审计日志（JSON Lines）"""
    if "ts" not in entry:
        entry["ts"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    log_dir, log_file = _get_log_paths()
    os.makedirs(log_dir, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    # 简单日志轮转：>10000行时截断
    _rotate_log_if_needed(log_file)


def _rotate_log_if_needed(log_file):
    """日志轮转：超过10000行保留最后5000行"""
    try:
        if os.path.getsize(log_file) > 2 * 1024 * 1024:  # 2MB
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) > 10000:
                with open(log_file, "w", encoding="utf-8") as f:
                    f.writelines(lines[-5000:])
    except (OSError, IOError):
        pass


# ── 自愈逻辑 ──────────────────────────────────────────
def is_in_cooldown(component):
    """检查是否在冷静期内"""
    now = time.time()
    if component in _cooldowns:
        if now < _cooldowns[component]:
            return True
        del _cooldowns[component]
    return False


def set_cooldown(component):
    """设置冷静期"""
    _cooldowns[component] = time.time() + COOLDOWN_SECONDS


def is_circuit_broken(component):
    """检查熔断器是否触发"""
    return _failure_counts.get(component, 0) >= MAX_FAILURES


def increment_failure(component):
    """增加失败计数"""
    _failure_counts[component] = _failure_counts.get(component, 0) + 1


def reset_failures(component):
    """重置失败计数"""
    _failure_counts[component] = 0


# ── 版本回滚 ─────────────────────────────────────────
def init_version_manifest():
    """初始化版本清单"""
    if not os.path.exists(MANIFEST_PATH):
        os.makedirs(VERSIONS_DIR, exist_ok=True)
        manifest = [{"version": "v1", "date": time.strftime("%Y-%m-%d"), "reason": "initial"}]
        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        return manifest
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_version_manifest(manifest):
    """保存版本清单"""
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def backup_current_version(reason="auto"):
    """备份当前 phoenix 文件为新版本"""
    manifest = init_version_manifest()
    next_num = len(manifest) + 1
    version_name = f"v{next_num}"
    version_dir = os.path.join(VERSIONS_DIR, version_name)

    os.makedirs(version_dir, exist_ok=True)

    # 备份所有关键文件
    files_to_backup = ["config.json", "registry.json"]
    module_files = ["phoenix.py"]
    for fname in ["probes.py", "healers.py", "alert.py"]:
        module_files.append(fname)

    for fname in files_to_backup + module_files:
        src = os.path.join(BASE_DIR, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(version_dir, fname))

    manifest.append({
        "version": version_name,
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "reason": reason,
    })
    save_version_manifest(manifest)
    print(f"[Phoenix] Backed up to {version_name}")
    return version_name


def rollback(version_name=None):
    """回滚到指定版本"""
    manifest = init_version_manifest()

    if version_name is None:
        # 回滚到上一个版本
        if len(manifest) < 2:
            print("[Phoenix] No previous version to rollback to")
            return False
        version_name = manifest[-2]["version"]
    else:
        if not any(v["version"] == version_name for v in manifest):
            print(f"[Phoenix] Version {version_name} not found in manifest")
            list_versions()
            return False

    version_dir = os.path.join(VERSIONS_DIR, version_name)
    if not os.path.exists(version_dir):
        print(f"[Phoenix] Version directory not found: {version_dir}")
        return False

    print(f"[Phoenix] Rolling back to {version_name}...")

    # 先备份当前版本
    backup_current_version(reason=f"pre-rollback-to-{version_name}")

    # 恢复文件
    restored = []
    for fname in os.listdir(version_dir):
        if fname.endswith((".py", ".json")):
            src = os.path.join(version_dir, fname)
            dst = os.path.join(BASE_DIR, fname)
            shutil.copy2(src, dst)
            restored.append(fname)

    print(f"[Phoenix] Restored: {', '.join(restored)}")
    print(f"[Phoenix] Rollback to {version_name} complete!")

    # 重载配置
    global CHECK_INTERVAL, COOLDOWN_SECONDS, MAX_FAILURES, FEISHU_WEBHOOK_URL
    config = load_config()
    CHECK_INTERVAL = config.get("check_interval", 30)
    COOLDOWN_SECONDS = config.get("cooldown_seconds", 300)
    MAX_FAILURES = config.get("max_failures", 2)
    FEISHU_WEBHOOK_URL = config.get("feishu_webhook_url", "")

    return True


def list_versions():
    """列出所有版本"""
    manifest = init_version_manifest()
    print("=== Phoenix Versions ===")
    for v in manifest:
        print(f"  {v['version']}: {v['date']} ({v['reason']})")
    print("=======================")
    return manifest


def check_and_auto_backup():
    """启动时检查：如果当前文件与versions不同，自动备份"""
    manifest = init_version_manifest()
    if not manifest:
        backup_current_version("initial")
        return

    # 检查 current -> versions/vN 的指向
    current_version = manifest[-1]["version"]
    version_dir = os.path.join(VERSIONS_DIR, current_version)

    if not os.path.exists(os.path.join(version_dir, "phoenix.py")):
        # 版本目录不完整，备份当前状态
        backup_current_version("recover-incomplete-version")


# ── 飞书告警包装 ──────────────────────────────────────
def send_alert(level, component, message, action_taken=None):
    """发送飞书告警（带限频）"""
    result = alert.send_alert(FEISHU_WEBHOOK_URL, level, component, message, action_taken)
    if result.get("sent"):
        log_audit({
            "level": "ALERT",
            "component": component,
            "alert_level": level,
            "message": message,
            "action_taken": action_taken or "",
        })
    return result


# ── 主循环 ────────────────────────────────────────────
def check_once(config):
    """单次检查所有服务"""
    global _last_deep_check
    now = time.time()
    do_deep = (now - _last_deep_check) >= DEEP_CHECK_INTERVAL
    if do_deep:
        _last_deep_check = now

    registry = load_registry()
    results = {}

    for svc_name, svc_config in config["services"].items():
        try:
            if do_deep:
                status = probes.deep_check(svc_name, svc_config)
            else:
                status = probes.quick_check(svc_name, svc_config)

            results[svc_name] = status

            # 更新注册表
            prev = registry["status"].get(svc_name, {})
            registry["status"][svc_name] = {
                "alive": status["alive"],
                "last_check": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "latency": status.get("latency", -1),
                "changed": prev.get("alive") != status["alive"] if prev else False,
            }

            # 审计日志（每轮都记）
            log_audit({
                "level": "INFO" if status["alive"] else "WARN",
                "component": svc_name,
                "status": "alive" if status["alive"] else "dead",
                "port_alive": status.get("port_alive", False),
                "pid_alive": status.get("pid_alive", False),
                "latency_ms": status.get("latency", -1),
            })

            # ── 自愈逻辑 ──
            if not status["alive"]:
                if is_in_cooldown(svc_name):
                    log_audit({"level": "DEBUG", "component": svc_name, "status": "cooldown"})
                    continue

                if is_circuit_broken(svc_name):
                    msg = f"{svc_name} 自愈失败{MAX_FAILURES}次，熔断器触发，需人工介入"
                    send_alert("CRITICAL", svc_name, msg, "熔断，不自愈")
                    log_audit({"level": "CRITICAL", "component": svc_name, "status": "circuit_broken"})
                    continue

                print(f"[Phoenix] {svc_name} is dead. Attempting heal...")
                result = healers.heal(svc_name, svc_config)
                set_cooldown(svc_name)

                if result["success"]:
                    reset_failures(svc_name)
                    send_alert("WARN", svc_name, f"服务异常已自愈", f"重启成功: {result['output'][:100]}")
                    log_audit({
                        "level": "HEAL", "component": svc_name,
                        "action": "restart", "result": "ok", "output": result["output"],
                    })
                    print(f"[Phoenix] {svc_name} heal OK")
                else:
                    increment_failure(svc_name)
                    send_alert("ERROR", svc_name, f"自愈失败", f"输出: {result['output'][:100]}")
                    log_audit({
                        "level": "HEAL_FAIL", "component": svc_name,
                        "action": "restart", "result": "fail", "output": result["output"],
                    })
                    print(f"[Phoenix] {svc_name} heal FAILED: {result['output']}")

            else:
                # 如果这次活着的，重置失败计数
                if status["alive"] and _failure_counts.get(svc_name, 0) > 0:
                    reset_failures(svc_name)

        except Exception as e:
            log_audit({"level": "ERROR", "component": svc_name, "status": "check_error", "error": str(e)})
            print(f"[Phoenix] Error checking {svc_name}: {e}")

    save_registry(registry)
    return results


def main_loop(config):
    """主守护循环"""
    global CHECK_INTERVAL, COOLDOWN_SECONDS, MAX_FAILURES, FEISHU_WEBHOOK_URL

    CHECK_INTERVAL = config.get("check_interval", 30)
    COOLDOWN_SECONDS = config.get("cooldown_seconds", 300)
    MAX_FAILURES = config.get("max_failures", 2)
    FEISHU_WEBHOOK_URL = config.get("feishu_webhook_url", "")

    # 版本检查（启动时自动备份）
    check_and_auto_backup()

    # 发送启动通知
    log_audit({"level": "BOOT", "component": "phoenix", "status": "started"})
    print(f"[Phoenix] Started. Check every {CHECK_INTERVAL}s, deep every {DEEP_CHECK_INTERVAL}s")
    print(f"[Phoenix] Cooldown: {COOLDOWN_SECONDS}s, Max failures: {MAX_FAILURES}")
    print(f"[Phoenix] Watching: {', '.join(config['services'].keys())}")

    error_count = 0
    while True:
        try:
            check_once(config)
            error_count = 0
        except KeyboardInterrupt:
            print("\n[Phoenix] Stopped by user")
            log_audit({"level": "BOOT", "component": "phoenix", "status": "stopped"})
            break
        except Exception as e:
            error_count += 1
            log_audit({"level": "ERROR", "component": "phoenix", "status": "loop_error", "error": str(e) + "\n" + traceback.format_exc()})
            print(f"[Phoenix] Loop error ({error_count}): {e}")
            if error_count > 5:
                print("[Phoenix] Too many errors, stopping")
                break

        time.sleep(CHECK_INTERVAL)


# ── 命令行入口 ────────────────────────────────────────
def main():
    _import_modules()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "--rollback":
            version = sys.argv[2] if len(sys.argv) > 2 else None
            rollback(version)
            return
        elif cmd == "--versions":
            list_versions()
            return
        elif cmd == "--check-once":
            cfg = load_config()
            results = check_once(cfg)
            print(json.dumps(results, indent=2, ensure_ascii=False))
            return
        elif cmd == "--help" or cmd == "-h":
            print(__doc__)
            return
        else:
            print(f"Unknown command: {cmd}")
            print(__doc__)
            return

    # 正常启动
    cfg = load_config()
    main_loop(cfg)


if __name__ == "__main__":
    main()
