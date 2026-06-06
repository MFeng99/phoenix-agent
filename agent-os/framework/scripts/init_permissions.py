"""初始化权限配置文件"""
import os
import json
import shutil

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
PERM_FILE = os.path.join(CONFIG_DIR, "permissions.json")


def main():
    if os.path.exists(PERM_FILE):
        backup = PERM_FILE + ".bak"
        shutil.copy2(PERM_FILE, backup)
        print(f"已备份现有配置到: {backup}")

    perms = {
        "users": {
            "admin": {"level": "P3", "note": "主用户，超级管理员"},
            "assistant": {"level": "P1", "note": "AI助手，标准用户"},
            "user_001": {"level": "P3", "note": "默认API用户，最高权限"},
        },
        "operationRequires": {
            "exec": "P2",
            "cron_create": "P2",
            "cron_activate": "P2",
            "message_external": "P2",
            "sessions_spawn": "P2",
            "gateway_restart": "P3",
            "config_set": "P3",
            "qdrant_delete": "P3",
            "guardian_config": "P3",
            "web_search": "P1",
            "web_fetch": "P1",
            "browser": "P1",
            "read": "P0",
            "write": "P1",
            "edit": "P1",
        },
    }

    with open(PERM_FILE, "w", encoding="utf-8") as f:
        json.dump(perms, f, ensure_ascii=False, indent=2)

    print(f"权限配置已写入: {PERM_FILE}")


if __name__ == "__main__":
    main()
