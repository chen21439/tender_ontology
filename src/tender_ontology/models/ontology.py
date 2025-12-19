"""
Ontology data models.
"""

from typing import Optional
from pydantic import BaseModel, Field


class OntologyNode(BaseModel):
    """Ontology node model."""

    id: Optional[int] = None
    name: str = Field(..., description="Node name")
    label: str = Field(..., description="Node label")
    description: Optional[str] = Field(None, description="Node description")
    node_type: str = Field(..., description="Type of the node")

    class Config:
        from_attributes = True


class OntologyEdge(BaseModel):
    """Ontology edge (relationship) model."""

    id: Optional[int] = None
    source_id: int = Field(..., description="Source node ID")
    target_id: int = Field(..., description="Target node ID")
    relationship_type: str = Field(..., description="Type of relationship")
    properties: Optional[dict] = Field(None, description="Additional properties")

    class Config:
        from_attributes = True


class OntologyCreateRequest(BaseModel):
    """Request model for creating ontology nodes."""

    name: str
    label: str
    description: Optional[str] = None
    node_type: str


class OntologyResponse(BaseModel):
    """Response model for ontology operations."""

    success: bool
    message: str
    data: Optional[dict] = None


class MoveNodeRequest(BaseModel):
    """Request model for moving a node to a new parent."""

    node_id: str = Field(..., description="要移动的节点 ID")
    target_parent_id: str = Field(..., description="目标父节点 ID，'root' 表示移动到根层级")