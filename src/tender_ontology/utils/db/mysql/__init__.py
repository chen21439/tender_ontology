"""
MySQL 数据库工具模块

提供 SQLAlchemy 2.x 的封装，支持同步和异步操作
"""

from .mysql_util import MySQLUtil
from .models import Base, ComplianceFileTask, PDFDocument, ProcessingLog
from .compliance_service import ComplianceService
from .connection import DatabaseManager, get_db, init_db, close_db

__all__ = [
    "MySQLUtil",
    "Base",
    "ComplianceFileTask",
    "PDFDocument",
    "ProcessingLog",
    "ComplianceService",
    # 全局连接管理
    "DatabaseManager",
    "get_db",
    "init_db",
    "close_db",
]