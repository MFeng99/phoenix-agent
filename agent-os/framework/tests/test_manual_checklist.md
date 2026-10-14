# 手动测试 Checklist

> 对应 Implementation Spec v3.3，Step 5 端到端验证场景。

## 测试环境准备

```bash
# 启动所有服务（在 agent-os/framework 目录下执行）
python run.py

# 安装 Python 依赖（首次）
pip install -r requirements.txt
```

---

## 测试项

### T1: Browser 工具调用
- [ ] 打开编排器 WebUI (http://localhost:8648)
- [ ] 输入："帮我用浏览器打开 https://example.com"
- [ ] 预期：Chrome 浏览器打开页面

### T2: 写入 Qdrant 经验
- [ ] 运行 `python scripts/init_qdrant.py`
- [ ] 预期：测试点写入成功，搜索验证通过
- [ ] 打开 Qdrant Dashboard (http://127.0.0.1:6333/dashboard)
- [ ] 预期：能看到 mfeng_products collection

### T3: 搜索 Qdrant 经验
- [ ] 运行 `python -c "from core import qdrant_client as qc, embedding; vec=embedding.embed('测试'); print(qc.search('mfeng_products', vec, limit=3, score_threshold=0.0))"`
- [ ] 预期：返回搜索结果列表

### T4: Reviewer 审核
- [ ] 运行端到端测试 `python tests/test_e2e.py` 中 Reviewer 部分
- [ ] 预期：高质量结果返回 STORE，低质量返回 DISCARD

### T5: TaskState 断点续跑
- [ ] 运行端到端测试中 TaskState 部分
- [ ] 手动创建一个 RUNNING 状态的任务
- [ ] 重启程序，调用 `resume_incomplete_tasks()`
- [ ] 预期：能读取到未完成任务

### T6: Permission 拒绝
- [ ] 运行 `python -c "from layers.permission import check_permission; print(check_permission('assistant', 'gateway_restart'))"`
- [ ] 预期：`allowed: False`

### T7: Phoenix 自愈
- [ ] 启动 Phoenix: `python phoenix/phoenix.py`
- [ ] 手动 kill 一个被监控的服务进程
- [ ] 等待一个检查周期（默认 30 秒）
- [ ] 预期：Phoenix 检测到异常并按配置自动重启

### T8: Phoenix 熔断保护
- [ ] 让某个被监控服务持续启动失败
- [ ] 观察连续失败次数达到 `max_failures` 阈值
- [ ] 预期：触发熔断进入冷却期，不再反复重启

### T9: MCP Server 连通
- [ ] 启动 Framework MCP Server: `python -m mcp_server --port 18766`
- [ ] 测试健康检查: `curl http://127.0.0.1:18766/health`
- [ ] 测试工具列表: `curl http://127.0.0.1:18766/api/tools/list`
- [ ] 预期：返回 JSON 响应

### T10: 完整管线
- [ ] 运行端到端测试中 Pipeline 部分
- [ ] 预期：Permission → 执行 → Reviewer → Scoring → 写入 全部成功
