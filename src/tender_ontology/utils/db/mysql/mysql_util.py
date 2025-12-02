"""
MySQL 工具类

基于 SQLAlchemy 2.x，提供同步数据库操作
"""

from sqlalchemy import create_engine, text, Engine, select, insert, update, delete
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool
from typing import List, Dict, Any, Optional, Type, TypeVar
from contextlib import contextmanager
import logging

from .models import Base

# 泛型类型变量 (用于 ORM 类型提示)
T = TypeVar('T', bound=Base)

logger = logging.getLogger(__name__)


class MySQLUtil:
    """
    MySQL 工具类 - 基于 SQLAlchemy 2.x

    特性:
    - 自动连接池管理 (QueuePool)
    - 事务自动提交/回滚
    - 支持 Core SQL 和 ORM 两种风格
    - 连接健康检查 (pool_pre_ping)
    """

    def __init__(self,
                 host: str = "localhost",
                 port: int = 3306,
                 user: str = "root",
                 password: str = "",
                 database: str = "test",
                 charset: str = "utf8mb4",
                 pool_size: int = 10,
                 max_overflow: int = 20,
                 pool_timeout: int = 30,
                 echo: bool = False):
        """
        初始化 MySQL 连接

        Args:
            host: 数据库主机地址
            port: 数据库端口
            user: 数据库用户名
            password: 数据库密码
            database: 数据库名称
            charset: 字符集 (默认 utf8mb4)
            pool_size: 连接池大小 (默认 10)
            max_overflow: 连接池最大溢出 (默认 20)
            pool_timeout: 连接超时时间 (秒, 默认 30)
            echo: 是否打印 SQL 语句 (默认 False)
        """
        self.host = host
        self.port = port
        self.user = user
        self.database = database

        # 构建连接 URL
        # 使用 PyMySQL 驱动: mysql+pymysql://
        # 使用 mysqlclient 驱动: mysql+mysqldb://
        connection_url = (
            f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
            f"?charset={charset}"
        )

        # 创建引擎
        self.engine: Engine = create_engine(
            connection_url,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_pre_ping=True,  # 连接健康检查
            echo=echo,           # 打印 SQL (调试用)
            future=True          # 使用 2.0 风格 API
        )

        # 创建 Session 工厂
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            future=True
        )

        logger.info(f"[MySQL] 已连接到 {host}:{port}/{database}")

    def create_tables(self, drop_existing: bool = False):
        """
        创建所有表 (基于 models.py 中定义的模型)

        Args:
            drop_existing: 是否先删除已存在的表 (默认 False)
        """
        if drop_existing:
            logger.warning("[MySQL] 删除所有表...")
            Base.metadata.drop_all(self.engine)

        logger.info("[MySQL] 创建表...")
        Base.metadata.create_all(self.engine)
        logger.info("[MySQL] ✓ 表创建完成")

    @contextmanager
    def get_session(self):
        """
        获取数据库会话 (自动管理事务)

        用法:
            with mysql_util.get_session() as session:
                user = session.query(User).filter_by(id=1).first()
                session.add(new_user)
                # 自动提交

        Yields:
            Session: SQLAlchemy Session 对象
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"[MySQL] 事务回滚: {e}")
            raise
        finally:
            session.close()

    def execute_raw_sql(self, sql: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        执行原生 SQL 查询 (Core SQL 风格)

        Args:
            sql: SQL 语句 (支持命名参数, 如 :param_name)
            params: 参数字典 (默认 None)

        Returns:
            查询结果列表 (字典格式)

        示例:
            rows = mysql_util.execute_raw_sql(
                "SELECT * FROM users WHERE status = :status",
                {"status": "active"}
            )
        """
        with self.engine.begin() as conn:
            result = conn.execute(text(sql), params or {})
            if result.returns_rows:
                # 将 Row 对象转换为字典
                return [dict(row._mapping) for row in result.all()]
            else:
                return []

    def execute_insert(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        """
        执行插入语句 (Core SQL 风格)

        Args:
            sql: INSERT 语句
            params: 参数字典

        Returns:
            受影响的行数
        """
        with self.engine.begin() as conn:
            result = conn.execute(text(sql), params or {})
            return result.rowcount

    def execute_update(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        """
        执行更新语句 (Core SQL 风格)

        Args:
            sql: UPDATE 语句
            params: 参数字典

        Returns:
            受影响的行数
        """
        with self.engine.begin() as conn:
            result = conn.execute(text(sql), params or {})
            return result.rowcount

    def execute_delete(self, sql: str, params: Optional[Dict[str, Any]] = None) -> int:
        """
        执行删除语句 (Core SQL 风格)

        Args:
            sql: DELETE 语句
            params: 参数字典

        Returns:
            受影响的行数
        """
        with self.engine.begin() as conn:
            result = conn.execute(text(sql), params or {})
            return result.rowcount

    # ==================== ORM 风格方法 ====================

    def get_by_id(self, model: Type[T], id_value: Any) -> Optional[T]:
        """
        根据主键查询单条记录 (ORM 风格)

        Args:
            model: ORM 模型类 (如 User)
            id_value: 主键值

        Returns:
            模型实例或 None

        示例:
            user = mysql_util.get_by_id(User, 1)
        """
        with self.get_session() as session:
            return session.get(model, id_value)

    def get_all(self, model: Type[T], limit: Optional[int] = None) -> List[T]:
        """
        查询所有记录 (ORM 风格)

        Args:
            model: ORM 模型类
            limit: 限制返回数量 (默认 None，返回所有)

        Returns:
            模型实例列表

        示例:
            users = mysql_util.get_all(User, limit=100)
        """
        with self.get_session() as session:
            stmt = select(model)
            if limit:
                stmt = stmt.limit(limit)
            result = session.execute(stmt)
            return list(result.scalars().all())

    def filter_by(self, model: Type[T], **kwargs) -> List[T]:
        """
        根据条件查询 (ORM 风格)

        Args:
            model: ORM 模型类
            **kwargs: 查询条件 (字段名=值)

        Returns:
            模型实例列表

        示例:
            active_users = mysql_util.filter_by(User, status="active", role="admin")
        """
        with self.get_session() as session:
            stmt = select(model).filter_by(**kwargs)
            result = session.execute(stmt)
            return list(result.scalars().all())

    def insert_one(self, instance: Base) -> Base:
        """
        插入单条记录 (ORM 风格)

        Args:
            instance: ORM 模型实例

        Returns:
            插入后的模型实例 (包含自增 ID)

        示例:
            user = User(name="Alice", status="active")
            saved_user = mysql_util.insert_one(user)
            print(saved_user.id)  # 自增 ID
        """
        with self.get_session() as session:
            session.add(instance)
            session.flush()  # 刷新以获取自增 ID
            session.refresh(instance)
            session.expunge(instance)  # 从 session 分离,使对象可以在 session 外使用
            return instance

    def insert_many(self, instances: List[Base]) -> int:
        """
        批量插入记录 (ORM 风格)

        Args:
            instances: ORM 模型实例列表

        Returns:
            插入的记录数
        """
        with self.get_session() as session:
            session.add_all(instances)
            session.flush()
            return len(instances)

    def update_by_id(self, model: Type[T], id_value: Any, **kwargs) -> bool:
        """
        根据主键更新记录 (ORM 风格)

        Args:
            model: ORM 模型类
            id_value: 主键值
            **kwargs: 要更新的字段 (字段名=值)

        Returns:
            是否更新成功

        示例:
            success = mysql_util.update_by_id(User, 1, status="inactive", updated_at=datetime.now())
        """
        with self.get_session() as session:
            instance = session.get(model, id_value)
            if instance:
                for key, value in kwargs.items():
                    setattr(instance, key, value)
                return True
            return False

    def delete_by_id(self, model: Type[T], id_value: Any) -> bool:
        """
        根据主键删除记录 (ORM 风格)

        Args:
            model: ORM 模型类
            id_value: 主键值

        Returns:
            是否删除成功

        示例:
            success = mysql_util.delete_by_id(User, 1)
        """
        with self.get_session() as session:
            instance = session.get(model, id_value)
            if instance:
                session.delete(instance)
                return True
            return False

    def count(self, model: Type[T], **kwargs) -> int:
        """
        统计记录数 (ORM 风格)

        Args:
            model: ORM 模型类
            **kwargs: 查询条件 (可选)

        Returns:
            记录数

        示例:
            total_users = mysql_util.count(User)
            active_users = mysql_util.count(User, status="active")
        """
        with self.get_session() as session:
            stmt = select(model)
            if kwargs:
                stmt = stmt.filter_by(**kwargs)
            result = session.execute(stmt)
            return len(list(result.scalars().all()))

    def close(self):
        """关闭连接池"""
        self.engine.dispose()
        logger.info("[MySQL] 连接池已关闭")

    def __enter__(self):
        """支持 with 语句"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持 with 语句"""
        self.close()


# 使用示例
def example():
    """
    使用示例
    """
    from .models import PDFDocument, ProcessingLog
    from datetime import datetime

    # 1. 初始化连接
    mysql = MySQLUtil(
        host="localhost",
        port=3306,
        user="root",
        password="password",
        database="pdf_db",
        charset="utf8mb4",
        echo=False  # 生产环境设为 False
    )

    # 2. 创建表
    mysql.create_tables(drop_existing=False)

    # 3. 使用 Core SQL 风格
    print("\n=== Core SQL 示例 ===")
    rows = mysql.execute_raw_sql(
        "SELECT * FROM pdf_documents WHERE status = :status LIMIT :limit",
        {"status": "completed", "limit": 10}
    )
    for row in rows:
        print(row)

    # 4. 使用 ORM 风格 - 插入
    print("\n=== ORM 插入示例 ===")
    doc = PDFDocument(
        doc_id="test_20250101_120000",
        task_id="test",
        file_name="test.pdf",
        status="pending",
        total_pages=10
    )
    saved_doc = mysql.insert_one(doc)
    print(f"插入成功, ID: {saved_doc.id}")

    # 5. 使用 ORM 风格 - 查询
    print("\n=== ORM 查询示例 ===")
    pending_docs = mysql.filter_by(PDFDocument, status="pending")
    for doc in pending_docs:
        print(doc)

    # 6. 使用 ORM 风格 - 更新
    print("\n=== ORM 更新示例 ===")
    success = mysql.update_by_id(
        PDFDocument,
        saved_doc.id,
        status="completed",
        processed_at=datetime.now()
    )
    print(f"更新成功: {success}")

    # 7. 使用 Session 手动控制事务
    print("\n=== Session 示例 ===")
    with mysql.get_session() as session:
        # 查询
        doc = session.get(PDFDocument, saved_doc.id)
        print(f"查询到: {doc}")

        # 修改
        doc.status = "failed"
        doc.error_message = "测试错误"

        # 添加日志
        log = ProcessingLog(
            doc_id=doc.doc_id,
            level="error",
            stage="extract",
            message="测试日志"
        )
        session.add(log)
        # 自动提交

    # 8. 统计
    print("\n=== 统计示例 ===")
    total = mysql.count(PDFDocument)
    completed = mysql.count(PDFDocument, status="completed")
    print(f"总文档数: {total}, 已完成: {completed}")

    # 9. 关闭连接
    mysql.close()


if __name__ == "__main__":
    example()