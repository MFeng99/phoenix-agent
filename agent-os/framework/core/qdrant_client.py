import os
import json
import requests

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "env.json")

def _load_config():
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

_cfg = _load_config()
QDRANT_URL = _cfg["qdrant"]["url"]
COLLECTION = "ai"


def health_check():
    """L1: Qdrant 是否可达"""
    try:
        resp = requests.get(f"{QDRANT_URL}/healthz", timeout=5)
        return resp.ok
    except requests.ConnectionError:
        return False


def create_collection(name=COLLECTION, size=384, distance="Cosine"):
    """创建 collection，已存在则跳过"""
    url = f"{QDRANT_URL}/collections/{name}"
    # 检查是否已存在
    try:
        resp = requests.get(url, timeout=5)
        if resp.ok:
            return {"status": "already_exists", "collection": name}
    except requests.ConnectionError:
        pass

    payload = {"vectors": {"size": size, "distance": distance}}
    resp = requests.put(url, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def upsert(collection, points):
    """插入或更新点

    Args:
        collection: collection 名称
        points: list[dict]，每个点包含 id, vector, payload
    """
    url = f"{QDRANT_URL}/collections/{collection}/points?wait=true"
    payload = {"points": points}
    resp = requests.put(url, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def search(collection, vector, limit=5, score_threshold=0.7, order_by=None):
    """向量搜索

    Args:
        vector: 384 维向量
        order_by: {"key": "score", "direction": "desc"} 等
    """
    url = f"{QDRANT_URL}/collections/{collection}/points/search"
    payload = {"vector": vector, "limit": limit, "score_threshold": score_threshold, "with_payload": True}
    if order_by:
        payload["order_by"] = order_by
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def scroll(collection, filter_cond=None, order_by=None, limit=10):
    """按条件滚动查询（用于高分经验召回、统计等）"""
    url = f"{QDRANT_URL}/collections/{collection}/points/scroll"
    payload = {"limit": limit, "with_payload": True}
    if filter_cond:
        payload["filter"] = filter_cond
    if order_by:
        payload["order_by"] = order_by
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def set_payload(collection, points):
    """更新 payload（用于动态更新 hit_count / score 等字段）

    Args:
        points: list[dict]，每个包含 id 和 payload
    """
    url = f"{QDRANT_URL}/collections/{collection}/points/payload?wait=true"
    payload = {"points": points}
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def delete_points(collection, ids):
    """删除指定 ID 的点"""
    url = f"{QDRANT_URL}/collections/{collection}/points/delete?wait=true"
    payload = {"points": ids}
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()
