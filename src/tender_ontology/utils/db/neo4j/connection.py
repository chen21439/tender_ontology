"""
全局 Neo4j 连接管理器

单例模式，项目启动时初始化，关闭时销毁
"""

import os
import logging
from typing import Optional

from .neo4j_util import Neo4jUtil

logger = logging.getLogger(__name__)


class Neo4jManager:
    """
    Neo4j 连接管理器（单例模式）

    在应用启动时调用 init()，关闭时调用 close()
    """

    _instance: Optional[Neo4jUtil] = None
    _initialized: bool = False

    @classmethod
    def init(
        cls,
        uri: str = None,
        user: str = None,
        password: str = None,
        database: str = None,
        max_connection_pool_size: int = 100,
        connection_timeout: float = 30.0,
        max_transaction_retry_time: float = 30.0,
        encrypted: bool = False
    ) -> Neo4jUtil:
        """
        初始化 Neo4j 连接池（只初始化一次）

        可以通过参数传入，也可以通过环境变量配置：
        - NEO4J_URI
        - NEO4J_USER
        - NEO4J_PASSWORD
        - NEO4J_DATABASE

        Returns:
            Neo4jUtil 实例
        """
        if cls._initialized and cls._instance is not None:
            logger.debug("[Neo4j] 连接池已存在，复用现有连接")
            return cls._instance

        # 从 settings 或参数获取配置
        from tender_ontology.config.settings import settings
        config = {
            "uri": uri or settings.neo4j_uri,
            "user": user or settings.neo4j_user,
            "password": password or settings.neo4j_password,
            "database": database or settings.neo4j_database,
            "max_connection_pool_size": max_connection_pool_size,
            "connection_timeout": connection_timeout if connection_timeout else 5.0,  # 默认 5 秒
            "max_transaction_retry_time": max_transaction_retry_time if max_transaction_retry_time else 5.0,
            "encrypted": encrypted
        }

        cls._instance = Neo4jUtil(**config)
        cls._initialized = True

        print(f"[Neo4j] 全局连接池已初始化: {config['uri']}, 数据库: {config['database']}")
        print(f"[Neo4j] 连接池配置: max_pool_size={max_connection_pool_size}, timeout={connection_timeout}s")

        return cls._instance

    @classmethod
    def get_instance(cls) -> Neo4jUtil:
        """
        获取 Neo4j 连接实例

        如果未初始化，会使用默认配置自动初始化

        Returns:
            Neo4jUtil 实例
        """
        if cls._instance is None or not cls._initialized:
            return cls.init()
        return cls._instance

    @classmethod
    def close(cls):
        """
        关闭 Neo4j 连接池

        通常在应用关闭时调用
        """
        if cls._instance is not None:
            cls._instance.close()
            cls._instance = None
            cls._initialized = False
            logger.info("[Neo4j] 全局连接池已关闭")

    @classmethod
    def is_initialized(cls) -> bool:
        """检查连接池是否已初始化"""
        return cls._initialized and cls._instance is not None


# 便捷函数
def get_neo4j() -> Neo4jUtil:
    """
    获取 Neo4j 连接实例的便捷函数

    用法:
        from tender_ontology.utils.db.neo4j import get_neo4j

        db = get_neo4j()
        nodes = db.find_nodes_by_label("Person")

    Returns:
        Neo4jUtil 实例
    """
    return Neo4jManager.get_instance()


def init_neo4j(**kwargs) -> Neo4jUtil:
    """
    初始化 Neo4j 连接的便捷函数

    Returns:
        Neo4jUtil 实例
    """
    return Neo4jManager.init(**kwargs)


def close_neo4j():
    """关闭 Neo4j 连接的便捷函数"""
    Neo4jManager.close()