"""
不死鸟 - 自愈执行器模块
各组件恢复逻辑，按配置路由
"""

import subprocess
import time


def heal_cdp():
    """重启CDP Chrome：调用 cdp_manager.py launch"""
    try:
        result = subprocess.run(
            ["python", "F:\\AI Agent\\framework\\scripts\\cdp_manager.py", "launch"],
            capture_output=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        output = result.stdout.decode("utf-8", errors="replace")
        error = result.stderr.decode("utf-8", errors="replace")
        success = result.returncode == 0
        return {
            "success": success,
            "output": output.strip() or error.strip(),
            "return_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Timeout (30s)", "return_code": -1}
    except Exception as e:
        return {"success": False, "output": str(e), "return_code": -1}


def heal_pm2(pm2_name):
    """通过PM2重启服务"""
    try:
        result = subprocess.run(
            ["npx", "pm2", "restart", pm2_name],
            capture_output=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        output = result.stdout.decode("utf-8", errors="replace")
        error = result.stderr.decode("utf-8", errors="replace")
        success = result.returncode == 0
        return {
            "success": success,
            "output": output.strip() or error.strip(),
            "return_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Timeout (30s)", "return_code": -1}
    except Exception as e:
        return {"success": False, "output": str(e), "return_code": -1}


def heal(component_name, svc_config):
    """路由到对应healer。
    返回 dict {success, output}
    """
    heal_type = svc_config.get("heal_type", "")
    if heal_type == "cdp_launch":
        result = heal_cdp()
    elif heal_type == "pm2_restart":
        pm2_name = svc_config.get("pm2_name", component_name)
        result = heal_pm2(pm2_name)
    else:
        result = {"success": False, "output": f"Unknown heal_type: {heal_type}"}
    return result


if __name__ == "__main__":
    import json
    print("=== Healers Self-Test ===")

    # Dry-run: just print what we would do
    test_configs = [
        ("chrome-cdp", {"heal_type": "cdp_launch"}),
        ("openclaw-gateway", {"heal_type": "pm2_restart", "pm2_name": "openclaw-gateway"}),
    ]
    for name, cfg in test_configs:
        print(f"  {name}: heal_type={cfg['heal_type']}")

    print("(not executing heal in self-test mode)")
    print("=== Done ===")
