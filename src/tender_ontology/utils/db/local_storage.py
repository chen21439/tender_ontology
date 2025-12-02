"""
本地文件存储服务

在没有 MySQL 的环境下，使用 JSON 文件存储任务列表
通过环境变量 STORAGE_MODE 控制：
- STORAGE_MODE=mysql (默认): 使用 MySQL 数据库
- STORAGE_MODE=local: 使用本地 JSON 文件
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from threading import Lock

# 存储模式
STORAGE_MODE = os.environ.get("STORAGE_MODE", "mysql").lower()


def is_local_mode() -> bool:
    """判断是否为本地存储模式"""
    return STORAGE_MODE == "local"


class LocalTaskStorage:
    """本地任务存储（使用 JSON 文件）"""

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._file_lock = Lock()
        self._tasks_file = self._get_tasks_file_path()
        self._ensure_file_exists()

    def _get_tasks_file_path(self) -> Path:
        """获取任务文件路径"""
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent.parent.parent
        static_upload = project_root / "static" / "upload"
        static_upload.mkdir(parents=True, exist_ok=True)
        return static_upload / "tasks.json"

    def _ensure_file_exists(self):
        """确保任务文件存在"""
        if not self._tasks_file.exists():
            self._save_tasks({"tasks": [], "next_id": 1})

    def _load_tasks(self) -> Dict[str, Any]:
        """加载任务数据"""
        with self._file_lock:
            try:
                content = self._tasks_file.read_text(encoding='utf-8')
                return json.loads(content)
            except Exception:
                return {"tasks": [], "next_id": 1}

    def _save_tasks(self, data: Dict[str, Any]):
        """保存任务数据"""
        with self._file_lock:
            self._tasks_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )

    def create_task(
        self,
        file_name: str,
        file_path: Optional[str] = None,
        project_name: Optional[str] = None,
        project_code: Optional[str] = None,
        procurement_method: Optional[str] = None,
        project_type: Optional[str] = None,
        overview: Optional[str] = None,
        app_id: Optional[str] = None,
        create_user: Optional[str] = None,
        create_user_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        创建新任务

        Returns:
            任务数据字典
        """
        data = self._load_tasks()

        task_id = data["next_id"]
        now = datetime.now()

        task = {
            "id": task_id,
            "file_id": f"file_{task_id}",
            "file_name": file_name,
            "file_path": file_path,
            "project_name": project_name,
            "project_code": project_code,
            "procurement_method": procurement_method,
            "project_type": project_type,
            "overview": overview,
            "app_id": app_id,
            "create_user": create_user,
            "create_user_name": create_user_name,
            "review_status": 3,  # 解析中
            "review_result": None,
            "create_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "update_time": now.strftime("%Y-%m-%d %H:%M:%S")
        }

        data["tasks"].append(task)
        data["next_id"] = task_id + 1
        self._save_tasks(data)

        print(f"[LocalStorage] 任务创建成功: {task_id}")
        return task

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务

        Args:
            task_id: 任务ID

        Returns:
            任务数据或 None
        """
        data = self._load_tasks()
        try:
            tid = int(task_id)
            for task in data["tasks"]:
                if task["id"] == tid:
                    return task
        except ValueError:
            pass
        return None

    def update_task_status(
        self,
        task_id: int,
        status: int,
        message: Optional[str] = None
    ):
        """
        更新任务状态

        Args:
            task_id: 任务ID
            status: 状态码 (1=待审查, 2=完成, 3=解析中, 4=失败)
            message: 状态消息
        """
        data = self._load_tasks()
        for task in data["tasks"]:
            if task["id"] == task_id:
                task["review_status"] = status
                task["update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                break
        self._save_tasks(data)
        print(f"[LocalStorage] 任务状态更新: {task_id} -> {status}")

    def update_task_file_path(self, task_id: int, file_path: str, file_name: Optional[str] = None):
        """
        更新任务文件路径

        Args:
            task_id: 任务ID
            file_path: 文件路径
            file_name: 文件名
        """
        data = self._load_tasks()
        for task in data["tasks"]:
            if task["id"] == task_id:
                task["file_path"] = file_path
                if file_name:
                    task["file_name"] = file_name
                task["update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                break
        self._save_tasks(data)

    def get_tasks_page(
        self,
        page_num: int = 1,
        page_size: int = 10
    ) -> Dict[str, Any]:
        """
        分页获取任务列表

        Args:
            page_num: 页码（从1开始）
            page_size: 每页数量

        Returns:
            分页数据
        """
        data = self._load_tasks()
        tasks = data["tasks"]

        # 按创建时间倒序
        tasks_sorted = sorted(tasks, key=lambda x: x["create_time"], reverse=True)

        total = len(tasks_sorted)
        pages = (total + page_size - 1) // page_size if total > 0 else 1
        offset = (page_num - 1) * page_size

        page_tasks = tasks_sorted[offset:offset + page_size]

        # 转换为响应格式
        data_list = []
        for task in page_tasks:
            review_progress = 100 if task["review_status"] == 2 else 0
            data_list.append({
                "taskId": task["id"],
                "fileId": task["file_id"],
                "fileName": task["file_name"],
                "projectName": task["project_name"],
                "projectCode": task["project_code"],
                "reviewStatus": task["review_status"],
                "reviewResult": task["review_result"],
                "createTime": task["create_time"],
                "createUserName": task["create_user_name"],
                "reviewProgress": review_progress
            })

        return {
            "total": total,
            "pageSize": page_size,
            "pageTotal": pages,
            "pageNum": page_num,
            "dataList": data_list
        }

    def delete_task(self, task_id: str) -> bool:
        """
        删除任务

        Args:
            task_id: 任务ID

        Returns:
            是否删除成功
        """
        data = self._load_tasks()
        try:
            tid = int(task_id)
            original_len = len(data["tasks"])
            data["tasks"] = [t for t in data["tasks"] if t["id"] != tid]
            if len(data["tasks"]) < original_len:
                self._save_tasks(data)
                print(f"[LocalStorage] 任务删除成功: {task_id}")
                return True
        except ValueError:
            pass
        return False


# 全局实例
_local_storage = None


def get_local_storage() -> LocalTaskStorage:
    """获取本地存储实例"""
    global _local_storage
    if _local_storage is None:
        _local_storage = LocalTaskStorage()
    return _local_storage
