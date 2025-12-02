"""
数据库/存储模块

支持两种存储模式：
- STORAGE_MODE=mysql (默认): 使用 MySQL 数据库
- STORAGE_MODE=local: 使用本地 JSON 文件

通过环境变量 STORAGE_MODE 控制存储模式
"""

from .local_storage import is_local_mode, get_local_storage, LocalTaskStorage

__all__ = ["is_local_mode", "get_local_storage", "LocalTaskStorage"]
