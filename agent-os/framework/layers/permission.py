"""Permission 权限层 — P0-P3 等级校验"""
import os
import json

_CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
_DEFAULT_PERM_FILE = os.path.join(_CONFIG_DIR, "permissions.json")

_LEVELS = ["P0", "P1", "P2", "P3"]


def _load_permissions(path=None):
    p = path or _DEFAULT_PERM_FILE
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _compare(user_level, required_level):
    """返回 >= 0 表示权限足够"""
    return _LEVELS.index(user_level) - _LEVELS.index(required_level)


def check_permission(user_id, operation, perm_path=None):
    """校验用户是否有权限执行操作

    Args:
        user_id: 用户标识，如 "admin"
        operation: 操作名，如 "exec", "gateway_restart"
        perm_path: 权限文件路径，默认 config/permissions.json

    Returns:
        {"allowed": bool, "reason": str, "user_level": str, "required_level": str}
    """
    perms = _load_permissions(perm_path)

    user_info = perms.get("users", {}).get(user_id)
    if not user_info:
        return {"allowed": False, "reason": f"未知用户: {user_id}", "user_level": None, "required_level": None}

    user_level = user_info["level"]
    required_level = perms.get("operationRequires", {}).get(operation)

    if required_level is None:
        # 未配置的操作默认 P1
        required_level = "P1"

    if _compare(user_level, required_level) < 0:
        return {
            "allowed": False,
            "reason": f"权限不足：用户 {user_id} 为 {user_level}，操作 '{operation}' 需要 {required_level}",
            "user_level": user_level,
            "required_level": required_level,
        }

    return {"allowed": True, "reason": "权限通过", "user_level": user_level, "required_level": required_level}
