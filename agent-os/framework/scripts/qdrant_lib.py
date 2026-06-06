# qdrant_lib.py — 知识库核心工具（Hermes 直接调用，无中间 MCP 层）
# 用法：在 Hermes 能访问的 Python 环境中 import 使用
# 依赖：requests, sentence-transformers (或 fallback)
import os, sys, json, uuid, hashlib, math
from datetime import datetime, timezone

# ---------- config ----------
QDRANT_URL = "http://127.0.0.1:6333"
COLLECTION_DEFAULT = "ai"          # 技术经验默认写 ai
COLLECTION_ECOMMERCE = "ecommerce"  # 电商业务写 ecommerce

# ---------- embedding ----------
try:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    from sentence_transformers import SentenceTransformer
    _st = SentenceTransformer("all-MiniLM-L6-v2", cache_folder="F:\\AI Agent\\models")
    def embed(text):
        vec = _st.encode(text, normalize_embeddings=True)
        return vec.tolist()
except Exception:
    def embed(text, dim=384):
        h = hashlib.sha256(text.encode("utf-8")).digest()
        vec = [((h[i % 32] + (i * 7) % 256) / 128.0) - 1.0 for i in range(dim)]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


# ---------- Qdrant HTTP helpers ----------
def _put(path, body):
    import requests
    return requests.put(f"{QDRANT_URL}{path}", json=body, timeout=30)

def _post(path, body):
    import requests
    return requests.post(f"{QDRANT_URL}{path}", json=body, timeout=30)


# ---------- 4 个核心工具 ----------
def qdrant_search(query_text, collection=COLLECTION_DEFAULT, limit=5, score_threshold=0.3):
    """向量搜索知识库"""
    vec = embed(query_text)
    resp = _post(f"/collections/{collection}/points/search", {
        "vector": vec, "limit": limit, "score_threshold": score_threshold, "with_payload": True
    })
    resp.raise_for_status()
    return resp.json().get("result", [])


def qdrant_upsert(experience, collection=COLLECTION_DEFAULT):
    """写入经验到知识库

    experience dict 必须包含:
        content: str    — 提炼后的通用经验描述
        score: int(0-10)  — 质量评分
        category: str   — tech|business|sop
        tags: [str]     — 标签列表
    可选:
        sku, market, confidence(0-1), status(active|deprecated)
    """
    vec = embed(experience["content"])
    point_id = str(uuid.uuid4())

    payload = {
        "content": experience["content"],
        "score": experience.get("score", 5),
        "confidence": experience.get("confidence", 0.8),
        "status": experience.get("status", "active"),
        "category": experience.get("category", "tech"),
        "tags": experience.get("tags", []),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "hit_count": 0,
    }
    for opt in ("sku", "market", "title"):
        if opt in experience:
            payload[opt] = experience[opt]

    resp = _put(f"/collections/{collection}/points?wait=true", {
        "points": [{"id": point_id, "vector": vec, "payload": payload}]
    })
    resp.raise_for_status()
    return {"id": point_id, "status": "stored", "collection": collection}


def qdrant_hit(point_id, collection=COLLECTION_DEFAULT):
    """经验被召回后，hit_count + 1"""
    import requests
    # 读取当前点完整数据
    get_url = f"{QDRANT_URL}/collections/{collection}/points/{point_id}"
    resp = requests.get(get_url, timeout=10).json()
    point = resp.get("result", {})
    current = point.get("payload", {}).get("hit_count", 0)

    # 用 set_payload 更新单个字段
    update_url = f"{QDRANT_URL}/collections/{collection}/points/payload"
    r = requests.post(update_url, json={
        "payload": {"hit_count": current + 1},
        "points": [point_id]
    }, timeout=15)
    r.raise_for_status()
    return current + 1


def qdrant_health():
    """检查 Qdrant 是否可达"""
    import requests
    try:
        return requests.get(f"{QDRANT_URL}/healthz", timeout=5).ok
    except Exception:
        return False
