"""初始化 Qdrant mfeng_products collection 并验证连通性"""
import sys
import os
import io
import uuid

# 强制 stdout 使用 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core import qdrant_client as qc
from core import embedding

COLLECTION = "mfeng_products"


def main():
    print("=" * 50)
    print("Qdrant 初始化脚本")
    print("=" * 50)

    # 1. 健康检查
    print("\n[1/4] 健康检查 ...")
    if not qc.health_check():
        print("  ✗ Qdrant 不可达，请确认 qdrant.exe 已启动在 127.0.0.1:6333")
        sys.exit(1)
    print("  ✓ Qdrant 可达")

    # 2. 创建 collection
    print(f"\n[2/4] 创建 collection '{COLLECTION}' (384维 Cosine) ...")
    result = qc.create_collection(COLLECTION, size=384, distance="Cosine")
    print(f"  ✓ {result}")

    # 3. 写入测试点
    print("\n[3/4] 写入测试点 ...")
    test_vec = embedding.embed("测试用例：商品分析经验")
    test_id = str(uuid.uuid4())
    test_point = {
        "id": test_id,
        "vector": test_vec,
        "payload": {
            "content": "初始化测试点，验证 Qdrant 写入功能正常",
            "sku": "TEST-001",
            "title": "测试商品",
            "category": "test",
            "market": "TEST",
            "price": 0,
            "score": 0,
            "reviewer_score": 0,
            "hit_count": 0,
            "source_count": 1,
            "is_bad": False,
            "tags": ["test"],
        },
    }
    qc.upsert(COLLECTION, [test_point])
    print("  ✓ 写入成功")

    # 4. 搜索验证
    print("\n[4/4] 搜索验证 ...")
    search_vec = embedding.embed("测试")
    results = qc.search(COLLECTION, search_vec, limit=3, score_threshold=0.0)
    if results.get("result"):
        print(f"  ✓ 搜索成功，返回 {len(results['result'])} 条结果")
        for r in results["result"]:
            print(f"    id={r['id']}  score={r['score']:.4f}")
    else:
        print("  ✗ 搜索无结果")
        sys.exit(1)

    # 清理测试点
    print("\n[清理] 删除测试点 ...")
    qc.delete_points(COLLECTION, [test_id])
    print("  ✓ 已删除")

    print("\n" + "=" * 50)
    print("Qdrant 初始化完成，连通性验证通过 ✓")
    print("=" * 50)


if __name__ == "__main__":
    main()
