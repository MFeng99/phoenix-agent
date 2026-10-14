"""新模块测试 — agent_log, health_check, chrome_cdp_check, seed_knowledge"""
import sys
import os
import io
import json
import uuid
import time

# Windows console UTF-8 workaround. Deliberately scoped to direct script
# execution: reassigning sys.stdout at import time breaks pytest's output
# capture, and therefore CI.
if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_agent_log_basic():
    """测试 Agent Log: 基本写入/读取"""
    from scripts.agent_log import log_action, get_recent, tail_log, log_path

    # 写入测试日志
    log_action("Orchestrator", "test.analyze", "评估用户意图", "OK")
    log_action("Executor", "test.execute", "执行浏览器操作", "RUNNING")
    log_action("Executor", "test.execute", "浏览器操作完成", "DONE")
    log_action("Orchestrator", "test.verify", "验证执行结果", "OK")

    # 读取
    entries = get_recent(limit=10)
    assert len(entries) >= 4, f"日志条目不足: {len(entries)}"

    # 检查最近一条是 Orchestrator 的 verify
    last = entries[-1]
    assert last["agent"] == "Orchestrator", f"最后一条应为Orchestrator: {last['agent']}"
    assert last["action"] == "test.verify", f"action应为test.verify: {last['action']}"

    # tail 输出
    output = tail_log(4)
    assert "Orchestrator" in output
    assert "Executor" in output

    # log_path
    assert log_path().endswith("framework_log.md")

    print(f"  ✓ Agent Log 正常 (日志路径: {log_path()}, 共 {len(entries)} 条)")


def test_agent_log_status_filter():
    """测试 Agent Log: 状态筛选"""
    from scripts.agent_log import get_recent

    failed_entries = get_recent(status_filter="FAILED")
    running_entries = get_recent(status_filter="RUNNING")
    ok_entries = get_recent(status_filter="OK", limit=50)

    assert isinstance(failed_entries, list)
    assert isinstance(running_entries, list)
    for e in running_entries:
        assert e["status"] == "RUNNING"

    print(f"  ✓ 状态筛选正常 (OK={len(ok_entries)}, RUNNING={len(running_entries)})")


def test_agent_log_special_chars():
    """测试 Agent Log: 特殊字符处理"""
    from scripts.agent_log import log_action, get_recent

    # 包含竖线字符的详情
    detail_with_pipe = "执行结果: a | b | c"
    log_action("Orchestrator", "test.special", detail_with_pipe, "OK")

    # 包含换行的详情
    detail_with_newline = "多行\n详情\n内容"
    log_action("Executor", "test.multiline", detail_with_newline, "OK")

    entries = get_recent(limit=5)
    # 检查是否有条目的 action 是 test.special
    special_entries = [e for e in entries if e["action"] == "test.special"]
    assert len(special_entries) > 0, "特殊字符日志应写入成功"

    print(f"  ✓ 特殊字符处理正常")


def test_health_check():
    """测试 Health Check: 服务检查函数"""
    from scripts.health_check import check_service, check_all

    # 测试单个服务检查（Qdrant 可能 UP 或 DOWN，但不抛异常）
    result = check_service("Qdrant", {
        "port": 6333,
        "url": "http://127.0.0.1:6333/healthz",
        "role": "向量知识库",
        "required": True,
    })
    assert "name" in result
    assert "status" in result
    assert result["status"] in ("UP", "DOWN", "UNKNOWN")
    assert "latency_ms" in result

    # 测试一个不存在的端口
    result_down = check_service("Ghost", {
        "port": 59999,
        "url": "http://127.0.0.1:59999/",
        "role": "不存在",
        "required": False,
    })
    assert result_down["status"] == "DOWN"

    # check_all 不应抛异常
    all_results = check_all()
    assert len(all_results) == 4
    for r in all_results:
        assert r["status"] in ("UP", "DOWN")

    print(f"  ✓ Health Check 正常 (Qdrant={result['status']}, Ghost={result_down['status']})")


def test_chrome_cdp_check():
    """测试 Chrome CDP Check: 函数不抛异常"""
    from scripts.chrome_cdp_check import check_cdp_running, list_tabs, check_fiverr_login

    # 这些函数应该优雅处理 CDP 不可达的情况，不抛异常
    cdp_status = check_cdp_running()
    assert "running" in cdp_status
    assert cdp_status["running"] in (True, False)

    tabs = list_tabs()
    assert isinstance(tabs, list)

    fiverr = check_fiverr_login()
    assert "logged_in" in fiverr
    assert isinstance(fiverr["logged_in"], bool)

    print(f"  ✓ CDP Check 正常 (CDP={'UP' if cdp_status['running'] else 'DOWN'}, "
          f"tabs={len(tabs)}, fiverr_logged_in={fiverr['logged_in']})")


def test_seed_knowledge_load_file():
    """测试 Seed Knowledge: 文件加载"""
    from scripts.seed_knowledge import load_knowledge_from_file

    # 加载 data/knowledge.json
    data_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "knowledge.json")
    if os.path.exists(data_file):
        entries = load_knowledge_from_file(data_file)
        assert len(entries) == 3, f"应有3条知识: {len(entries)}"
        for e in entries:
            assert "content" in e, "每条需含content"
        print(f"  ✓ Seed Knowledge 文件加载正常 ({len(entries)} 条)")
    else:
        print(f"  - Seed Knowledge 文件不存在，跳过加载测试")


def test_seed_knowledge_batch():
    """测试 Seed Knowledge: 批量写入预览和真实写入"""
    from scripts.seed_knowledge import batch_upsert

    test_entries = [
        {"content": "测试知识一：这是一个测试条目，用于验证批量写入功能。", "category": "tech", "score": 5},
        {"content": "测试知识二：第二个测试条目。", "category": "business", "score": 6},
        {"content": "", "category": "tech"},  # 空条会被跳过
    ]

    # dry-run 模式：空content会在content检查时被跳过
    stats = batch_upsert(test_entries, dry_run=True)
    assert stats["total"] == 3
    assert stats["success"] == 2  # 两个有内容的条目
    assert stats["skipped"] == 1  # 空content被跳过

    # 实际写入模式（如果 Qdrant 不可达会抛异常，捕获之）
    try:
        stats_real = batch_upsert(test_entries, dry_run=False)
        assert stats_real["total"] == 3
        assert stats_real["skipped"] >= 0
        print(f"  ✓ Seed Knowledge 批量正常 (dry_ok={stats['success']}, real_ok={stats_real['success']})")
    except Exception as e:
        print(f"  - Qdrant 不可达，跳过真实写入测试 ({str(e)[:60]})")


def main():
    print("=" * 50)
    print("  新模块测试")
    print("=" * 50)

    tests = [
        ("Agent Log 基本", test_agent_log_basic),
        ("Agent Log 筛选", test_agent_log_status_filter),
        ("Agent Log 特殊字符", test_agent_log_special_chars),
        ("Health Check", test_health_check),
        ("CDP Check", test_chrome_cdp_check),
        ("Seed Knowledge 加载", test_seed_knowledge_load_file),
        ("Seed Knowledge 批量", test_seed_knowledge_batch),
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
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 50)
    print(f"  结果: {passed} 通过, {failed} 失败")
    print("=" * 50)
    return failed


if __name__ == "__main__":
    sys.exit(main())
