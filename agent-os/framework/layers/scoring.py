"""Scoring 经验评分系统 — 四因子加权 + 负面惩罚"""
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core import qdrant_client as qc

COLLECTION = "ai"


def calc_scoring(reviewer_score, hit_count=0, days_old=0, source_count=1, is_bad=False):
    """计算经验总分 (0-100)

    Args:
        reviewer_score: Reviewer 原始评分 (0-10)
        hit_count: 被召回次数
        days_old: 经验创建距今天数
        source_count: 来源执行次数
        is_bad: 是否被标记为劣质

    Returns:
        int: 0-100 的总分
    """
    # 质量分 (40%) — reviewer 0-10 映射到 0-40
    quality = reviewer_score * 4

    # 命中分 (20%)
    hit = min(hit_count * 2, 20)

    # 时效分 (20%) — 越新越高
    timeliness = max(0, 20 - days_old * 0.5)

    # 多样性分 (10%)
    diversity = min(source_count * 3, 10)

    # 负面惩罚
    penalty = 20 if is_bad else 0

    total = quality * 0.4 + hit * 0.2 + timeliness * 0.2 + diversity * 0.1 - penalty * 0.2
    return max(0, min(100, int(total)))


def update_qdrant_score(point_id, new_score):
    """回写评分到 Qdrant"""
    qc.set_payload(COLLECTION, [{
        "id": point_id,
        "payload": {"score": new_score},
    }])


def increment_hit_count(point_id):
    """经验被召回时，hit_count + 1"""
    # 先查当前值
    try:
        results = qc.scroll(
            COLLECTION,
            filter_cond={
                "must": [{"key": "id", "match": {"value": point_id}}]
            },
            limit=1,
        )
        points = results.get("result", {}).get("points", [])
        if points:
            current = points[0].get("payload", {}).get("hit_count", 0)
            qc.set_payload(COLLECTION, [{
                "id": point_id,
                "payload": {
                    "hit_count": current + 1,
                    "last_hit_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                },
            }])
    except Exception:
        pass
