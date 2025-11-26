"""
基于 Level 的树构建算法

核心思路：
1. 千问 API 返回每个标题的 level（# = 1, ## = 2, ...）
2. 按阅读顺序遍历，使用「右支路」原则挂载节点
3. 非标题节点（text/table）挂载到最近的标题节点下

算法：
对于新节点 N（level = L）：
1. 沿着右支路向上找，找到第一个 level < L 的节点 P
2. 把 N 挂载为 P 的子节点

特殊情况：
- 如果找不到 level < L 的节点，N 成为新的根节点
- 如果 N.level == 1，N 直接成为根节点
- 非标题节点视为 level = 无穷大，挂到最近的标题下
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class TreeNode:
    """树节点"""
    id: str
    text: str
    label: str  # section_header, text, table
    level: int  # 标题层级，非标题节点为 999
    page: Optional[int] = None
    bboxes: List[Dict[str, Any]] = field(default_factory=list)
    docling_ref: Optional[str] = None

    # 树结构
    parent: Optional['TreeNode'] = None
    children: List['TreeNode'] = field(default_factory=list)

    def add_child(self, child: 'TreeNode'):
        """添加子节点"""
        if child not in self.children:
            self.children.append(child)
            child.parent = self

    def to_dict(self, include_children: bool = True) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "id": self.id,
            "text": self.text[:100] if len(self.text) > 100 else self.text,
            "label": self.label,
            "level": self.level,
        }

        if self.page is not None:
            result["page"] = self.page
        if self.bboxes:
            result["bboxes"] = self.bboxes
        if self.docling_ref:
            result["docling_ref"] = self.docling_ref

        if include_children and self.children:
            result["children"] = [
                child.to_dict(include_children=True)
                for child in self.children
            ]

        return result

    def __repr__(self):
        return f"TreeNode(id={self.id}, level={self.level}, text='{self.text[:20]}...', children={len(self.children)})"


class LevelTreeConstructor:
    """
    基于 Level 的树构建器

    输入：
    1. model_headings: 千问返回的标题列表（带 level）
    2. fulltext_items: docling 的 fulltext 数据（按阅读顺序）

    输出：
    完整的文档层级树
    """

    # 非标题节点的虚拟 level
    NON_HEADING_LEVEL = 999

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.nodes_map: Dict[str, TreeNode] = {}
        self.root_nodes: List[TreeNode] = []
        # 右支路缓存：从根到最右叶子的路径
        self._rightmost_path: List[TreeNode] = []

    def build_tree(
        self,
        model_headings: List[Dict[str, Any]],
        fulltext_items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        构建完整的文档层级树

        Args:
            model_headings: 千问返回的标题列表，格式：
                [{"id": "texts-0", "text": "标题", "level": 1, "page": 1, "bboxes": [...]}]
            fulltext_items: docling fulltext 数据，格式：
                [{"id": "texts-0", "label": "section_header", "text": "...", "page": 1, "bboxes": [...]}]

        Returns:
            树结构和统计信息
        """
        if self.verbose:
            print(f"[LevelTreeConstructor] 开始构建层级树...")
            print(f"[LevelTreeConstructor] 模型标题数: {len(model_headings)}")
            print(f"[LevelTreeConstructor] Fulltext 元素数: {len(fulltext_items)}")

        # 1. 构建标题 ID 到 level 的映射
        heading_level_map = self._build_heading_level_map(model_headings)

        # 2. 按阅读顺序遍历 fulltext，逐个插入
        for i, item in enumerate(fulltext_items):
            node_id = item.get("id", "")
            label = item.get("label", "text")
            text = item.get("text", "")
            page = item.get("page")
            bboxes = item.get("bboxes", [])
            docling_ref = item.get("docling_ref")

            # 确定 level
            if label == "section_header" and node_id in heading_level_map:
                level = heading_level_map[node_id]
            elif label == "section_header":
                # 标题但不在模型结果中，当作普通段落处理
                level = self.NON_HEADING_LEVEL
                label = "text"  # 修改 label 为 text
            else:
                # 非标题节点
                level = self.NON_HEADING_LEVEL

            # 创建节点
            node = TreeNode(
                id=node_id,
                text=text,
                label=label,
                level=level,
                page=page,
                bboxes=bboxes,
                docling_ref=docling_ref
            )
            self.nodes_map[node_id] = node

            # 插入节点
            self._insert_node(node, i)

        # 3. 构建结果
        result = self._build_result()

        if self.verbose:
            print(f"[LevelTreeConstructor] 构建完成")
            print(f"[LevelTreeConstructor] 根节点数: {len(self.root_nodes)}")
            print(f"[LevelTreeConstructor] 总节点数: {len(self.nodes_map)}")

        return result

    def _build_heading_level_map(
        self,
        model_headings: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        构建标题 ID 到 level 的映射

        Args:
            model_headings: 千问返回的标题列表

        Returns:
            {id: level} 映射
        """
        level_map = {}

        for heading in model_headings:
            node_id = heading.get("id", "")
            level = heading.get("level", 1)

            if node_id:
                level_map[node_id] = level

        if self.verbose:
            print(f"[LevelTreeConstructor] 标题 level 映射: {len(level_map)} 个")
            # 统计各 level 数量
            level_counts = {}
            for lvl in level_map.values():
                level_counts[lvl] = level_counts.get(lvl, 0) + 1
            print(f"[LevelTreeConstructor] Level 分布: {level_counts}")

        return level_map

    def _insert_node(self, node: TreeNode, index: int):
        """
        按右支路原则插入节点

        算法：
        1. 如果是第一个节点，作为根节点
        2. 如果 level == 1，作为新的根节点
        3. 否则，沿右支路向上找第一个 level < 当前 level 的节点，挂载为其子节点

        Args:
            node: 待插入的节点
            index: 节点在 fulltext 中的索引
        """
        # 第一个节点或 level=1 的标题节点
        if index == 0:
            self.root_nodes.append(node)
            self._rightmost_path = [node]
            if self.verbose:
                print(f"[LevelTreeConstructor]   [{index}] {node.id} (L{node.level}) -> 根节点")
            return

        # level=1 的标题成为新的根节点
        if node.level == 1 and node.label == "section_header":
            self.root_nodes.append(node)
            self._rightmost_path = [node]
            if self.verbose:
                print(f"[LevelTreeConstructor]   [{index}] {node.id} (L{node.level}) -> 新根节点")
            return

        # 沿右支路向上找合适的父节点
        parent_node = self._find_parent_on_rightmost_path(node.level)

        if parent_node:
            parent_node.add_child(node)
            # 更新右支路
            self._update_rightmost_path(node)
            if self.verbose and index < 20:
                print(f"[LevelTreeConstructor]   [{index}] {node.id} (L{node.level}) -> 挂到 {parent_node.id} (L{parent_node.level})")
        else:
            # 找不到合适的父节点，作为根节点
            self.root_nodes.append(node)
            self._rightmost_path = [node]
            if self.verbose:
                print(f"[LevelTreeConstructor]   [{index}] {node.id} (L{node.level}) -> 根节点（无合适父节点）")

    def _find_parent_on_rightmost_path(self, target_level: int) -> Optional[TreeNode]:
        """
        在右支路上找第一个 level < target_level 的节点

        从右支路末端（最右叶子）向上遍历，找到第一个 level 比当前小的节点

        Args:
            target_level: 待插入节点的 level

        Returns:
            合适的父节点，如果找不到返回 None
        """
        # 从右支路末端向上遍历
        for node in reversed(self._rightmost_path):
            if node.level < target_level:
                return node

        return None

    def _update_rightmost_path(self, new_node: TreeNode):
        """
        更新右支路

        新节点插入后，右支路 = 从根到新节点的路径

        Args:
            new_node: 新插入的节点
        """
        # 从新节点向上回溯到根，构建路径
        path = []
        current = new_node
        while current is not None:
            path.append(current)
            current = current.parent

        # 反转得到从根到叶的路径
        self._rightmost_path = list(reversed(path))

    def _build_result(self) -> Dict[str, Any]:
        """构建最终结果"""
        # 序列化树结构
        tree_structure = [
            root.to_dict(include_children=True)
            for root in self.root_nodes
        ]

        # 统计
        label_counts = {}
        level_counts = {}
        for node in self.nodes_map.values():
            label_counts[node.label] = label_counts.get(node.label, 0) + 1
            if node.label == "section_header":
                lvl_key = f"level_{node.level}"
                level_counts[lvl_key] = level_counts.get(lvl_key, 0) + 1

        return {
            "tree": tree_structure,
            "summary": {
                "total_nodes": len(self.nodes_map),
                "root_nodes": len(self.root_nodes),
                "label_distribution": label_counts,
                "heading_level_distribution": level_counts
            }
        }

    def print_tree(self, max_depth: int = 4, show_non_headers: bool = False):
        """
        打印树结构

        Args:
            max_depth: 最大打印深度
            show_non_headers: 是否显示非标题节点
        """
        def print_node(node: TreeNode, depth: int = 0, prefix: str = ""):
            if depth > max_depth:
                return

            # 跳过非标题节点（如果不显示）
            if not show_non_headers and node.label != "section_header":
                return

            indent = "  " * depth
            text_preview = node.text[:40] if node.text else "(空)"
            level_str = f"L{node.level}" if node.level < self.NON_HEADING_LEVEL else "---"
            print(f"{indent}{prefix}[{level_str}] {node.id}: {text_preview}")

            for i, child in enumerate(node.children):
                is_last = (i == len(node.children) - 1)
                child_prefix = "└─ " if is_last else "├─ "
                print_node(child, depth + 1, child_prefix)

        print("\n" + "=" * 80)
        print("树结构预览:")
        print("=" * 80)

        for i, root in enumerate(self.root_nodes):
            print(f"\n根节点 #{i + 1}:")
            print_node(root)

        print("=" * 80 + "\n")


def build_document_tree(
    model_headings: List[Dict[str, Any]],
    fulltext_items: List[Dict[str, Any]],
    verbose: bool = True
) -> Dict[str, Any]:
    """
    便捷函数：构建文档层级树

    Args:
        model_headings: 千问返回的标题列表
        fulltext_items: docling fulltext 数据
        verbose: 是否打印详细信息

    Returns:
        树结构和统计信息
    """
    constructor = LevelTreeConstructor(verbose=verbose)
    return constructor.build_tree(model_headings, fulltext_items)


if __name__ == "__main__":
    # 测试示例
    print("""
LevelTreeConstructor - 基于 Level 的树构建算法
==============================================

使用方法：
---------
from tender_ontology.utils.document_struct.tree import LevelTreeConstructor

# 千问返回的标题
model_headings = [
    {"id": "texts-0", "text": "第一章", "level": 1},
    {"id": "texts-5", "text": "一、背景", "level": 2},
    {"id": "texts-10", "text": "1.1 现状", "level": 3},
]

# Docling fulltext
fulltext_items = [
    {"id": "texts-0", "label": "section_header", "text": "第一章"},
    {"id": "texts-1", "label": "text", "text": "这是正文..."},
    {"id": "texts-5", "label": "section_header", "text": "一、背景"},
    ...
]

# 构建树
constructor = LevelTreeConstructor(verbose=True)
result = constructor.build_tree(model_headings, fulltext_items)

# 打印树结构
constructor.print_tree(max_depth=3)
    """)

    # 简单测试
    test_headings = [
        {"id": "texts-0", "text": "第一章 项目概述", "level": 1},
        {"id": "texts-5", "text": "一、项目背景", "level": 2},
        {"id": "texts-10", "text": "1.1 现状分析", "level": 3},
        {"id": "texts-15", "text": "二、项目目标", "level": 2},
        {"id": "texts-30", "text": "第二章 技术方案", "level": 1},
    ]

    test_fulltext = [
        {"id": "texts-0", "label": "section_header", "text": "第一章 项目概述"},
        {"id": "texts-1", "label": "text", "text": "本项目旨在..."},
        {"id": "texts-5", "label": "section_header", "text": "一、项目背景"},
        {"id": "texts-6", "label": "text", "text": "随着信息化发展..."},
        {"id": "texts-10", "label": "section_header", "text": "1.1 现状分析"},
        {"id": "texts-11", "label": "text", "text": "目前存在以下问题..."},
        {"id": "tables-0", "label": "table", "text": "<table>...</table>"},
        {"id": "texts-15", "label": "section_header", "text": "二、项目目标"},
        {"id": "texts-16", "label": "text", "text": "实现以下目标..."},
        {"id": "texts-30", "label": "section_header", "text": "第二章 技术方案"},
        {"id": "texts-31", "label": "text", "text": "技术方案如下..."},
    ]

    print("\n运行测试...")
    constructor = LevelTreeConstructor(verbose=True)
    result = constructor.build_tree(test_headings, test_fulltext)

    constructor.print_tree(max_depth=5, show_non_headers=False)

    print("\n结果摘要:")
    print(result["summary"])