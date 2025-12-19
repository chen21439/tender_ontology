"""
Ontology management endpoints.
"""

from fastapi import APIRouter, HTTPException
from typing import List

from tender_ontology.models.ontology import (
    OntologyNode,
    OntologyCreateRequest,
    OntologyResponse,
    MoveNodeRequest,
)
from tender_ontology.services.ontology_editor import move_ontology_node

router = APIRouter(prefix="/ontology")


@router.get("/nodes", response_model=List[OntologyNode])
async def get_nodes():
    """
    Get all ontology nodes.

    Returns:
        List[OntologyNode]: List of ontology nodes
    """
    # TODO: Implement database query
    return []


@router.post("/nodes", response_model=OntologyResponse)
async def create_node(request: OntologyCreateRequest):
    """
    Create a new ontology node.

    Args:
        request: Node creation request

    Returns:
        OntologyResponse: Creation result
    """
    # TODO: Implement database insert
    return OntologyResponse(
        success=True,
        message="Node created successfully",
        data={"name": request.name, "label": request.label},
    )


@router.get("/nodes/{node_id}", response_model=OntologyNode)
async def get_node(node_id: int):
    """
    Get a specific ontology node.

    Args:
        node_id: Node ID

    Returns:
        OntologyNode: The requested node

    Raises:
        HTTPException: If node not found
    """
    # TODO: Implement database query
    raise HTTPException(status_code=404, detail="Node not found")


@router.delete("/nodes/{node_id}", response_model=OntologyResponse)
async def delete_node(node_id: int):
    """
    Delete an ontology node.

    Args:
        node_id: Node ID

    Returns:
        OntologyResponse: Deletion result
    """
    # TODO: Implement database delete
    return OntologyResponse(success=True, message=f"Node {node_id} deleted")


@router.post("/task/{task_id}/move-node", response_model=OntologyResponse)
async def move_node(task_id: str, request: MoveNodeRequest):
    """
    移动 ontology.json 中的节点到新的父节点下

    Args:
        task_id: 任务 ID
        request: 包含 node_id 和 target_parent_id

    Returns:
        OntologyResponse: 操作结果
    """
    result = move_ontology_node(
        task_id=task_id,
        node_id=request.node_id,
        target_parent_id=request.target_parent_id,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))

    return OntologyResponse(
        success=True,
        message=result.get("message", "节点移动成功"),
    )