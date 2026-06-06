"""种子知识脚本 — 向 Qdrant 写入框架知识和业务经验

支持三种知识来源：
  1. 内置 v5.0 架构知识（8条）
  2. JSON/JSONL 知识文件批量导入
  3. 命令行交互式单条写入

用法:
    python scripts/seed_knowledge.py                        # 写入内置种子知识
    python scripts/seed_knowledge.py --batch data/knowledge.json  # 批量导入文件
    python scripts/seed_knowledge.py --add                  # 交互式添加
    python scripts/seed_knowledge.py --dry-run              # 预览而不写入
    python scripts/seed_knowledge.py --list                 # 列出已有的知识条目
"""
import argparse
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(__file__))
from qdrant_lib import qdrant_upsert, qdrant_health, qdrant_search


# ── 内置种子知识 ─────────────────────────────────────────────

BUILTIN_ENTRIES = [
    {
        "content": "Hermes+OpenClaw v5.0架构：移除Framework MCP中间层，所有风险评估和权限校验由Hermes内建推理完成。OpenClaw由PM2守护，崩溃自动拉起。Qdrant采用ai+ecommerce双collection策略。",
        "score": 10, "confidence": 1.0, "category": "tech",
        "tags": ["architecture", "v5.0", "hermes", "openclaw", "pm2", "qdrant"],
    },
    {
        "content": "PM2替代自写Guardian是v5.0最大改进。旧Guardian(v1.4-v4.1)用端口和日志猜测进程状态，误判导致反复杀CLI。PM2作为父进程，子进程退出立刻知道，100%准确。配置：max_memory_restart=800M, max_restarts=10, restart_delay=5s。",
        "score": 10, "confidence": 1.0, "category": "tech",
        "tags": ["pm2", "guardian", "self-healing", "process-management"],
    },
    {
        "content": "qdrant_lib.py极简封装：4个函数(search/upsert/hit/health)，直连port 6333，无中间层。sentence-transformers离线模式+hash fallback保证无网络时也能工作。embedding缓存到F:\\AI Agent\\models。",
        "score": 9, "confidence": 0.9, "category": "tech",
        "tags": ["qdrant", "embedding", "knowledge-base", "qdrant_lib"],
    },
    {
        "content": "启动流程v5.0极简：4步，无串行依赖。Qdrant→OpenClaw(PM2)→Hermes WebUI→Chrome CDP。hermes-web-ui启动需15-30秒才能端口就绪，脚本内有轮询等待逻辑。",
        "score": 8, "confidence": 0.9, "category": "tech",
        "tags": ["startup", "boot", "launcher", "bat"],
    },
    {
        "content": "Qdrant v1.18.1兼容性要点：health endpoint是/healthz(非/health)；启动无--listen-addr参数直接./qdrant.exe；point ID只接受UUID或uint64；search默认不返回payload必须加with_payload:true。",
        "score": 9, "confidence": 1.0, "category": "tech",
        "tags": ["qdrant", "compatibility", "v1.18.1", "pitfalls"],
    },
    {
        "content": "ECONNRESET的根因不是网络问题而是会话历史堆积。当session消息数>200条时context_estimate耗时超过TCP超时触发reset。解决方案：Guardian(旧)/PM2(新)定时trim sessions到15条。trim阈值30条触发、保留15条、每30秒检查一次。",
        "score": 9, "confidence": 0.95, "category": "tech",
        "tags": ["ECONNRESET", "session-bloat", "trim", "bridge", "debug"],
    },
    {
        "content": "风险评估内建模板：1)触发词预检-删除/发送/支付/部署/执行命令/下单命中即HIGH；2)八维评估-影响范围/数据敏感/可逆性/外部可见/合规/资源/链路/系统级；3)决策规则-任一维度HIGH即HIGH，任一MEDIUM即MEDIUM，全LOW才LOW。",
        "score": 9, "confidence": 0.9, "category": "tech",
        "tags": ["risk-assessment", "trigger-words", "eight-dimensions"],
    },
    {
        "content": "TikTok Shop电商运营SOP：商品上架需登录卖家中心→商品管理→填写标题/价格/库存→提交审核。竞品分析需web_search+browser截图对比。客户消息回复需人工确认后再发送(高风险操作)。",
        "score": 7, "confidence": 0.8, "category": "business",
        "tags": ["tiktok", "ecommerce", "sop", "seller-center"],
    },
]


# ── 数据目录扫描 ──────────────────────────────────────────────

def find_data_dir():
    """查找数据目录，依次尝试:
    1. 框架根目录下的 data/
    2. scripts/ 同级的 data/
    3. 用户桌面的 data/
    """
    framework_root = os.path.dirname(os.path.dirname(__file__))
    candidates = [
        os.path.join(framework_root, "data"),
        os.path.join(os.path.dirname(__file__), "data"),
        os.path.join(os.path.expanduser("~"), "Desktop", "framework-data"),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None


def load_knowledge_from_file(filepath):
    """从 JSON 或 JSONL 文件加载知识条目

    支持格式:
      JSON:  {"entries": [{...}, {...}]}
      JSONL: 每行一个 {"content": "...", ...}

    每条的必填字段: content
    可选字段: score(0-10), confidence(0-1), category(tech|business|sop), tags(list)

    Returns:
        list[dict]: 知识条目列表
    """
    entries = []
    ext = os.path.splitext(filepath)[1].lower()

    with open(filepath, "r", encoding="utf-8") as f:
        if ext == ".jsonl":
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        elif ext == ".json":
            data = json.load(f)
            if isinstance(data, list):
                entries = data
            elif isinstance(data, dict) and "entries" in data:
                entries = data["entries"]
            else:
                entries = [data]
        else:
            # 尝试 JSON 解析
            content = f.read()
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    entries = data
                elif isinstance(data, dict) and "entries" in data:
                    entries = data["entries"]
                else:
                    entries = [data]
            except json.JSONDecodeError:
                print(f"警告: 无法解析文件 {filepath}，跳过")
                return []

    return entries


def collect_knowledge_from_data_dir():
    """从数据目录收集所有知识条目"""
    data_dir = find_data_dir()
    if not data_dir:
        return []

    all_entries = []
    for fname in os.listdir(data_dir):
        fpath = os.path.join(data_dir, fname)
        if fname.endswith((".json", ".jsonl")):
            entries = load_knowledge_from_file(fpath)
            all_entries.extend(entries)
            print(f"  -> 从 {fname} 加载 {len(entries)} 条")

    return all_entries


# ── 批量写入 ──────────────────────────────────────────────────

def batch_upsert(entries, collection=None, dry_run=False):
    """批量写入知识条目到 Qdrant

    Args:
        entries: list[dict] 知识条目
        collection: 指定 collection，为 None 时按 category 自动选择
        dry_run: True 时仅预览，不写入

    Returns:
        dict: {"total": N, "success": N, "failed": N, "skipped": N, "results": [...]}
    """
    stats = {"total": len(entries), "success": 0, "failed": 0, "skipped": 0, "results": []}

    if not entries:
        print("无条目需要写入。")
        return stats

    for i, entry in enumerate(entries):
        # 确定 collection
        if collection:
            coll = collection
        else:
            coll = "ecommerce" if entry.get("category") == "business" else "ai"

        # 验证必填字段
        if not entry.get("content"):
            print(f"  [{i+1}/{len(entries)}] 跳过: 缺少 content 字段")
            stats["skipped"] += 1
            continue

        if dry_run:
            preview = entry["content"][:60]
            print(f"  [{i+1}/{len(entries)}] DRY-RUN -> {coll}: {preview}...")
            stats["success"] += 1
            continue

        try:
            result = qdrant_upsert(entry, coll)
            point_id = result.get("id", "?")[:12]
            preview = entry["content"][:50]
            print(f"  [{i+1}/{len(entries)}] -> {coll} [{point_id}]: {preview}...")
            stats["success"] += 1
            stats["results"].append(result)
        except Exception as e:
            print(f"  [{i+1}/{len(entries)}] 失败: {e}")
            stats["failed"] += 1

    return stats


# ── 交互式单条添加 ───────────────────────────────────────────

def interactive_add():
    """交互式添加单条知识"""
    print("=== 交互式添加知识条目 ===\n")

    content = input("内容 (必填): ").strip()
    if not content:
        print("取消：内容不能为空。")
        return

    category = input("分类 [tech/business/sop, 默认 tech]: ").strip() or "tech"
    score_str = input("评分 [0-10, 默认 5]: ").strip()
    score = int(score_str) if score_str else 5
    conf_str = input("置信度 [0-1, 默认 0.8]: ").strip()
    confidence = float(conf_str) if conf_str else 0.8
    tags_str = input("标签 (逗号分隔): ").strip()
    tags = [t.strip() for t in tags_str.split(",")] if tags_str else []
    coll = input("Collection [ai/ecommerce, 默认按分类]: ").strip()

    entry = {
        "content": content,
        "score": score,
        "confidence": confidence,
        "category": category,
        "tags": tags,
    }

    target_coll = coll if coll else ("ecommerce" if category == "business" else "ai")
    result = qdrant_upsert(entry, target_coll)
    print(f"\n写入成功: {result['id']} -> {target_coll}")


def list_existing():
    """列出已有的知识条目（最近 20 条）"""
    print("=== 已有知识条目 (最近20条) ===\n")
    for coll in ("ai", "ecommerce"):
        try:
            results = qdrant_search("架构 启动 电商", coll, limit=10, score_threshold=0.0)
            if results:
                print(f"[{coll}] {len(results)} 条结果:")
                for r in results:
                    payload = r.get("payload", {})
                    print(f"  - [{payload.get('category', '?')}] {payload.get('content', '')[:80]}...")
                print()
        except Exception as e:
            print(f"[{coll}] 查询失败: {e}\n")


# ── 主入口 ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="种子知识管理工具")
    parser.add_argument("--batch", type=str, metavar="FILE",
                        help="从 JSON/JSONL 文件批量导入知识")
    parser.add_argument("--add", action="store_true",
                        help="交互式添加单条知识")
    parser.add_argument("--dry-run", action="store_true",
                        help="预览而不实际写入")
    parser.add_argument("--list", action="store_true",
                        help="列出已有知识条目")
    parser.add_argument("--coll", type=str, default=None,
                        help="指定目标 collection (ai/ecommerce)")
    args = parser.parse_args()

    # 健康检查
    if not qdrant_health():
        print("错误: Qdrant 不可达，请先启动 Qdrant 服务。")
        sys.exit(1)

    print(f"Qdrant: 可达 (http://127.0.0.1:6333)")

    # 列出模式
    if args.list:
        list_existing()
        return

    # 交互式添加
    if args.add:
        interactive_add()
        return

    # 批量导入模式
    if args.batch:
        filepath = args.batch
        if not os.path.exists(filepath):
            print(f"错误: 文件不存在 — {filepath}")
            sys.exit(1)

        print(f"\n从文件导入: {filepath}")
        entries = load_knowledge_from_file(filepath)
        print(f"加载 {len(entries)} 条知识")
        stats = batch_upsert(entries, collection=args.coll, dry_run=args.dry_run)
        _print_stats(stats, args.dry_run)
        return

    # 默认模式：写入内置种子知识 + 数据目录
    print("\n=== 内置种子知识 ===")
    stats_builtin = batch_upsert(BUILTIN_ENTRIES, collection=args.coll, dry_run=args.dry_run)

    # 尝试从数据目录加载额外知识
    data_dir = find_data_dir()
    if data_dir:
        print(f"\n=== 数据目录: {data_dir} ===")
        extra_entries = collect_knowledge_from_data_dir()
        if extra_entries:
            print(f"\n共从数据目录加载 {len(extra_entries)} 条额外知识")
            stats_extra = batch_upsert(extra_entries, collection=args.coll, dry_run=args.dry_run)
            total = stats_builtin["total"] + stats_extra["total"]
            success = stats_builtin["success"] + stats_extra["success"]
            failed = stats_builtin["failed"] + stats_extra["failed"]
            skipped = stats_builtin["skipped"] + stats_extra["skipped"]
            _print_stats({"total": total, "success": success, "failed": failed, "skipped": skipped}, args.dry_run)
            return
    else:
        print("\n(提示: 创建 data/ 目录并放入 .json 知识文件可批量导入)")

    _print_stats(stats_builtin, args.dry_run)


def _print_stats(stats, dry_run=False):
    """打印统计信息"""
    mode = "预览" if dry_run else "写入"
    print(f"\n{mode}完成: {stats['total']} 条, "
          f"成功 {stats['success']}, "
          f"失败 {stats['failed']}, "
          f"跳过 {stats['skipped']}")


if __name__ == "__main__":
    main()
