"""
全局数据库连接管理器

单例模式，项目启动时初始化，关闭时销毁
"""

import os
import logging
from typing import Optional

from .mysql_util import MySQLUtil

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    数据库连接管理器（单例模式）

    在应用启动时调用 init()，关闭时调用 close()
    """

    _instance: Optional[MySQLUtil] = None
    _initialized: bool = False

    @classmethod
    def init(
        cls,
        host: str = None,
        port: int = None,
        user: str = None,
        password: str = None,
        database: str = None,
        charset: str = "utf8mb4",
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_timeout: int = 30,
        echo: bool = False
    ) -> MySQLUtil:
        """
        初始化数据库连接池（只初始化一次）

        可以通过参数传入，也可以通过环境变量配置：
        - MYSQL_HOST
        - MYSQL_PORT
        - MYSQL_USER
        - MYSQL_PASSWORD
        - MYSQL_DATABASE

        Returns:
            MySQLUtil 实例
        """
        if cls._initialized and cls._instance is not None:
            logger.debug("[MySQL] 连接池已存在，复用现有连接")
            return cls._instance

        # 从环境变量或参数获取配置
        config = {
            "host": host or os.getenv("MYSQL_HOST", "172.16.0.116"),
            "port": port or int(os.getenv("MYSQL_PORT", "3306")),
            "user": user or os.getenv("MYSQL_USER", "root"),
            "password": password or os.getenv("MYSQL_PASSWORD", "123456"),
            "database": database or os.getenv("MYSQL_DATABASE", "tender_compliance"),
            "charset": charset,
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_timeout": pool_timeout,
            "echo": echo
        }

        cls._instance = MySQLUtil(**config)
        cls._initialized = True

        print(f"[MySQL] 全局连接池已初始化: {config['host']}:{config['port']}/{config['database']}")
        print(f"[MySQL] 连接池配置: pool_size={pool_size}, max_overflow={max_overflow}")

        return cls._instance

    @classmethod
    def get_instance(cls) -> MySQLUtil:
        """
        获取数据库连接实例

        如果未初始化，会使用默认配置自动初始化

        Returns:
            MySQLUtil 实例
        """
        if cls._instance is None or not cls._initialized:
            return cls.init()
        return cls._instance

    @classmethod
    def close(cls):
        """
        关闭数据库连接池

        通常在应用关闭时调用
        """
        if cls._instance is not None:
            cls._instance.close()
            cls._instance = None
            cls._initialized = False
            logger.info("[MySQL] 全局连接池已关闭")

    @classmethod
    def is_initialized(cls) -> bool:
        """检查连接池是否已初始化"""
        return cls._initialized and cls._instance is not None


# 便捷函数
def get_db() -> MySQLUtil:
    """
    获取数据库连接实例的便捷函数

    用法:
        from tender_ontology.utils.db.mysql import get_db

        db = get_db()
        with db.get_session() as session:
            # 执行数据库操作
            pass

    Returns:
        MySQLUtil 实例
    """
    return DatabaseManager.get_instance()


def init_db(**kwargs) -> MySQLUtil:
    """
    初始化数据库连接的便捷函数

    Returns:
        MySQLUtil 实例
    """
    return DatabaseManager.init(**kwargs)


def close_db():
    """关闭数据库连接的便捷函数"""
    DatabaseManager.close()