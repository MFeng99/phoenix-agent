"""端到端测试 — 验证框架各层连通性"""
import sys
import os
import uuid
import io

# Windows console UTF-8 workaround -- scoped to direct execution only, since
# reassigning sys.stdout at import time breaks pytest's output capture.
if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_qdrant_connectivity():
    """测试 1: Qdrant 连通性"""
    from core import qdrant_client as qc
    assert qc.health_check(), "Qdrant 不可达"
    print("  ✓ Qdrant 连通")


def test_embedding():
    """测试 2: 文本向量化"""
    from core import embedding
    vec = embedding.embed("测试文本")
    assert isinstance(vec, list), "返回值不是 list"
    assert len(vec) == 384, f"向量维度 {len(vec)} != 384"
    print(f"  ✓ Embedding 正常，维度={len(vec)}")


def test_qdrant_crud():
    """测试 3: Qdrant 写入/搜索/删除"""
    from core import qdrant_client as qc
    from core import embedding

    # 确保 collection 存在
    qc.create_collection("mfeng_products", size=384, distance="Cosine")

    # 写入
    vec = embedding.embed("端到端测试经验")
    test_id = str(uuid.uuid4())
    point = {
        "id": test_id,
        "vector": vec,
        "payload": {"content": "端到端测试经验", "sku": "E2E-001", "score": 50},
    }
    qc.upsert("mfeng_products", [point])

    # 搜索
    results = qc.search("mfeng_products", vec, limit=1, score_threshold=0.0)
    assert results.get("result"), "搜索无结果"
    print(f"  ✓ Qdrant CRUD 正常")

    # 清理
    qc.delete_points("mfeng_products", [test_id])


def test_permission():
    """测试 4: 权限校验"""
    from layers.permission import check_permission

    # P3 用户执行 exec (需要 P2) → 通过
    r1 = check_permission("admin", "exec")
    assert r1["allowed"], f"P3 用户 exec 应通过: {r1}"

    # P1 用户执行 gateway_restart (需要 P3) → 拒绝
    r2 = check_permission("assistant", "gateway_restart")
    assert not r2["allowed"], f"P1 用户 gateway_restart 应拒绝"

    print(f"  ✓ Permission 层正常")


def test_task_state():
    """测试 5: 任务状态机"""
    from layers.task_state import TaskState
    import uuid

    ts = TaskState()
    tid = f"e2e-{uuid.uuid4().hex[:8]}"

    # 创建
    r = ts.create_task(tid, {"test": True})
    assert r.get("state") == "CREATED", f"创建失败: {r}"

    # 更新
    r = ts.update_state(tid, "RUNNING", {"currentStep": "test"})
    assert r.get("state") == "RUNNING", f"更新失败: {r}"

    # 读取
    r = ts.get_latest(tid)
    assert r["state"] == "RUNNING", f"读取失败: {r}"

    # 完成
    r = ts.update_state(tid, "DONE")
    assert r.get("state") == "DONE", f"完成失败: {r}"

    print(f"  ✓ TaskState 正常")


def test_reviewer():
    """测试 6: Reviewer 审核"""
    from layers.reviewer import review_result

    # 高质量结果
    r1 = review_result({
        "content": "这是一个完整的操作经验，包含步骤：第一步登录、第二步搜索、第三步下单。方法通用可复用。" * 5,
        "sku": "TEST-SKU-001",
        "category": "电商",
    })
    assert r1["action"] in ("STORE", "STORE_LOW_PRIORITY"), f"高质量结果应 STORE: {r1}"

    # 低质量结果
    r2 = review_result({"content": "ok"})
    assert r2["action"] == "DISCARD", f"低质量结果应 DISCARD: {r2}"

    print(f"  ✓ Reviewer 正常 (高质量={r1['action']}, 低质量={r2['action']})")


def test_scoring():
    """测试 7: Scoring 评分"""
    from layers.scoring import calc_scoring

    s1 = calc_scoring(reviewer_score=8, hit_count=5, days_old=1, source_count=3, is_bad=False)
    assert 0 <= s1 <= 100, f"分数超出范围: {s1}"

    s2 = calc_scoring(reviewer_score=2, hit_count=0, days_old=100, source_count=1, is_bad=True)
    assert s2 < s1, f"差经验分数应低于好经验: {s2} >= {s1}"

    print(f"  ✓ Scoring 正常 (好经验={s1}, 差经验={s2})")


def test_pipeline():
    """测试 8: 完整管线"""
    from layers.pipeline import execute_with_layers

    result = execute_with_layers(
        user_id="admin",
        operation="web_search",
        exec_fn=lambda: {"content": "管线测试经验：搜索关键词返回了5个结果", "sku": "PIPE-001"},
        context={"test": True},
    )
    assert result["success"], f"管线执行失败: {result}"
    assert result["permission"]["allowed"], "权限应通过"
    assert result["review"]["action"] in ("STORE", "STORE_LOW_PRIORITY", "DISCARD")
    print(f"  ✓ Pipeline 正常 (review={result['review']['action']}, stored={result['stored']})")


def test_qdrant_lib():
    """测试 9: qdrant_lib 核心函数"""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts'))
    from qdrant_lib import qdrant_health, qdrant_search, qdrant_upsert, qdrant_hit
    assert qdrant_health(), "Qdrant 不可达"
    r = qdrant_search('test', 'ai', limit=1)
    assert isinstance(r, list), "search 应返回 list"
    print(f"  ✓ qdrant_lib OK (health=True, search={len(r)} results)")


def test_risk_assessment():
    """测试 10: 风险评估"""
    from layers.risk_assessment import assess_risk, trigger_word_check

    # 低风险：搜索
    r1 = assess_risk("web_search", "搜索TikTok商品")
    assert r1["level"] == "LOW", f"搜索应为 LOW: {r1}"

    # 高风险：exec
    r2 = assess_risk("exec", "执行命令删除临时文件")
    assert r2["level"] == "HIGH", f"exec 应为 HIGH: {r2}"

    # 高风险：触发词
    r3 = assess_risk("web_search", "帮我发送邮件给客户")
    assert r3["level"] == "HIGH", f"命中发送触发词应为 HIGH: {r3}"

    # 中风险：触发词
    r4 = assess_risk("web_search", "打开网页并截图")
    assert r4["level"] == "MEDIUM", f"命中浏览器触发词应为 MEDIUM: {r4}"

    # 触发词单独测试
    t1 = trigger_word_check("删除所有文件")
    assert t1["level"] == "HIGH"
    t2 = trigger_word_check("保存文档到本地")
    assert t2["level"] == "MEDIUM"
    t3 = trigger_word_check("查询订单列表")
    assert t3["level"] == "LOW"

    print(f"  ✓ 风险评估正常 (LOW={r1['level']}, HIGH={r2['level']}, 触发词=OK)")


def main():
    print("=" * 50)
    print("  端到端测试")
    print("=" * 50)

    tests = [
        ("Qdrant 连通", test_qdrant_connectivity),
        ("Embedding", test_embedding),
        ("Qdrant CRUD", test_qdrant_crud),
        ("Permission", test_permission),
        ("TaskState", test_task_state),
        ("Reviewer", test_reviewer),
        ("Scoring", test_scoring),
        ("Pipeline", test_pipeline),
        ("qdrant_lib", test_qdrant_lib),
        ("风险评估", test_risk_assessment),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        print(f"\n[{name}]")
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  ✗ 失败: {e}")
            failed += 1

    print("\n" + "=" * 50)
    print(f"  结果: {passed} 通过, {failed} 失败")
    print("=" * 50)
    return failed


if __name__ == "__main__":
    sys.exit(main())
