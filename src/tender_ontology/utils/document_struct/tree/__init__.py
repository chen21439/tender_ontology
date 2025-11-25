"""
文档层级树构建模块

包含两种树构建算法：
1. TreeConstructor: 基于 Detect-Order-Construct 论文，需要模型预测 parent_id
2. LevelTreeConstructor: 基于 Level 的树构建，使用千问返回的标题层级
"""

from .tree_construct import TreeConstructor, TreeNode, construct_tree_from_predictions
from .level_tree_construct import LevelTreeConstructor, build_document_tree

__all__ = [
    "TreeConstructor",
    "TreeNode",
    "construct_tree_from_predictions",
    "LevelTreeConstructor",
    "build_document_tree",
]