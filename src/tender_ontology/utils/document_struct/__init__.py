"""
document_struct 工具模块
提供百度文心一言图像理解和文本分析功能
"""

# 图像客户端（Bearer 鉴权）
from .baidu_client_bearer import (
    BaiduImageClientBearer,
    get_baidu_client_bearer,
    reset_baidu_client_bearer
)

# 文本客户端
from .baidu_text_client import (
    BaiduTextClient,
    get_baidu_text_client,
    reset_baidu_text_client
)

# 文档层级构建
from .hierarchy_builder import (
    process_document_hierarchy,
    load_tagged_document,
    extract_text_content
)

# 文档层级构建（关系预测方法）
from .hierarchy_relation import (
    process_document_hierarchy_relations,
    extract_heading_candidates
)

# 树构建算法（基于论文）
from .tree import (
    TreeConstructor,
    TreeNode,
    construct_tree_from_predictions
)

# 坐标转换工具
from .bbox_utils import (
    convert_bbox_to_topleft,
    convert_bboxes_to_topleft,
    extract_page_heights_from_docling,
    convert_element_bboxes_to_topleft,
    convert_fulltext_to_topleft,
    convert_tree_node_to_topleft,
    convert_forward_to_topleft
)

__all__ = [
    # 图像客户端
    "BaiduImageClientBearer",
    "get_baidu_client_bearer",
    "reset_baidu_client_bearer",
    # 文本客户端
    "BaiduTextClient",
    "get_baidu_text_client",
    "reset_baidu_text_client",
    # 层级构建（直接方法）
    "process_document_hierarchy",
    "load_tagged_document",
    "extract_text_content",
    # 层级构建（关系预测方法）
    "process_document_hierarchy_relations",
    "extract_heading_candidates",
    # 树构建算法
    "TreeConstructor",
    "TreeNode",
    "construct_tree_from_predictions",
    # 坐标转换工具
    "convert_bbox_to_topleft",
    "convert_bboxes_to_topleft",
    "extract_page_heights_from_docling",
    "convert_element_bboxes_to_topleft",
    "convert_fulltext_to_topleft",
    "convert_tree_node_to_topleft",
    "convert_forward_to_topleft",
]
