"""Reviewer 审核层 — 三维度评分 + 去重 + 存储决策"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core import qdrant_client as qc
from core import embedding


COLLECTION = "ai"
DUPLICATE_THRESHOLD = 0.95


def review_result(exec_result, task_context=None):
    """审核执行结果，决定是否写入 Qdrant

    Args:
        exec_result: 执行结果 dict，至少包含 "content" 字段
        task_context: 任务上下文（可选）

    Returns:
        {
            "action": "STORE" | "STORE_LOW_PRIORITY" | "DISCARD",
            "score": float (0-10),
            "dimensions": {"completeness": float, "reusability": float, "infoDensity": float},
            "dedup": {"similarity": float, "duplicate": bool}
        }
    """
    content = exec_result.get("content", "")
    if not content or len(content.strip()) < 10:
        return {
            "action": "DISCARD",
            "score": 0,
            "dimensions": {"completeness": 0, "reusability": 0, "infoDensity": 0},
            "dedup": {"similarity": 0, "duplicate": False},
        }

    # 三维度打分（简单启发式，后续可替换为 LLM 评分）
    completeness = _score_completeness(exec_result)
    reusability = _score_reusability(exec_result)
    info_density = _score_info_density(exec_result)

    total = round((completeness + reusability + info_density) / 3, 2)

    # 去重检查
    dedup = _check_duplicate(content)

    # 决策
    if dedup["duplicate"]:
        action = "DISCARD"
    elif total >= 7:
        action = "STORE"
    elif total >= 4:
        action = "STORE_LOW_PRIORITY"
    else:
        action = "DISCARD"

    return {
        "action": action,
        "score": total,
        "dimensions": {
            "completeness": completeness,
            "reusability": reusability,
            "infoDensity": info_density,
        },
        "dedup": dedup,
    }


def _score_completeness(result):
    """完整性评分 0-10"""
    content = result.get("content", "")
    score = 0
    if len(content) > 50:
        score += 3
    if len(content) > 200:
        score += 3
    if result.get("sku"):
        score += 2
    if result.get("category"):
        score += 2
    return min(score, 10)


def _score_reusability(result):
    """可复用性评分 0-10"""
    content = result.get("content", "")
    score = 0
    # 包含通用性词汇
    generic_keywords = ["方法", "步骤", "流程", "技巧", "经验", "注意", "建议", "通用"]
    for kw in generic_keywords:
        if kw in content:
            score += 1
    # 非特定实例
    if not result.get("sku", "").startswith("TEST"):
        score += 2
    return min(score, 10)


def _score_info_density(result):
    """信息密度评分 0-10"""
    content = result.get("content", "")
    if not content:
        return 0
    # 简单用信息熵近似：唯一字占比
    unique_chars = len(set(content))
    total_chars = len(content)
    ratio = unique_chars / max(total_chars, 1)
    return min(round(ratio * 15, 1), 10)


def _check_duplicate(content):
    """向量去重：与已有经验比较相似度"""
    try:
        vec = embedding.embed(content)
        results = qc.search(COLLECTION, vec, limit=1, score_threshold=0.0)
        if results.get("result"):
            top_score = results["result"][0]["score"]
            if top_score >= DUPLICATE_THRESHOLD:
                return {"similarity": top_score, "duplicate": True}
            return {"similarity": top_score, "duplicate": False}
    except Exception:
        pass
    return {"similarity": 0, "duplicate": False}
