"""
不死鸟 - 健康探针模块
双重确认：端口不通 + PID不存在 才算服务挂了
"""

import socket
import subprocess
import urllib.request
import urllib.error
import time
import json


def check_port(port, timeout=3):
    """检查端口是否可连接，返回 (bool, float) -> (是否通, 延迟ms)"""
    start = time.time()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        result = sock.connect_ex(("127.0.0.1", port))
        elapsed = (time.time() - start) * 1000
        return result == 0, round(elapsed, 1)
    finally:
        sock.close()


def check_http(url, timeout=3):
    """HTTP健康检查，返回 dict {alive, latency, status_code, error}"""
    start = time.time()
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = (time.time() - start) * 1000
            return {
                "alive": resp.status < 500,
                "latency": round(elapsed, 1),
                "status_code": resp.status,
                "error": None,
            }
    except urllib.error.HTTPError as e:
        elapsed = (time.time() - start) * 1000
        # 4xx 错误算是活着的（服务在响应）
        return {
            "alive": e.code < 500,
            "latency": round(elapsed, 1),
            "status_code": e.code,
            "error": f"HTTP {e.code}",
        }
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        elapsed = (time.time() - start) * 1000
        return {
            "alive": False,
            "latency": round(elapsed, 1),
            "status_code": None,
            "error": str(e),
        }


def check_pid(process_name):
    """通过tasklist检查进程是否存在。
    双重确认用：直接在Windows上查进程名。
    返回 bool
    """
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/FO", "CSV", "/NH"],
            capture_output=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        # CSV格式: "chrome.exe","12345","Console","1","123,456 K"
        # 有进程返回 ≥1行，无进程返回空
        lines = result.stdout.decode("utf-8", errors="replace").strip().split("\n")
        lines = [l for l in lines if process_name.lower() in l.lower()]
        return len(lines) > 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def check_pid_by_port(port, timeout=5):
    """通过 netstat 查找某个端口对应的 PID。
    用于辅助确认：端口和进程对应关系。
    返回 PID 或 None
    """
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        text = result.stdout.decode("utf-8", errors="replace")
        for line in text.split("\n"):
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                if parts:
                    pid_str = parts[-1]
                    try:
                        return int(pid_str)
                    except ValueError:
                        return None
        return None
    except Exception:
        return None


def check_pid_specific(pid):
    """通过 tasklist 精确验证指定 PID 是否存活。
    返回 bool
    """
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        lines = result.stdout.decode("utf-8", errors="replace").strip().split("\n")
        lines = [l for l in lines if l.strip()]
        return len(lines) > 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def quick_check(service_name, svc_config):
    """快速检查：端口是否通 + 进程是否在。
    精确验证：当端口存活时，优先通过端口查找 PID 并精确验证该 PID，
    避免同进程名多实例导致的误判。
    返回 dict {alive, port_alive, pid_alive, latency}
    """
    port_alive, latency = check_port(svc_config["port"])

    if port_alive:
        pid = check_pid_by_port(svc_config["port"])
        if pid is not None:
            pid_alive = check_pid_specific(pid)
        else:
            # 端口通但拿不到 PID（权限等），回退到进程名匹配
            pid_alive = check_pid(svc_config["process_name"])
    else:
        # 端口不通时用进程名兜底（服务可能刚重启、端口暂未就绪）
        pid_alive = check_pid(svc_config["process_name"])

    return {
        "alive": port_alive and pid_alive,
        "port_alive": port_alive,
        "pid_alive": pid_alive,
        "latency": latency,
        "port": svc_config["port"],
    }


def deep_check(service_name, svc_config):
    """深度检查：快速检查 + HTTP健康检查。
    返回 dict {alive, port_alive, pid_alive, http_alive, latency, status_code, error}
    """
    quick = quick_check(service_name, svc_config)

    http_result = {"alive": False, "latency": None, "status_code": None, "error": "skipped"}
    if quick["port_alive"]:
        url = f"http://127.0.0.1:{svc_config['port']}{svc_config.get('http_path', '/')}"
        http_result = check_http(url)

    alive = quick["port_alive"] or quick["pid_alive"]
    return {
        "alive": alive,
        "port_alive": quick["port_alive"],
        "pid_alive": quick["pid_alive"],
        "http_alive": http_result["alive"],
        "latency": http_result.get("latency") or quick["latency"],
        "status_code": http_result.get("status_code"),
        "http_error": http_result.get("error"),
        "port": svc_config["port"],
    }


if __name__ == "__main__":
    import json
    # Self-test
    print("=== Probes Self-Test ===")
    port, lat = check_port(6333)
    print(f"Qdrant port 6333: alive={port}, latency={lat}ms")

    pid = check_pid("chrome.exe")
    print(f"chrome.exe PID: {pid}")

    test_config = {"port": 6333, "http_path": "/healthz", "process_name": "qdrant.exe"}
    quick = quick_check("qdrant", test_config)
    print(f"Quick check: {json.dumps(quick, indent=2)}")

    deep = deep_check("qdrant", test_config)
    print(f"Deep check: {json.dumps(deep, indent=2)}")
    print("=== Done ===")
