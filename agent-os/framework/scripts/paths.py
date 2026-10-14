"""统一运行期路径解析 —— 所有可写目录的唯一来源。

设计目标
    * 可移植 —— 不再依赖 ~/Desktop 这类平台特有位置（Linux / macOS / CI 上并不存在）
    * 可覆盖 —— 容器、只读安装目录、CI 都可通过环境变量重定向
    * 单点维护 —— 各模块不再各自拼路径

环境变量
    AGENT_OS_DATA_DIR   数据根目录，默认 <framework>/var
    AGENT_OS_LOG_DIR    日志目录，默认 <AGENT_OS_DATA_DIR>/logs
    AGENT_LOG_PATH      共享操作日志文件，默认 <AGENT_OS_LOG_DIR>/framework_log.md
"""
import os

# framework 根目录（本文件位于 <framework>/scripts/）
FRAMEWORK_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir():
    """数据根目录（可用 AGENT_OS_DATA_DIR 覆盖）。"""
    return os.path.abspath(
        os.environ.get("AGENT_OS_DATA_DIR") or os.path.join(FRAMEWORK_ROOT, "var")
    )


def logs_dir():
    """日志目录（可用 AGENT_OS_LOG_DIR 覆盖）。"""
    return os.path.abspath(
        os.environ.get("AGENT_OS_LOG_DIR") or os.path.join(data_dir(), "logs")
    )


def state_dir():
    """持久化状态目录。"""
    return os.path.join(data_dir(), "state")


def state_file(name):
    """状态文件完整路径。"""
    return os.path.join(state_dir(), name)


def log_file(name="framework_log.md"):
    """共享操作日志文件（可用 AGENT_LOG_PATH 覆盖）。"""
    return os.environ.get("AGENT_LOG_PATH") or os.path.join(logs_dir(), name)


def ensure_parent(path):
    """确保 path 的父目录存在，返回 path。"""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return path
