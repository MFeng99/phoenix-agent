"""Risk Assessment 风险评估层 — 八维风险分级 + 触发词预检

对应文档：双Agent风险分级框架设计.md 第二节
"""

# ── 触发词库 ─────────────────────────────────────────────────

HIGH_TRIGGERS = {
    # 对外通信类
    "发送", "发消息", "发邮件", "通知", "推送", "发布", "公开",
    "reply", "send", "notify", "publish", "post",
    # 删除/破坏类
    "删除", "卸载", "清空", "格式化", "永久删除", "drop",
    "delete", "remove", "uninstall", "format", "purge",
    # 金融/合同类
    "支付", "付款", "转账", "扣款", "购买", "订阅", "合同", "签约", "确认支付",
    "pay", "purchase", "subscribe", "contract", "charge",
    # 系统/生产类
    "部署", "上线", "重启服务", "迁移", "生产环境", "正式环境",
    "deploy", "production", "migrate",
    # Shell/代码执行类
    "执行命令", "运行脚本", "sudo", "管理员权限", "系统配置",
    "exec", "run command", "administrator", "registry",
    # 浏览器提交类
    "提交表单", "确认订单", "下单",
    "submit", "checkout", "place order",
    # Cron/自动化类
    "定时", "计划任务", "每天自动", "无人值守", "循环执行",
    "schedule", "cron", "automated", "unattended",
    # 远程控制类
    "控制设备", "远程", "节点", "GPS", "摄像头",
    "remote", "device", "node",
}

MEDIUM_TRIGGERS = {
    # 文件操作类
    "写入", "修改", "更新文件", "保存", "生成报告", "创建文档",
    "write", "edit", "update", "save", "generate",
    # 浏览器操作类
    "截图", "打开网页", "点击", "填写", "浏览",
    "screenshot", "open", "click", "fill", "browse",
    # 邮件读取类
    "读取邮件", "查看消息", "收件箱",
    "read mail", "inbox",
}

LOW_TRIGGERS = {
    "查询", "搜索", "查看", "列出", "读取", "计算", "分析",
    "query", "search", "view", "list", "read", "calculate", "analyze",
}

# ── 八维风险评估维度 ─────────────────────────────────────────

DIMENSIONS = [
    "impact_scope",       # 影响范围
    "data_sensitivity",   # 数据敏感性
    "reversibility",      # 操作可逆性
    "external_visibility",# 外部可见性
    "compliance_risk",    # 合规/法律风险
    "resource_cost",      # 资源消耗
    "automation_chain",   # 自动化链风险 (v3.0 新增)
    "system_impact",      # 系统级影响 (v3.0 新增)
]

def trigger_word_check(text):
    """触发词预检：扫描文本中的风险触发词

    Args:
        text: 用户指令或操作描述

    Returns:
        {"level": "HIGH"|"MEDIUM"|"LOW"|None, "matched_words": list}
    """
    if not text:
        return {"level": None, "matched_words": []}

    text_lower = text.lower()
    matched_high = [w for w in HIGH_TRIGGERS if w.lower() in text_lower]
    matched_medium = [w for w in MEDIUM_TRIGGERS if w.lower() in text_lower]
    matched_low = [w for w in LOW_TRIGGERS if w.lower() in text_lower]

    if matched_high:
        return {"level": "HIGH", "matched_words": matched_high}
    if matched_medium:
        return {"level": "MEDIUM", "matched_words": matched_medium}
    if matched_low:
        return {"level": "LOW", "matched_words": matched_low}
    return {"level": None, "matched_words": []}


def assess_risk(operation, user_text=None):
    """八维风险评估

    决策规则：
      八维全部 LOW  → LOW（自动执行）
      任一维度 MEDIUM → MEDIUM（口头确认）
      任一维度 HIGH → HIGH（强制人工确认）
      不确定 → 默认升级为人工审核

    Args:
        operation: 操作名（如 "exec", "browser", "web_search"）
        user_text: 用户原始指令（用于触发词预检）

    Returns:
        {
            "level": "LOW"|"MEDIUM"|"HIGH",
            "trigger_check": dict,
            "dimensions": dict,
            "reason": str
        }
    """
    # ① 触发词预检
    trigger = trigger_word_check(user_text or "")
    if trigger["level"] == "HIGH":
        return {
            "level": "HIGH",
            "trigger_check": trigger,
            "dimensions": None,
            "reason": f"命中 HIGH 触发词: {', '.join(trigger['matched_words'][:3])}",
        }

    # ② 八维评估
    dims = OPERATION_DEFAULTS.get(operation, OPERATION_DEFAULTS.get("read"))
    max_level = "LOW"
    reason_parts = []

    for dim, level in dims.items():
        if level == "HIGH":
            max_level = "HIGH"
            reason_parts.append(f"{DIM_NAMES[dim]}=HIGH")
        elif level == "MEDIUM" and max_level != "HIGH":
            max_level = "MEDIUM"
            reason_parts.append(f"{DIM_NAMES[dim]}=MEDIUM")

    # ③ 触发词中风险升维
    if trigger["level"] == "MEDIUM" and max_level == "LOW":
        max_level = "MEDIUM"
        reason_parts.append(f"触发词: {', '.join(trigger['matched_words'][:3])}")

    return {
        "level": max_level,
        "trigger_check": trigger,
        "dimensions": dims,
        "reason": "; ".join(reason_parts) if reason_parts else "全部维度 LOW",
    }


# ── 维度名映射 ──────────────────────────────────────────────

DIM_NAMES = {
    "impact_scope": "影响范围",
    "data_sensitivity": "数据敏感性",
    "reversibility": "操作可逆性",
    "external_visibility": "外部可见性",
    "compliance_risk": "合规风险",
    "resource_cost": "资源消耗",
    "automation_chain": "自动化链风险",
    "system_impact": "系统级影响",
}

# ── 操作默认值映射 ──────────────────────────────────────────

OPERATION_DEFAULTS = {
    "read": {
        "impact_scope": "LOW", "data_sensitivity": "LOW",
        "reversibility": "LOW", "external_visibility": "LOW",
        "compliance_risk": "LOW", "resource_cost": "LOW",
        "automation_chain": "LOW", "system_impact": "LOW",
    },
    "write": {
        "impact_scope": "MEDIUM", "data_sensitivity": "MEDIUM",
        "reversibility": "MEDIUM", "external_visibility": "LOW",
        "compliance_risk": "LOW", "resource_cost": "LOW",
        "automation_chain": "LOW", "system_impact": "LOW",
    },
    "edit": {
        "impact_scope": "MEDIUM", "data_sensitivity": "MEDIUM",
        "reversibility": "MEDIUM", "external_visibility": "LOW",
        "compliance_risk": "LOW", "resource_cost": "LOW",
        "automation_chain": "LOW", "system_impact": "LOW",
    },
    "exec": {
        "impact_scope": "HIGH", "data_sensitivity": "MEDIUM",
        "reversibility": "HIGH", "external_visibility": "LOW",
        "compliance_risk": "MEDIUM", "resource_cost": "MEDIUM",
        "automation_chain": "MEDIUM", "system_impact": "HIGH",
    },
    "browser": {
        "impact_scope": "MEDIUM", "data_sensitivity": "MEDIUM",
        "reversibility": "MEDIUM", "external_visibility": "MEDIUM",
        "compliance_risk": "LOW", "resource_cost": "LOW",
        "automation_chain": "LOW", "system_impact": "LOW",
    },
    "web_search": {
        "impact_scope": "LOW", "data_sensitivity": "LOW",
        "reversibility": "LOW", "external_visibility": "LOW",
        "compliance_risk": "LOW", "resource_cost": "LOW",
        "automation_chain": "LOW", "system_impact": "LOW",
    },
    "web_fetch": {
        "impact_scope": "LOW", "data_sensitivity": "LOW",
        "reversibility": "LOW", "external_visibility": "LOW",
        "compliance_risk": "LOW", "resource_cost": "LOW",
        "automation_chain": "LOW", "system_impact": "LOW",
    },
    "cron": {
        "impact_scope": "HIGH", "data_sensitivity": "MEDIUM",
        "reversibility": "MEDIUM", "external_visibility": "MEDIUM",
        "compliance_risk": "MEDIUM", "resource_cost": "MEDIUM",
        "automation_chain": "HIGH", "system_impact": "MEDIUM",
    },
    "message": {
        "impact_scope": "HIGH", "data_sensitivity": "MEDIUM",
        "reversibility": "HIGH", "external_visibility": "HIGH",
        "compliance_risk": "HIGH", "resource_cost": "LOW",
        "automation_chain": "MEDIUM", "system_impact": "LOW",
    },
    "gateway": {
        "impact_scope": "HIGH", "data_sensitivity": "HIGH",
        "reversibility": "HIGH", "external_visibility": "LOW",
        "compliance_risk": "MEDIUM", "resource_cost": "HIGH",
        "automation_chain": "LOW", "system_impact": "HIGH",
    },
    "nodes": {
        "impact_scope": "HIGH", "data_sensitivity": "HIGH",
        "reversibility": "HIGH", "external_visibility": "MEDIUM",
        "compliance_risk": "HIGH", "resource_cost": "HIGH",
        "automation_chain": "MEDIUM", "system_impact": "HIGH",
    },
    "sessions_spawn": {
        "impact_scope": "MEDIUM", "data_sensitivity": "MEDIUM",
        "reversibility": "MEDIUM", "external_visibility": "LOW",
        "compliance_risk": "LOW", "resource_cost": "MEDIUM",
        "automation_chain": "MEDIUM", "system_impact": "LOW",
    },
    "sessions_send": {
        "impact_scope": "MEDIUM", "data_sensitivity": "MEDIUM",
        "reversibility": "HIGH", "external_visibility": "LOW",
        "compliance_risk": "LOW", "resource_cost": "LOW",
        "automation_chain": "LOW", "system_impact": "LOW",
    },
}
