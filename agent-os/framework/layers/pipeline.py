"""Pipeline 执行管线 — 完整九步决策流程

对应文档：双Agent风险分级框架设计.md 第七节

流程：
  ① Permission 权限校验
  ② 触发词预检
  ③ 八维风险评估
  ④ 风险等级决策 (LOW→自动 / MEDIUM→口头确认 / HIGH→人工确认)
  ⑤ TaskState 创建 + 执行
  ⑥ Reviewer 审核
  ⑦ TaskState 更新
  ⑧ Scoring 评分
  ⑨ 写入 Qdrant / 丢弃 + 结果汇报
"""
import sys
import os
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from layers.permission import check_permission
from layers.risk_assessment import assess_risk
from layers.task_state import TaskState
from layers.reviewer import review_result
from layers.scoring import calc_scoring
from core import qdrant_client as qc
from core import embedding

COLLECTION = "ai"


def execute_with_layers(user_id, operation, exec_fn, context=None, user_text=None,
                        confirmation_callback=None):
    """完整九步管线执行

    Args:
        user_id: 用户 ID
        operation: 操作名（用于权限校验 + 风险评估）
        exec_fn: 执行函数，返回 {"content": str, ...}
        context: 额外上下文
        user_text: 用户原始指令（用于触发词预检）
        confirmation_callback: MEDIUM/HARD 确认回调函数
            签名: callback(level, reason) -> bool
            返回 True 表示确认执行，False 表示取消

    Returns:
        {
            "success": bool, "task_id": str,
            "permission": dict, "risk": dict,
            "execution": dict | None,
            "review": dict | None, "scoring": int | None,
            "stored": bool,
            "require_confirmation": bool,
        }
    """
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    ts = TaskState()
    ctx = context or {}

    # ── ① Permission 权限校验 ──────────────────────────────
    perm = check_permission(user_id, operation)
    if not perm["allowed"]:
        return _result(False, task_id, perm, None, None, None, None, False, False,
                       reason=f"权限不足: {perm['reason']}")

    # ── ②③ 触发词预检 + 八维风险评估 ──────────────────────
    risk = assess_risk(operation, user_text)

    # ── ④ 风险等级决策 ────────────────────────────────────
    if risk["level"] == "HIGH":
        # HIGH：强制人工确认
        if confirmation_callback:
            confirmed = confirmation_callback("HIGH", risk["reason"])
            if not confirmed:
                return _result(False, task_id, perm, risk, None, None, None, False, False,
                               reason="用户取消 HIGH 风险操作")
        else:
            # 无回调时拒绝
            return _result(False, task_id, perm, risk, None, None, None, False, True,
                           reason=f"HIGH 风险操作需人工确认: {risk['reason']}")

    elif risk["level"] == "MEDIUM":
        # MEDIUM：口头确认
        if confirmation_callback:
            confirmed = confirmation_callback("MEDIUM", risk["reason"])
            if not confirmed:
                return _result(False, task_id, perm, risk, None, None, None, False, False,
                               reason="用户取消 MEDIUM 风险操作")
        else:
            return _result(False, task_id, perm, risk, None, None, None, False, True,
                           reason=f"MEDIUM 风险操作需口头确认: {risk['reason']}")

    # LOW：自动执行，无需确认

    # ── ⑤ TaskState 创建 + 执行 ───────────────────────────
    ts.create_task(task_id, context={"user": user_id, "operation": operation, **ctx})
    ts.update_state(task_id, "RUNNING", {"currentStep": operation})

    try:
        exec_result = exec_fn()
    except Exception as e:
        ts.update_state(task_id, "FAILED", {"error": str(e)[:200]})
        return _result(False, task_id, perm, risk,
                       {"error": str(e)}, None, None, False, False,
                       reason=f"执行异常: {str(e)[:100]}")

    # ── ⑥ Reviewer 审核 ───────────────────────────────────
    review = review_result(exec_result, ctx)

    # ── ⑦ TaskState 更新 ──────────────────────────────────
    ts.update_state(task_id, "DONE", {"result": str(exec_result)[:200]})

    # ── ⑧⑨ Scoring + 写入 Qdrant ──────────────────────────
    score = None
    stored = False

    if review["action"] in ("STORE", "STORE_LOW_PRIORITY"):
        score = calc_scoring(
            reviewer_score=review["score"],
            hit_count=0,
            days_old=0,
            source_count=1,
            is_bad=False,
        )

        try:
            point_id = str(uuid.uuid4())
            vec = embedding.embed(exec_result.get("content", ""))
            point = {
                "id": point_id,
                "vector": vec,
                "payload": {
                    "content": exec_result.get("content", ""),
                    "sku": exec_result.get("sku", ""),
                    "title": exec_result.get("title", ""),
                    "category": exec_result.get("category", ""),
                    "market": exec_result.get("market", ""),
                    "price": exec_result.get("price", 0),
                    "score": score,
                    "reviewer_score": review["score"],
                    "hit_count": 0,
                    "source_count": 1,
                    "is_bad": False,
                    "tags": exec_result.get("tags", []),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            }
            qc.upsert(COLLECTION, [point])
            stored = True
        except Exception:
            pass

    return _result(True, task_id, perm, risk, exec_result, review, score, stored, False)


def _result(success, task_id, permission, risk, execution, review, scoring,
            stored, require_confirmation, reason=None):
    return {
        "success": success,
        "task_id": task_id,
        "permission": permission,
        "risk": risk,
        "execution": execution,
        "review": review,
        "scoring": scoring,
        "stored": stored,
        "require_confirmation": require_confirmation,
        "reason": reason,
    }
