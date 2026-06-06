"""Framework Service v5.0 — FastAPI 服务化部署

用法:
    uvicorn framework_service:app --host 0.0.0.0 --port 18888 --reload

端点:
    GET  /health              → 检查4个服务状态 (公开)
    POST /execute             → 跑完整九步管线
    POST /knowledge/search    → 搜索 Qdrant 知识库
    POST /knowledge/store     → 写入 Qdrant
    GET  /tasks/{task_id}     → 查询任务状态
    GET  /logs                → 查询最近操作日志
"""

import sys
import os
import uuid
import subprocess
import json

# 确保框架模块可导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Optional
import uvicorn

from layers.pipeline import execute_with_layers
from layers.task_state import TaskState
from core import qdrant_client as qc
from core import embedding
from core.cdp_browser import (
    connect_cdp as cdp_connect,
    run_js as cdp_run_js,
    read_upwork_messages as cdp_read_upwork,
    send_upwork_message as cdp_send_upwork,
)
import core.cdp_browser as cdp_browser
from core.freelance_agent import FreelanceAgent
from scripts.agent_log import log_action, get_recent

_freelance_agent: FreelanceAgent | None = None

def _get_freelance_agent() -> FreelanceAgent:
    global _freelance_agent
    if _freelance_agent is None:
        _freelance_agent = FreelanceAgent()
    return _freelance_agent

app = FastAPI(title="Framework v5.0 Service", version="5.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HEALTH_MAP = {
    "Qdrant": {"port": 6333},
    "OpenClaw": {"port": 18789},
    "WebUI": {"port": 8648},
    "CDP": {"port": 9333},
}

# ── API Key 认证 ─────────────────────────────────────────────

# 用户需在 .env 文件或系统环境变量中设置 FRAMEWORK_API_KEY，否则默认空密钥
API_KEY = os.environ.get("FRAMEWORK_API_KEY", "")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_api_key(api_key: str = Depends(api_key_header)):
    if not api_key or api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return api_key


# ── 请求/响应模型 ────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    user_id: str = "user_001"
    operation: str
    user_text: str = ""
    context: dict = {}
    target_agent: Optional[str] = None  # "bpd" | "freelance" | None=自动


class KnowledgeSearchRequest(BaseModel):
    query: str
    limit: int = 5
    score_threshold: float = 0.3


class KnowledgeStoreRequest(BaseModel):
    content: str
    category: str = "general"
    tags: list = []
    score: float = 8.0


class BrowserRunJSRequest(BaseModel):
    tab_keyword: str
    js_code: str


class BrowserReplyRequest(BaseModel):
    message: str


class FreelanceReplyRequest(BaseModel):
    platform: str  # "upwork" or "fiverr"
    message: str


class FreelanceReadRequest(BaseModel):
    platform: str  # "upwork" or "fiverr"


class FreelanceHuntRequest(BaseModel):
    keywords: list[str] | None = None  # 如 ["web scraping", "python"]
    limit: int = 10


# ── 端点实现 ─────────────────────────────────────────────────

@app.get("/health")
def health_check():
    """检查四个关键服务是否在线"""
    import urllib.request
    import urllib.error

    results = {}
    all_ok = True

    for name, info in HEALTH_MAP.items():
        port = info["port"]
        if name == "Qdrant":
            url = f"http://127.0.0.1:{port}/healthz"
        elif name == "CDP":
            url = f"http://127.0.0.1:{port}/json/version"
        else:
            url = f"http://127.0.0.1:{port}/"

        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                results[name] = {
                    "status": "UP",
                    "port": port,
                    "code": resp.status,
                }
        except Exception as e:
            results[name] = {
                "status": "DOWN",
                "port": port,
                "error": str(e),
            }
            all_ok = False

    return {
        "service": "Framework v5.0",
        "healthy": all_ok,
        "services": results,
    }


@app.post("/execute")
def execute_pipeline(req: ExecuteRequest, api_key: str = Depends(get_api_key)):
    """执行完整九步管线 — 通过 OpenClaw agent 执行实际任务"""
    task_id = f"task-{uuid.uuid4().hex[:8]}"

    log_action("Framework", "pipeline.start", f"operation={req.operation} user={req.user_id}", "RUNNING")

    # 构造 exec_fn — 根据 operation 分发到真实执行器
    def _exec_fn():
        op = req.operation.lower()
        context = req.context or {}

        # ── 总超时检测 + CDP端口可用性预检 ────────────────────
        import time, socket
        _exec_start = time.time()
        _cdp_ok = False
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            _cdp_ok = s.connect_ex(('127.0.0.1', 9333)) == 0
            s.close()
        except Exception:
            _cdp_ok = False

        def _within_timeout(limit=25):
            return time.time() - _exec_start < limit

        # ── 方案0: target_agent 指定派发给 Agent 员工 ────────────
        if req.target_agent in ("bpd", "freelance"):
            # 从环境变量获取 AGENT_DIR，默认值可根据部署调整
            AGENT_DIR = os.environ.get(
                "FRAMEWORK_AGENT_DIR",
                os.path.join(os.path.expanduser("~"), ".hermes", "agent-memory")
            )
            agent_path = os.path.join(AGENT_DIR, req.target_agent, "memory.md")
            memory_content = ""
            if os.path.exists(agent_path):
                try:
                    with open(agent_path, "r", encoding="utf-8") as f:
                        memory_content = f.read()
                except Exception:
                    pass

            toolsets = {
                "bpd": ["browser", "web", "search", "file", "terminal"],
                "freelance": ["browser", "web", "search", "file"],
            }

            log_action("Framework", "execute.dispatch", f"target={req.target_agent} op={req.operation}", "OK")
            return {
                "content": req.user_text or req.operation,
                "method": f"dispatch:{req.target_agent}",
                "operation": req.operation,
                "target_agent": req.target_agent,
                "agent_memory_path": agent_path,
                "agent_memory_length": len(memory_content),
                "suggested_toolsets": toolsets.get(req.target_agent, ["browser", "web", "search", "file"]),
                "dispatch": True,
            }

        # ── 方案A: CDP脚本 — 动态扫描匹配 (跳过若CDP端口不可用或超时) ──
        # 从环境变量 FRAMEWORK_CDP_DIR 获取 CDP 脚本目录，默认指向项目下的 cdp-scripts
        CDP_DIR = os.environ.get("FRAMEWORK_CDP_DIR", "")

        if _cdp_ok and _within_timeout():
            is_read = any(kw in op for kw in ["read", "check", "search", "get", "fetch", "view", "look", "peek"])
            is_write = any(kw in op for kw in ["reply", "send", "respond", "write", "post", "create", "update", "fill", "type", "input", "compose"])

            matching_scripts = []
            if os.path.isdir(CDP_DIR):
                all_cjs = [f for f in os.listdir(CDP_DIR) if f.endswith('.cjs')]
                if is_read:
                    matching_scripts.extend([f for f in all_cjs if 'check' in f.lower()])
                if is_write:
                    matching_scripts.extend([f for f in all_cjs if 'reply' in f.lower()])

            for script in matching_scripts:
                if not _within_timeout():
                    break
                path = os.path.join(CDP_DIR, script)
                try:
                    result = subprocess.run(
                        ["node", path],
                        cwd=CDP_DIR,
                        capture_output=True, text=True, timeout=30
                    )
                    if result.returncode == 0:
                        log_action("Framework", "execute.cdp", f"cdp:{script}", "OK")
                        return {
                            "content": result.stdout[:2000],
                            "method": f"cdp:{script}",
                            "raw": result.stdout[:3000],
                            "operation": req.operation,
                        }
                except Exception:
                    continue

        # 方案B: OpenClaw bridge 模块执行
        if _within_timeout():
            try:
                from core.openclaw_bridge import call_oc, agent as oc_agent
                # 尝试通过 OpenClaw agent 执行（短超时，避免挂起）
                result = call_oc(
                    ["agent", "--agent", "main", "--json",
                     "--message", f"[Framework] {req.operation}"],
                    timeout=8
                )
                if result["success"] and result["stdout"].strip():
                    log_action("Framework", "execute.openclaw", f"openclaw:{req.operation}", "OK")
                    try:
                        data = json.loads(result["stdout"])
                        return {
                            "content": data.get("text", result["stdout"][:1000]),
                            "tool": "openclaw",
                            "operation": req.operation,
                        }
                    except (json.JSONDecodeError, ValueError):
                        return {
                            "content": result["stdout"][:1000],
                            "tool": "openclaw",
                            "operation": req.operation,
                        }
            except Exception:
                pass

        # 方案C: Hermes 工具（调 Hermes WebUI API）
        if _within_timeout():
            try:
                import urllib.request
                req_body = json.dumps({
                    "operation": req.operation,
                    "text": req.user_text or req.operation,
                }).encode()
                hermes_req = urllib.request.Request(
                    "http://127.0.0.1:8648/api/execute",
                    data=req_body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(hermes_req, timeout=5) as resp:
                    hermes_result = resp.read().decode()
                    if hermes_result.strip():
                        log_action("Framework", "execute.hermes", f"hermes:{req.operation}", "OK")
                        return {
                            "content": hermes_result[:1000],
                            "tool": "hermes",
                            "operation": req.operation,
                        }
            except Exception:
                pass

        # 方案D: 直接 CDP Node.js 通用脚本 (跳过若CDP端口不可用或超时)
        if _cdp_ok and _within_timeout() and os.path.exists(os.path.join(CDP_DIR, "cdp-helper.cjs")):
            try:
                cdp_url = context.get("cdp_url", "http://127.0.0.1:9333")
                script = (
                    "const {CDP} = require('chrome-remote-interface');"
                    "(async () => {"
                    "    const client = await CDP({url: '" + cdp_url + "'});"
                    "    const {Runtime} = client;"
                    "    const r = await Runtime.evaluate({expression: `" + req.operation + "`});"
                    "    console.log(JSON.stringify(r.result));"
                    "    await client.close();"
                    "})();"
                )
                result = subprocess.run(
                    ["node", "-e", script],
                    capture_output=True, text=True, timeout=15
                )
                if result.returncode == 0 and result.stdout.strip():
                    log_action("Framework", "execute.cdp-eval", f"cdp-eval:{req.operation}", "OK")
                    return {
                        "content": result.stdout[:1000],
                        "tool": "cdp-eval",
                        "operation": req.operation,
                    }
            except Exception:
                pass

        # 最终回退: 返回说明
        log_action("Framework", "execute.fallback", "no executor matched, dispatched to Hermes", "SKIPPED")
        return {
            "content": f"[DISPATCHED] 操作: {req.operation}",
            "tool": "dispatch",
            "operation": req.operation,
            "note": "走 Hermes 手动执行流程（请见 /execute 返回自行处理）",
        }

    try:
        result = execute_with_layers(
            user_id=req.user_id,
            operation=req.operation,
            exec_fn=_exec_fn,
            context=req.context,
            user_text=req.user_text,
        )

        status = "OK" if result.get("success") else "FAILED"
        log_action("Framework", "pipeline.done", f"task={result.get('task_id','?')} success={result.get('success')}", status)

        return {
            "task_id": result.get("task_id", task_id),
            "success": result.get("success", False),
            "reason": result.get("reason", ""),
            "permission": result.get("permission"),
            "risk": result.get("risk"),
            "execution": result.get("execution"),
            "review": result.get("review"),
            "scoring": result.get("scoring"),
            "stored": result.get("stored", False),
            "require_confirmation": result.get("require_confirmation", False),
        }

    except Exception as e:
        log_action("Framework", "pipeline.error", str(e)[:80], "FAILED")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@app.post("/knowledge/search")
def search_knowledge(req: KnowledgeSearchRequest, api_key: str = Depends(get_api_key)):
    """搜索 Qdrant 知识库"""
    try:
        vec = embedding.embed(req.query)
        result = qc.search(
            collection="ai",
            vector=vec,
            limit=req.limit,
            score_threshold=req.score_threshold,
        )

        # 提取结果
        points = []
        if "result" in result:
            for item in result["result"]:
                points.append({
                    "id": item.get("id"),
                    "score": item.get("score"),
                    "content": item.get("payload", {}).get("content", ""),
                    "category": item.get("payload", {}).get("category", ""),
                    "tags": item.get("payload", {}).get("tags", []),
                })

        log_action("Framework", "knowledge.search", f"q=\"{req.query}\" hits={len(points)}", "OK")
        return {"success": True, "query": req.query, "hits": points, "count": len(points)}

    except Exception as e:
        log_action("Framework", "knowledge.search", str(e)[:80], "FAILED")
        return {"success": False, "error": str(e)}


@app.post("/knowledge/store")
def store_knowledge(req: KnowledgeStoreRequest, api_key: str = Depends(get_api_key)):
    """写入 Qdrant 知识库"""
    try:
        point_id = str(uuid.uuid4())
        vec = embedding.embed(req.content)
        from datetime import datetime, timezone

        point = {
            "id": point_id,
            "vector": vec,
            "payload": {
                "content": req.content,
                "category": req.category,
                "tags": req.tags,
                "score": req.score,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        qc.upsert("ai", [point])

        log_action("Framework", "knowledge.store", f"category={req.category} id={point_id[:8]}", "OK")
        return {"success": True, "id": point_id}

    except Exception as e:
        log_action("Framework", "knowledge.store", str(e)[:80], "FAILED")
        return {"success": False, "error": str(e)}


@app.get("/tasks/{task_id}")
def get_task_status(task_id: str, api_key: str = Depends(get_api_key)):
    """查询任务状态"""
    try:
        ts = TaskState()
        state = ts.get_latest(task_id)
        if state is None:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return {"task_id": task_id, "state": state}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Task not found: {str(e)}")


@app.get("/logs")
def get_logs(limit: int = 20, status: str = "", api_key: str = Depends(get_api_key)):
    """返回最近的操作日志"""
    entries = get_recent(status_filter=status or None, limit=limit)
    return {"success": True, "entries": entries, "count": len(entries)}


@app.get("/browser/debug")
def browser_debug(api_key: str = Depends(get_api_key)):
    """调试：检查CDP浏览器模块状态"""
    import traceback, subprocess, json as _json
    result = {}
    try:
        # Check cdp_browser module
        result["cdp_browser_file"] = cdp_browser.__file__
        result["framework_root"] = cdp_browser._FRAMEWORK_ROOT
        result["temp_dir"] = cdp_browser._TEMP_DIR
        result["os_path_exists"] = os.path.exists(cdp_browser._TEMP_DIR)
        
        # Check CDP connection
        try:
            pages = cdp_browser._cdp_json()
            result["cdp_pages"] = len(pages)
        except Exception as e:
            result["cdp_error"] = str(e)[:200]
        
        # List .mjs files
        mjs_files = [f for f in os.listdir(cdp_browser._TEMP_DIR) if f.endswith('.mjs')]
        result["mjs_files"] = mjs_files[:5]
        
        # Run a simple node test with the EXACT reading script
        try:
            r = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=5, cwd=cdp_browser._FRAMEWORK_ROOT)
            result["node_version"] = r.stdout.strip()
        except Exception as e:
            result["node_error"] = str(e)[:200]
        
        # Run the EXACT .mjs script
        debug_mjs = os.path.join(cdp_browser._TEMP_DIR, "upread_1780414769716.debug.mjs")
        if os.path.exists(debug_mjs):
            try:
                r = subprocess.run(["node", debug_mjs], capture_output=True, text=True, timeout=15, cwd=cdp_browser._FRAMEWORK_ROOT)
                result["mjs_test"] = {
                    "rc": r.returncode,
                    "stdout_len": len(r.stdout or ""),
                    "stderr_len": len(r.stderr or ""),
                    "stdout_preview": (r.stdout or "")[:200],
                    "stderr_preview": (r.stderr or "")[:200],
                }
            except Exception as e:
                result["mjs_error"] = str(e)[:300]
        
        result["all_ok"] = True
    except Exception as e:
        result["error"] = str(e)[:500]
        result["traceback"] = traceback.format_exc()
    return result


@app.post("/browser/run-js")
def browser_run_js(req: BrowserRunJSRequest, api_key: str = Depends(get_api_key)):
    """在匹配关键字的标签页中执行任意 JavaScript"""
    try:
        log_action("Framework", "browser.run_js", f'tab="{req.tab_keyword}"', "RUNNING")
        result = cdp_run_js(req.tab_keyword, req.js_code)
        status = "OK" if "result" in result else "FAILED"
        log_action("Framework", "browser.run_js", str(result)[:100], status)
        return {"success": status == "OK", **result}
    except Exception as e:
        log_action("Framework", "browser.run_js", str(e)[:80], "FAILED")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/browser/check-upwork")
def browser_check_upwork(api_key: str = Depends(get_api_key)):
    """读取 Upwork 当前对话的消息内容"""
    try:
        log_action("Framework", "browser.check_upwork", "reading Upwork messages", "RUNNING")
        result = cdp_read_upwork()
        status = "OK" if "content" in result else "FAILED"
        log_action("Framework", "browser.check_upwork", f'content_len={len(result.get("content",""))}', status)
        return {"success": status == "OK", **result}
    except Exception as e:
        log_action("Framework", "browser.check_upwork", str(e)[:80], "FAILED")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/browser/reply-upwork")
def browser_reply_upwork(req: BrowserReplyRequest, api_key: str = Depends(get_api_key)):
    """向 Upwork 当前对话发送消息"""
    try:
        log_action("Framework", "browser.reply_upwork", f'msg_len={len(req.message)}', "RUNNING")
        result = cdp_send_upwork(req.message)
        status = "OK" if result.get("status") == "sent" else "FAILED"
        log_action("Framework", "browser.reply_upwork", str(result)[:100], status)
        return {"success": status == "OK", **result}
    except Exception as e:
        log_action("Framework", "browser.reply_upwork", str(e)[:80], "FAILED")
        raise HTTPException(status_code=500, detail=str(e))


# ── 兼职平台 (Freelance) 端点 ──────────────────────────────────


@app.post("/freelance/check")
def freelance_check(api_key: str = Depends(get_api_key)):
    """检查所有兼职平台是否有新消息"""
    try:
        log_action("Framework", "freelance.check", "checking all platforms", "RUNNING")
        agent = _get_freelance_agent()
        result = agent.check_all()
        status = "NOTIFY" if result.get("has_new") else "OK"
        log_action("Framework", "freelance.check", f"has_new={result.get('has_new')}", status)
        return result
    except Exception as e:
        log_action("Framework", "freelance.check", str(e)[:80], "FAILED")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/freelance/read")
def freelance_read(req: FreelanceReadRequest, api_key: str = Depends(get_api_key)):
    """读取指定平台的完整消息"""
    try:
        log_action("Framework", "freelance.read", f'platform={req.platform}', "RUNNING")
        agent = _get_freelance_agent()
        result = agent.read_messages(req.platform)
        status = "OK" if result.get("success") else "FAILED"
        log_action("Framework", "freelance.read", f'platform={req.platform}', status)
        return result
    except Exception as e:
        log_action("Framework", "freelance.read", str(e)[:80], "FAILED")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/freelance/reply")
def freelance_reply(req: FreelanceReplyRequest, api_key: str = Depends(get_api_key)):
    """向指定平台发送回复"""
    try:
        log_action("Framework", "freelance.reply", f'platform={req.platform} msg_len={len(req.message)}', "RUNNING")
        agent = _get_freelance_agent()
        result = agent.send_reply(req.platform, req.message)
        status = "OK" if result.get("success") else "FAILED"
        log_action("Framework", "freelance.reply", f'platform={req.platform}', status)
        return result
    except Exception as e:
        log_action("Framework", "freelance.reply", str(e)[:80], "FAILED")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/freelance/jobs")
def freelance_jobs(api_key: str = Depends(get_api_key)):
    """返回缓存的岗位列表"""
    try:
        from core.job_search import load_search_results
        jobs = load_search_results()
        return {"success": True, "count": len(jobs), "jobs": jobs}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/freelance/status")
def freelance_status(api_key: str = Depends(get_api_key)):
    """获取兼职平台状态摘要（不含消息全文）"""
    try:
        log_action("Framework", "freelance.status", "getting status summary", "RUNNING")
        agent = _get_freelance_agent()
        result = agent.status()
        log_action("Framework", "freelance.status", "OK", "OK")
        return result
    except Exception as e:
        log_action("Framework", "freelance.status", str(e)[:80], "FAILED")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/freelance/hunt")
def freelance_hunt(req: FreelanceHuntRequest, api_key: str = Depends(get_api_key)):
    """主动找活 — 搜索双平台最新工作机会"""
    try:
        keywords = req.keywords or ["web scraping", "python", "AI automation", "data extraction"]
        log_action("Framework", "freelance.hunt", f"keywords={' '.join(keywords)[:80]}", "RUNNING")
        agent = _get_freelance_agent()
        result = agent.scan_opportunities(keywords=keywords, limit=req.limit)
        status = "OK" if result.get("total", 0) > 0 else "NOT_FOUND"
        log_action("Framework", "freelance.hunt", f"total={result.get('total',0)}", status)
        return result
    except Exception as e:
        log_action("Framework", "freelance.hunt", str(e)[:80], "FAILED")
        raise HTTPException(status_code=500, detail=str(e))


# ── 直接运行入口 ─────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    log_action("Framework", "service.start", "Starting Framework Service on :18888", "RUNNING")
    uvicorn.run(app, host="0.0.0.0", port=18888)
