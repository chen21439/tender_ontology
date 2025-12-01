"""
知识图谱路由

提供 Neo4j 图数据库的查询接口
"""

from fastapi import APIRouter
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

# 创建路由
router = APIRouter(tags=["知识图谱"])


# ==================== 响应模型 ====================

class GraphResponse(BaseModel):
    """通用图数据响应"""
    success: bool = Field(..., description="是否成功")
    errCode: Optional[str] = Field(None, description="错误码")
    errMsg: Optional[str] = Field(None, description="错误信息")
    data: Optional[Dict[str, Any]] = Field(None, description="响应数据")


# ==================== 路由接口 ====================

@router.get("/graph", response_model=GraphResponse, summary="查询所有节点和边")
async def get_all_graph():
    """
    查询 Neo4j 中所有节点和边

    Returns:
        包含所有节点和边的图数据
    """
    # 先尝试导入依赖
    try:
        from tender_ontology.utils.db.neo4j import get_neo4j
        from neo4j.exceptions import ServiceUnavailable, AuthError
    except ImportError as e:
        return GraphResponse(
            success=False,
            errCode="NEO4J_NOT_INSTALLED",
            errMsg=f"Neo4j 驱动未安装，请执行: pip install neo4j。错误: {str(e)}",
            data=None
        )

    try:
        db = get_neo4j()

        # 先验证连接
        if not db.verify_connectivity():
            return GraphResponse(
                success=False,
                errCode="NEO4J_CONN_ERR",
                errMsg="Neo4j 连接失败，请检查服务是否启动",
                data=None
            )

        # 1. 查询所有节点
        nodes_query = """
        MATCH (n)
        RETURN id(n) AS id, labels(n) AS labels, properties(n) AS properties
        """
        nodes_result = db.execute_read(nodes_query, {})

        nodes = []
        for record in nodes_result:
            nodes.append({
                "id": record["id"],
                "labels": record["labels"],
                "properties": record["properties"]
            })

        # 2. 查询所有边
        edges_query = """
        MATCH (a)-[r]->(b)
        RETURN id(r) AS id, type(r) AS type, id(a) AS source, id(b) AS target, properties(r) AS properties
        """
        edges_result = db.execute_read(edges_query, {})

        edges = []
        for record in edges_result:
            edges.append({
                "id": record["id"],
                "type": record["type"],
                "source": record["source"],
                "target": record["target"],
                "properties": record["properties"] or {}
            })

        return GraphResponse(
            success=True,
            errCode=None,
            errMsg=None,
            data={
                "nodes": nodes,
                "edges": edges
            }
        )

    except ServiceUnavailable as e:
        return GraphResponse(
            success=False,
            errCode="NEO4J_UNAVAILABLE",
            errMsg=f"Neo4j 服务不可用: {str(e)}",
            data=None
        )
    except AuthError as e:
        return GraphResponse(
            success=False,
            errCode="NEO4J_AUTH_ERR",
            errMsg=f"Neo4j 认证失败: {str(e)}",
            data=None
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return GraphResponse(
            success=False,
            errCode="GRAPH_001",
            errMsg=f"查询失败: {str(e)}",
            data=None
        )