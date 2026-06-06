import os
import json
import hashlib
import math

# 离线模式：模型已缓存，不联网检查更新
os.environ["HF_HUB_OFFLINE"] = "1"

# 延迟导入：不在模块加载时导入 sentence_transformers，避免网络挂起
_HAS_ST = None

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "env.json")


def _load_config():
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


_cfg = _load_config()
_model = None


def _check_st():
    """延迟检测 sentence_transformers 是否可用"""
    global _HAS_ST
    if _HAS_ST is None:
        try:
            # 限制导入时间 - 如果 sentence_transformers 尝试联网会挂起
            import importlib
            import sys
            spec = importlib.util.find_spec("sentence_transformers")
            if spec is None:
                _HAS_ST = False
                print("[embedding] sentence_transformers not installed, using hash fallback")
            else:
                # 只标记为可用，真实导入推迟到 _get_model
                _HAS_ST = True
        except Exception:
            _HAS_ST = False
            print("[embedding] sentence_transformers check failed, using hash fallback")
    return _HAS_ST


def _get_model():
    global _model
    if _model is None and _check_st():
        try:
            from sentence_transformers import SentenceTransformer
            cache = _cfg["embedding"]["cache_folder"]
            os.makedirs(cache, exist_ok=True)
            _model = SentenceTransformer(
                _cfg["embedding"]["model"],
                cache_folder=cache,
            )
        except Exception as e:
            print(f"[embedding] model load failed: {e}, using hash fallback")
            return None
    return _model


def _fallback_embed(text, dim=384):
    """sentence_transformers 未安装时的 fallback：用哈希生成伪向量"""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    vec = []
    for i in range(dim):
        val = ((h[i % 32] + (i * 7) % 256) / 128.0) - 1.0
        vec.append(val)
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def embed(text):
    """将单条文本编码为 384 维向量"""
    model = _get_model()
    if model is None:
        return _fallback_embed(text)
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


def embed_batch(texts):
    """批量编码，返回 list[list[float]]"""
    model = _get_model()
    if model is None:
        return [_fallback_embed(t) for t in texts]
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vecs]
