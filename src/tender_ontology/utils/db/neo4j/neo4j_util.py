"""
Neo4j 工具类

基于官方 Neo4j Python Driver，提供图数据库操作
"""

from neo4j import GraphDatabase, Driver, Session, Result
from neo4j.exceptions import ServiceUnavailable, AuthError
from typing import List, Dict, Any, Optional, Callable, TypeVar, Union
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class Neo4jUtil:
    """
    Neo4j 工具类 - 基于官方 Neo4j Python Driver

    特性:
    - 自动连接池管理 (Driver 内置连接池)
    - 事务自动提交/回滚
    - 支持读/写事务分离
    - 连接健康检查
    """

    def __init__(self,
                 uri: str = "bolt://localhost:7687",
                 user: str = "neo4j",
                 password: str = "",
                 database: str = "neo4j",
                 max_connection_pool_size: int = 100,
                 connection_timeout: float = 30.0,
                 max_transaction_retry_time: float = 30.0,
                 encrypted: bool = False):
        """
        初始化 Neo4j 连接

        Args:
            uri: Neo4j 连接地址 (bolt://host:port 或 neo4j+s://...)
            user: 数据库用户名
            password: 数据库密码
            database: 数据库名称 (默认 neo4j)
            max_connection_pool_size: 连接池最大连接数 (默认 100)
            connection_timeout: 连接超时时间 (秒, 默认 30)
            max_transaction_retry_time: 事务重试最大时间 (秒, 默认 30)
            encrypted: 是否启用加密 (默认 False, 本地开发用)
        """
        self.uri = uri
        self.user = user
        self.database = database

        # 创建驱动 (内置连接池)
        self.driver: Driver = GraphDatabase.driver(
            uri,
            auth=(user, password),
            max_connection_pool_size=max_connection_pool_size,
            connection_timeout=connection_timeout,
            max_transaction_retry_time=max_transaction_retry_time,
            encrypted=encrypted
        )

        logger.info(f"[Neo4j] 已连接到 {uri}, 数据库: {database}")

    def verify_connectivity(self) -> bool:
        """
        验证连接是否正常

        Returns:
            连接是否成功
        """
        try:
            self.driver.verify_connectivity()
            logger.info("[Neo4j] 连接验证成功")
            return True
        except ServiceUnavailable as e:
            logger.error(f"[Neo4j] 服务不可用: {e}")
            return False
        except AuthError as e:
            logger.error(f"[Neo4j] 认证失败: {e}")
            return False

    def get_version(self) -> Dict[str, Any]:
        """
        获取 Neo4j 版本信息

        Returns:
            版本信息字典
        """
        def _get_version(tx):
            result = tx.run("CALL dbms.components() YIELD name, versions, edition "
                          "RETURN name, versions[0] AS version, edition")
            record = result.single()
            if record:
                return {
                    "name": record["name"],
                    "version": record["version"],
                    "edition": record["edition"]
                }
            return {}

        with self.driver.session(database=self.database) as session:
            return session.execute_read(_get_version)

    @contextmanager
    def get_session(self, access_mode: str = "WRITE"):
        """
        获取数据库会话

        Args:
            access_mode: 访问模式 ("READ" 或 "WRITE")

        Yields:
            Session: Neo4j Session 对象

        用法:
            with neo4j_util.get_session() as session:
                result = session.run("MATCH (n) RETURN n LIMIT 10")
                for record in result:
                    print(record)
        """
        from neo4j import READ_ACCESS, WRITE_ACCESS

        mode = READ_ACCESS if access_mode.upper() == "READ" else WRITE_ACCESS
        session = self.driver.session(database=self.database, default_access_mode=mode)
        try:
            yield session
        finally:
            session.close()

    # ==================== 读操作 ====================

    def execute_read(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        执行读取查询

        Args:
            query: Cypher 查询语句
            params: 参数字典 (默认 None)

        Returns:
            查询结果列表 (字典格式)

        示例:
            results = neo4j_util.execute_read(
                "MATCH (p:Person {name: $name}) RETURN p.name AS name, p.age AS age",
                {"name": "Alice"}
            )
        """
        def _read(tx, query, params):
            result = tx.run(query, params or {})
            return [record.data() for record in result]

        with self.driver.session(database=self.database) as session:
            return session.execute_read(_read, query, params)

    def execute_read_single(self, query: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        执行读取查询，返回单条结果

        Args:
            query: Cypher 查询语句
            params: 参数字典

        Returns:
            单条记录 (字典格式) 或 None
        """
        def _read_single(tx, query, params):
            result = tx.run(query, params or {})
            record = result.single()
            return record.data() if record else None

        with self.driver.session(database=self.database) as session:
            return session.execute_read(_read_single, query, params)

    # ==================== 写操作 ====================

    def execute_write(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        执行写入查询

        Args:
            query: Cypher 查询语句
            params: 参数字典

        Returns:
            查询结果列表 (字典格式)

        示例:
            result = neo4j_util.execute_write(
                "CREATE (p:Person {name: $name, age: $age}) RETURN p",
                {"name": "Alice", "age": 30}
            )
        """
        def _write(tx, query, params):
            result = tx.run(query, params or {})
            return [record.data() for record in result]

        with self.driver.session(database=self.database) as session:
            return session.execute_write(_write, query, params)

    def execute_write_single(self, query: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        执行写入查询，返回单条结果

        Args:
            query: Cypher 查询语句
            params: 参数字典

        Returns:
            单条记录 (字典格式) 或 None
        """
        def _write_single(tx, query, params):
            result = tx.run(query, params or {})
            record = result.single()
            return record.data() if record else None

        with self.driver.session(database=self.database) as session:
            return session.execute_write(_write_single, query, params)

    # ==================== CRUD 便捷方法 ====================

    def create_node(self, label: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建节点

        Args:
            label: 节点标签
            properties: 节点属性

        Returns:
            创建的节点信息

        示例:
            node = neo4j_util.create_node("Person", {"name": "Alice", "age": 30})
        """
        query = f"CREATE (n:{label} $props) RETURN n, id(n) AS node_id, labels(n) AS labels"
        result = self.execute_write_single(query, {"props": properties})
        return result

    def create_nodes_batch(self, label: str, nodes_data: List[Dict[str, Any]]) -> int:
        """
        批量创建节点

        Args:
            label: 节点标签
            nodes_data: 节点属性列表

        Returns:
            创建的节点数量

        示例:
            count = neo4j_util.create_nodes_batch("Person", [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25}
            ])
        """
        query = f"UNWIND $batch AS props CREATE (n:{label}) SET n = props RETURN count(n) AS count"
        result = self.execute_write_single(query, {"batch": nodes_data})
        return result["count"] if result else 0

    def find_node_by_id(self, node_id: int) -> Optional[Dict[str, Any]]:
        """
        根据内部 ID 查找节点

        Args:
            node_id: Neo4j 内部节点 ID

        Returns:
            节点信息或 None
        """
        query = "MATCH (n) WHERE id(n) = $node_id RETURN n, id(n) AS node_id, labels(n) AS labels"
        return self.execute_read_single(query, {"node_id": node_id})

    def find_nodes_by_label(self, label: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        根据标签查找节点

        Args:
            label: 节点标签
            limit: 返回数量限制

        Returns:
            节点列表
        """
        query = f"MATCH (n:{label}) RETURN n, id(n) AS node_id, labels(n) AS labels LIMIT $limit"
        return self.execute_read(query, {"limit": limit})

    def find_nodes_by_property(self, label: str, property_name: str, property_value: Any,
                               limit: int = 100) -> List[Dict[str, Any]]:
        """
        根据属性查找节点

        Args:
            label: 节点标签
            property_name: 属性名
            property_value: 属性值
            limit: 返回数量限制

        Returns:
            节点列表

        示例:
            nodes = neo4j_util.find_nodes_by_property("Person", "name", "Alice")
        """
        query = f"MATCH (n:{label} {{{property_name}: $value}}) RETURN n, id(n) AS node_id, labels(n) AS labels LIMIT $limit"
        return self.execute_read(query, {"value": property_value, "limit": limit})

    def update_node(self, node_id: int, properties: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        更新节点属性

        Args:
            node_id: Neo4j 内部节点 ID
            properties: 要更新的属性

        Returns:
            更新后的节点信息

        示例:
            node = neo4j_util.update_node(123, {"age": 31, "city": "Beijing"})
        """
        query = "MATCH (n) WHERE id(n) = $node_id SET n += $props RETURN n, id(n) AS node_id, labels(n) AS labels"
        return self.execute_write_single(query, {"node_id": node_id, "props": properties})

    def delete_node(self, node_id: int) -> bool:
        """
        删除节点 (及其所有关系)

        Args:
            node_id: Neo4j 内部节点 ID

        Returns:
            是否删除成功
        """
        query = "MATCH (n) WHERE id(n) = $node_id DETACH DELETE n RETURN count(n) AS count"
        result = self.execute_write_single(query, {"node_id": node_id})
        return result["count"] > 0 if result else False

    def delete_nodes_by_label(self, label: str) -> int:
        """
        删除指定标签的所有节点

        Args:
            label: 节点标签

        Returns:
            删除的节点数量
        """
        query = f"MATCH (n:{label}) DETACH DELETE n RETURN count(n) AS count"
        result = self.execute_write_single(query, {})
        return result["count"] if result else 0

    # ==================== 关系操作 ====================

    def create_relationship(self,
                           from_node_id: int,
                           to_node_id: int,
                           rel_type: str,
                           properties: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        创建关系

        Args:
            from_node_id: 起始节点 ID
            to_node_id: 目标节点 ID
            rel_type: 关系类型
            properties: 关系属性 (可选)

        Returns:
            创建的关系信息

        示例:
            rel = neo4j_util.create_relationship(1, 2, "KNOWS", {"since": 2020})
        """
        props_clause = "SET r = $props" if properties else ""
        query = f"""
        MATCH (a), (b)
        WHERE id(a) = $from_id AND id(b) = $to_id
        CREATE (a)-[r:{rel_type}]->(b)
        {props_clause}
        RETURN type(r) AS type, id(r) AS rel_id, id(a) AS from_id, id(b) AS to_id
        """
        params = {"from_id": from_node_id, "to_id": to_node_id}
        if properties:
            params["props"] = properties
        return self.execute_write_single(query, params)

    def find_relationships(self,
                          from_label: Optional[str] = None,
                          to_label: Optional[str] = None,
                          rel_type: Optional[str] = None,
                          limit: int = 100) -> List[Dict[str, Any]]:
        """
        查找关系

        Args:
            from_label: 起始节点标签 (可选)
            to_label: 目标节点标签 (可选)
            rel_type: 关系类型 (可选)
            limit: 返回数量限制

        Returns:
            关系列表
        """
        from_clause = f":{from_label}" if from_label else ""
        to_clause = f":{to_label}" if to_label else ""
        rel_clause = f":{rel_type}" if rel_type else ""

        query = f"""
        MATCH (a{from_clause})-[r{rel_clause}]->(b{to_clause})
        RETURN a AS from_node, r AS relationship, b AS to_node,
               type(r) AS rel_type, id(r) AS rel_id
        LIMIT $limit
        """
        return self.execute_read(query, {"limit": limit})

    def delete_relationship(self, rel_id: int) -> bool:
        """
        删除关系

        Args:
            rel_id: 关系 ID

        Returns:
            是否删除成功
        """
        query = "MATCH ()-[r]->() WHERE id(r) = $rel_id DELETE r RETURN count(r) AS count"
        result = self.execute_write_single(query, {"rel_id": rel_id})
        return result["count"] > 0 if result else False

    # ==================== 统计和工具方法 ====================

    def count_nodes(self, label: Optional[str] = None) -> int:
        """
        统计节点数量

        Args:
            label: 节点标签 (可选，不指定则统计所有节点)

        Returns:
            节点数量
        """
        if label:
            query = f"MATCH (n:{label}) RETURN count(n) AS count"
        else:
            query = "MATCH (n) RETURN count(n) AS count"
        result = self.execute_read_single(query, {})
        return result["count"] if result else 0

    def count_relationships(self, rel_type: Optional[str] = None) -> int:
        """
        统计关系数量

        Args:
            rel_type: 关系类型 (可选)

        Returns:
            关系数量
        """
        if rel_type:
            query = f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS count"
        else:
            query = "MATCH ()-[r]->() RETURN count(r) AS count"
        result = self.execute_read_single(query, {})
        return result["count"] if result else 0

    def clear_database(self) -> int:
        """
        清空数据库 (删除所有节点和关系)

        ⚠️ 危险操作，请谨慎使用

        Returns:
            删除的节点数量
        """
        query = "MATCH (n) DETACH DELETE n RETURN count(n) AS count"
        result = self.execute_write_single(query, {})
        count = result["count"] if result else 0
        logger.warning(f"[Neo4j] 已清空数据库，删除 {count} 个节点")
        return count

    def close(self):
        """关闭连接池"""
        self.driver.close()
        logger.info("[Neo4j] 连接池已关闭")

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
    # 1. 初始化连接
    neo4j = Neo4jUtil(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="your_password",
        database="neo4j"
    )

    # 2. 验证连接
    if not neo4j.verify_connectivity():
        print("连接失败!")
        return

    # 3. 获取版本
    version = neo4j.get_version()
    print(f"Neo4j 版本: {version}")

    # 4. 创建节点
    print("\n=== 创建节点 ===")
    alice = neo4j.create_node("Person", {"name": "Alice", "age": 30})
    print(f"创建 Alice: {alice}")

    bob = neo4j.create_node("Person", {"name": "Bob", "age": 25})
    print(f"创建 Bob: {bob}")

    # 5. 创建关系
    print("\n=== 创建关系 ===")
    rel = neo4j.create_relationship(
        alice["node_id"], bob["node_id"], "KNOWS", {"since": 2020}
    )
    print(f"创建关系: {rel}")

    # 6. 查询节点
    print("\n=== 查询节点 ===")
    persons = neo4j.find_nodes_by_label("Person")
    for p in persons:
        print(p)

    # 7. 根据属性查询
    print("\n=== 根据属性查询 ===")
    alice_nodes = neo4j.find_nodes_by_property("Person", "name", "Alice")
    print(f"找到 Alice: {alice_nodes}")

    # 8. 更新节点
    print("\n=== 更新节点 ===")
    updated = neo4j.update_node(alice["node_id"], {"age": 31, "city": "Beijing"})
    print(f"更新后: {updated}")

    # 9. 执行自定义查询
    print("\n=== 自定义查询 ===")
    results = neo4j.execute_read(
        "MATCH (a:Person)-[r:KNOWS]->(b:Person) "
        "RETURN a.name AS from_name, b.name AS to_name, r.since AS since"
    )
    for r in results:
        print(r)

    # 10. 统计
    print("\n=== 统计 ===")
    print(f"Person 节点数: {neo4j.count_nodes('Person')}")
    print(f"KNOWS 关系数: {neo4j.count_relationships('KNOWS')}")

    # 11. 删除
    print("\n=== 删除 ===")
    neo4j.delete_node(bob["node_id"])
    print("已删除 Bob")

    # 12. 关闭连接
    neo4j.close()


if __name__ == "__main__":
    example()