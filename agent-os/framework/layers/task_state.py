"""TaskState 任务状态机 — 持久化 + 断点续跑"""
import os
import sys
import json
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.paths import state_file  # noqa: E402

_STATES_VALID = {
    "CREATED", "RUNNING", "WAITING", "RESUMING", "DONE", "FAILED", "RETRYING", "ABORTED",
}

_TRANSITIONS = {
    "CREATED":   ["RUNNING"],
    "RUNNING":   ["DONE", "FAILED", "WAITING"],
    "WAITING":   ["RESUMING", "ABORTED"],
    "RESUMING":  ["RUNNING", "FAILED"],
    "FAILED":    ["RETRYING", "ABORTED"],
    "RETRYING":  ["RUNNING", "ABORTED"],
    "DONE":      [],
    "ABORTED":   [],
}

_DEFAULT_PATH = state_file("task-states.jsonl")


class TaskState:
    def __init__(self, storage_path=None):
        self.storage_path = storage_path or _DEFAULT_PATH
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        if not os.path.exists(self.storage_path):
            open(self.storage_path, "w").close()

    def _append(self, record):
        with open(self.storage_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _read_all(self):
        records = []
        with open(self.storage_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def get_latest(self, task_id):
        """获取任务最新状态"""
        latest = None
        for rec in self._read_all():
            if rec.get("taskId") == task_id:
                latest = rec
        return latest

    def create_task(self, task_id, context=None):
        """创建新任务"""
        existing = self.get_latest(task_id)
        if existing:
            return {"error": f"任务 {task_id} 已存在，当前状态: {existing.get('state')}"}

        record = {
            "taskId": task_id,
            "state": "CREATED",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "context": context or {},
        }
        self._append(record)
        return record

    def update_state(self, task_id, new_state, meta=None):
        """更新任务状态

        Args:
            new_state: 目标状态
            meta: 额外信息（currentStep, error, retryCount 等）
        """
        if new_state not in _STATES_VALID:
            return {"error": f"无效状态: {new_state}"}

        latest = self.get_latest(task_id)
        if not latest:
            return {"error": f"任务 {task_id} 不存在"}

        current = latest.get("state")
        allowed = _TRANSITIONS.get(current, [])
        if new_state not in allowed:
            return {"error": f"不允许从 {current} 转换到 {new_state}，允许: {allowed}"}

        record = {
            "taskId": task_id,
            "state": new_state,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        if meta:
            record.update(meta)
        self._append(record)
        return record

    def resume_incomplete_tasks(self):
        """查找所有未完成任务（非 DONE / ABORTED），返回列表"""
        latest_by_task = {}
        for rec in self._read_all():
            tid = rec.get("taskId")
            if tid:
                latest_by_task[tid] = rec

        incomplete = []
        for tid, rec in latest_by_task.items():
            state = rec.get("state")
            if state not in ("DONE", "ABORTED"):
                incomplete.append(rec)
        return incomplete
