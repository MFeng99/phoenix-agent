"""网上兼职 Agent — 管理 Upwork + Fiverr 消息收发与机会搜索"""

import hashlib
import json
import os
import time as _time
from datetime import datetime, timezone

from . import cdp_browser as cdp
from core.job_search import load_search_results, save_search_results, deduplicate_jobs

# ── 路径 ───────────────────────────────────────────────────────

_FRAMEWORK_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(
    _FRAMEWORK_ROOT, "agent-memory", "freelance", "freelance-state.json"
)
ACTION_LOG = os.path.join(_FRAMEWORK_ROOT, "logs", "freelance-actions.json")
os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
os.makedirs(os.path.dirname(ACTION_LOG), exist_ok=True)


# ── 平台配置 ───────────────────────────────────────────────────

PLATFORMS = {
    "upwork": {
        "name": "Upwork",
        "url_match": "upwork.com/ab/messages",
        "read_fn": cdp.read_upwork_messages,
        "send_fn": cdp.send_upwork_message,
        "search_fn": cdp.search_upwork_jobs,
    },
    "fiverr": {
        "name": "Fiverr",
        "url_match": "fiverr.com/inbox",
        "read_fn": cdp.read_fiverr_messages,
        "send_fn": cdp.send_fiverr_message,
        "search_fn": cdp.search_fiverr_opportunities,
    },
}


# ── Agent 核心 ─────────────────────────────────────────────────


class FreelanceAgent:
    """网上兼职 Agent — 管理 Upwork + Fiverr"""

    def __init__(self):
        self.state = self._load_state()
        self.knowledge = self._load_knowledge()

    # ── 状态管理 ────────────────────────────────────────────

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "last_check": "",
            "platforms": {},
            "proposals": [],
            "clients": {},
        }

    def _save_state(self):
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        self.state["last_check"] = datetime.now(timezone.utc).isoformat()
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def _load_knowledge(self):
        kb_dir = os.path.join(_FRAMEWORK_ROOT, "agent-memory", "freelance")
        kb_file = os.path.join(kb_dir, "memory.md")
        if os.path.exists(kb_file):
            try:
                with open(kb_file, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                pass
        return ""

    # ── 哈希去重 ─────────────────────────────────────────────

    @staticmethod
    def _hash_messages(content: str) -> str:
        return hashlib.md5(content.encode()).hexdigest() if content else ""

    # ── 平台操作 ────────────────────────────────────────────

    def check_platform(self, platform_key: str) -> dict:
        p = PLATFORMS.get(platform_key)
        if not p:
            return {"platform": platform_key, "error": "Unknown platform"}

        try:
            result = p["read_fn"]()
            content = result.get("content", "")
            total_length = result.get("totalLength", 0)
        except Exception as e:
            log_action("Freelance", f"{platform_key}.read", str(e)[:100], "FAILED")
            return {
                "platform": platform_key,
                "error": str(e),
                "status": "error",
            }

        current_hash = self._hash_messages(content)
        prev_state = self.state.get("platforms", {}).get(platform_key, {})
        prev_hash = prev_state.get("hash", "")
        is_new = bool(prev_hash) and current_hash != prev_hash

        if "platforms" not in self.state:
            self.state["platforms"] = {}
        self.state["platforms"][platform_key] = {
            "hash": current_hash,
            "total_length": total_length,
            "is_new": is_new,
            "last_update": datetime.now(timezone.utc).isoformat(),
        }

        log_action(
            "Freelance",
            f"{platform_key}.check",
            f"msgs={total_length} is_new={is_new}",
            "OK",
        )

        return {
            "platform": platform_key,
            "name": p["name"],
            "success": True,
            "is_new": is_new,
            "content": content,
            "total_length": total_length,
        }

    def check_all(self) -> dict:
        results = {}
        for key in PLATFORMS:
            results[key] = self.check_platform(key)
        self._save_state()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platforms": results,
            "has_new": any(r.get("is_new") for r in results.values()),
        }

    def read_messages(self, platform: str) -> dict:
        p = PLATFORMS.get(platform)
        if not p:
            return {"error": f"Unknown platform: {platform}"}
        try:
            result = p["read_fn"]()
            return {"platform": platform, "success": True, **result}
        except Exception as e:
            log_action("Freelance", f"{platform}.read", str(e)[:100], "FAILED")
            return {"platform": platform, "error": str(e)}

    def send_reply(self, platform: str, message: str) -> dict:
        p = PLATFORMS.get(platform)
        if not p:
            return {"error": f"Unknown platform: {platform}"}
        try:
            result = p["send_fn"](message)
            log_action(
                "Freelance",
                f"{platform}.reply",
                f"length={len(message)} result={result.get('status','?')}",
                "OK",
            )
            return {"platform": platform, "success": True, **result}
        except Exception as e:
            log_action("Freelance", f"{platform}.reply", str(e)[:100], "FAILED")
            return {"platform": platform, "error": str(e)}

    # ── 智能回复 ────────────────────────────────────────────

    def classify_message(self, platform: str, content: str) -> str:
        if not content:
            return "other"
        text = content.lower()
        if any(w in text for w in ["offer", "job", "position", "hire"]):
            return "offer"
        if any(w in text for w in ["question", "rate", "available", "interested"]):
            return "inquiry"
        if any(w in text for w in ["thank", "next step", "looking forward"]):
            return "followup"
        return "other"

    # ── 机会搜索 ────────────────────────────────────────────

    def scan_opportunities(self, keywords: list[str] | None = None, limit: int = 10) -> dict:
        """主动搜索最新工作机会（从缓存读取 + CDP尝试）"""
        result = {}

        # 从搜索缓存加载
        cached = load_search_results()
        result["cached_jobs"] = cached[:limit] if cached else []

        for key, p in PLATFORMS.items():
            try:
                sk = p.get("search_fn")
                if not sk:
                    continue
                jobs = sk()
                result[key] = {"success": True, "count": len(jobs), "jobs": jobs}
            except Exception as e:
                result[key] = {"success": False, "error": str(e)}
        self.state["last_scan"] = {"time": datetime.now().isoformat(), "results": result}
        self._save_state()
        log_action(
            "Freelance", "hunt",
            f"platforms={len(result)} cached={len(result.get('cached_jobs',[]))}",
            "OK",
        )
        return result

    # ── 状态报告 ────────────────────────────────────────────

    def status(self) -> dict:
        cached_jobs = load_search_results()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "last_check": self.state.get("last_check", ""),
            "platforms": self.state.get("platforms", {}),
            "proposals": self.state.get("proposals", []),
            "clients": self.state.get("clients", {}),
            "last_scan": self.state.get("last_scan", {}),
            "cached_jobs": len(cached_jobs),
        }


# ── 日志 ───────────────────────────────────────────────────────


def log_action(agent: str, action: str, detail: str, status: str = "OK"):
    entry = {
        "timestamp": _time.strftime("%Y-%m-%d %H:%M:%S"),
        "agent": agent[:20],
        "action": action[:30],
        "detail": detail[:100],
        "status": status[:10],
    }
    try:
        os.makedirs(os.path.dirname(ACTION_LOG), exist_ok=True)
        records = []
        if os.path.exists(ACTION_LOG):
            with open(ACTION_LOG, "r", encoding="utf-8") as f:
                records = json.load(f)
        records.append(entry)
        records = records[-500:]
        with open(ACTION_LOG, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
