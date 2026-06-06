"""初始化 TaskState 持久化文件"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from layers.task_state import TaskState


def main():
    ts = TaskState()
    print(f"TaskState 文件已创建: {ts.storage_path}")
    print(f"当前未完成任务数: {len(ts.resume_incomplete_tasks())}")


if __name__ == "__main__":
    main()
