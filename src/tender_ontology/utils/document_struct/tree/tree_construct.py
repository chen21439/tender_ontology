"""
基于 Detect-Order-Construct 论文的树构建算法
https://arxiv.org/pdf/2401.11874

核心思路：
1. 大模型预测每个标题的 parent_id 和 left_sibling_id
2. 按阅读顺序逐个插入标题，构建层级树
3. 每次插入时，融合 parent 和 sibling 的打分，选择最佳插入位置

这个版本只使用大模型返回的结果，不考虑小模型的打分矩阵。
"""

from typing import List, Dict, Any, Optional
from collections import defaultdict


class TreeNode:
    """树节点类"""

    def __init__(
        self,
        node_id: str,
        text: str = "",
        heading_type: str = "section",
        parent_id: Optional[str] = None,
        left_sibling_id: Optional[str] = None,
        confidence: str = "medium",
        reasoning: str = "",
        page: Optional[str] = None,
        features: Optional[Dict[str, Any]] = None
    ):
        """
        初始化树节点

        Args:
            node_id: 节点ID（通常是行号）
            text: 标题文本
            heading_type: 标题类型（section/subsection/subsubsection等）
            parent_id: 父节点ID（大模型预测）
            left_sibling_id: 左兄弟节点ID（大模型预测）
            confidence: 置信度（high/medium/low）
            reasoning: 预测理由
            page: 页码
            features: 特征字典
        """
        self.id = node_id
        self.text = text
        self.heading_type = heading_type
        self.parent_id = parent_id
        self.left_sibling_id = left_sibling_id
        self.confidence = confidence
        self.reasoning = reasoning
        self.page = page
        self.features = features or {}

        # 树结构相关
        self.parent: Optional[TreeNode] = None
        self.children: List[TreeNode] = []
        self.level: Optional[int] = None  # 树的层级，根节点为1

    def add_child(self, child: 'TreeNode'):
        """添加子节点"""
        if child not in self.children:
            self.children.append(child)
            child.parent = self

    def get_rightmost_child(self) -> Optional['TreeNode']:
        """获取最右边的子节点"""
        if not self.children:
            return None
        return self.children[-1]

    def to_dict(self, include_children: bool = True) -> Dict[str, Any]:
        """
        转换为字典格式

        Args:
            include_children: 是否包含子节点（用于递归序列化）

        Returns:
            节点的字典表示
        """
        result = {
            "id": self.id,
            "text": self.text,
            "heading_type": self.heading_type,
            "level": self.level,
            "confidence": self.confidence,
        }

        # 可选字段
        if self.page:
            result["page"] = self.page
        if self.reasoning:
            result["reasoning"] = self.reasoning

        # 递归包含子节点
        if include_children and self.children:
            result["children"] = [child.to_dict(include_children=True) for child in self.children]

        return result

    def __repr__(self):
        return f"TreeNode(id={self.id}, text='{self.text[:20]}...', level={self.level}, children={len(self.children)})"


class TreeConstructor:
    """
    基于 Detect-Order-Construct 论文的树构建器

    核心算法：Tree Insertion Algorithm
    """

    def __init__(self, verbose: bool = True):
        """
        初始化树构建器

        Args:
            verbose: 是否打印详细信息
        """
        self.verbose = verbose
        self.nodes_map: Dict[str, TreeNode] = {}  # id -> TreeNode 映射
        self.root_nodes: List[TreeNode] = []  # 根节点列表

    def build_tree_from_predictions(
        self,
        predictions: List[Dict[str, Any]],
        candidates_map: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        从大模型预测结果构建层级树

        Args:
            predictions: 大模型预测的标题列表，每个元素包含：
                {
                    "id": 节点ID,
                    "is_heading": true,
                    "heading_type": "section",
                    "parent_id": 父节点ID,
                    "left_sibling_id": 左兄弟ID,
                    "confidence": "high",
                    "reasoning": "预测理由"
                }
            candidates_map: 可选的候选项映射（id -> 原始候选数据），用于补充文本和特征

        Returns:
            层级树结构
        """
        if self.verbose:
            print(f"[TreeConstructor] 开始构建层级树...")
            print(f"[TreeConstructor] 输入预测数: {len(predictions)}")

        # 第一步：创建所有节点
        self._create_nodes(predictions, candidates_map)

        # 第二步：按论文算法插入节点
        self._insert_nodes_in_order(predictions)

        # 第三步：计算层级
        self._calculate_levels()

        # 第四步：构建结果
        result = self._build_result()

        if self.verbose:
            print(f"[TreeConstructor] 构建完成")
            print(f"[TreeConstructor] 根节点数: {len(self.root_nodes)}")
            print(f"[TreeConstructor] 总节点数: {len(self.nodes_map)}")
            print(f"[TreeConstructor] 层级分布: {result['summary']['level_distribution']}")

        return result

    def _create_nodes(
        self,
        predictions: List[Dict[str, Any]],
        candidates_map: Optional[Dict[str, Dict[str, Any]]]
    ):
        """
        创建所有树节点

        Args:
            predictions: 预测结果列表
            candidates_map: 候选项映射
        """
        for pred in predictions:
            node_id = str(pred["id"])

            # 从 candidates_map 中获取原始数据
            text = ""
            page = None
            features = None

            if candidates_map and node_id in candidates_map:
                candidate = candidates_map[node_id]
                text = candidate.get("text", "")
                page = candidate.get("page")
                features = candidate.get("features")

            # 创建节点
            node = TreeNode(
                node_id=node_id,
                text=text,
                heading_type=pred.get("heading_type", "section"),
                parent_id=str(pred.get("parent_id")),
                left_sibling_id=str(pred.get("left_sibling_id")),
                confidence=pred.get("confidence", "medium"),
                reasoning=pred.get("reasoning", ""),
                page=page,
                features=features
            )

            self.nodes_map[node_id] = node

    def _insert_nodes_in_order(self, predictions: List[Dict[str, Any]]):
        """
        按阅读顺序插入节点（论文的 Tree Insertion Algorithm）

        核心逻辑：
        1. 遍历每个标题 sec_i (按阅读顺序)
        2. 候选位置 = 已插入的所有节点（右支路）
        3. 对每个候选位置 sec_r，计算综合得分：
           - 是否匹配 parent_id
           - 是否匹配 left_sibling_id
        4. 选择得分最高的位置，将 sec_i 插入为其最右子节点

        Args:
            predictions: 预测结果列表（已按阅读顺序排列）
        """
        if self.verbose:
            print(f"[TreeConstructor] 开始逐个插入节点...")

        for i, pred in enumerate(predictions):
            node_id = str(pred["id"])
            node = self.nodes_map[node_id]

            if self.verbose and (i % 10 == 0 or i < 5):
                print(f"[TreeConstructor]   [{i+1}/{len(predictions)}] 插入节点 id={node_id}, text='{node.text[:30]}'")

            # 如果是第一个节点，直接作为根节点
            if i == 0:
                self.root_nodes.append(node)
                if self.verbose:
                    print(f"[TreeConstructor]     -> 作为第一个根节点")
                continue

            # 获取当前的右支路候选位置
            candidate_nodes = self._get_rightmost_path()

            # 如果 parent_id 指向自己，说明是新的根节点
            if node.parent_id == node_id:
                self.root_nodes.append(node)
                if self.verbose:
                    print(f"[TreeConstructor]     -> 作为新的根节点 (parent_id 指向自己)")
                continue

            # 寻找最佳插入位置
            best_candidate = self._find_best_insertion_point(node, candidate_nodes)

            if best_candidate:
                # 插入为最右子节点
                best_candidate.add_child(node)
                if self.verbose:
                    print(f"[TreeConstructor]     -> 插入到 id={best_candidate.id} 的最右子节点")
            else:
                # 找不到合适位置，作为根节点
                self.root_nodes.append(node)
                if self.verbose:
                    print(f"[TreeConstructor]     -> 找不到合适位置，作为根节点")

    def _get_rightmost_path(self) -> List[TreeNode]:
        """
        获取当前树的最右支路上的所有节点（作为插入候选位置）

        最右支路 = 从每个根节点开始，不断往最右子节点走，直到叶子节点

        Returns:
            候选节点列表
        """
        candidates = []

        # 遍历所有根节点
        for root in self.root_nodes:
            candidates.append(root)

            # 沿着最右子节点一直走到底
            current = root
            while current.children:
                rightmost_child = current.get_rightmost_child()
                candidates.append(rightmost_child)
                current = rightmost_child

        return candidates

    def _find_best_insertion_point(
        self,
        node: TreeNode,
        candidate_nodes: List[TreeNode]
    ) -> Optional[TreeNode]:
        """
        寻找最佳插入位置

        论文算法：
        1. 对每个候选节点，计算 parent_score 和 sibling_score
        2. 融合两个得分（这里使用简单的布尔匹配）
        3. 返回得分最高的候选节点

        简化版本：
        - 优先匹配 parent_id
        - 如果多个候选匹配 parent_id，选择最后一个（最右边的）

        Args:
            node: 待插入的节点
            candidate_nodes: 候选插入位置列表

        Returns:
            最佳候选节点，如果找不到则返回 None
        """
        # 第一优先级：严格匹配 parent_id
        parent_matches = [c for c in candidate_nodes if c.id == node.parent_id]
        if parent_matches:
            # 返回最后一个匹配（最右边的）
            return parent_matches[-1]

        # 第二优先级：匹配 left_sibling_id 的父节点
        # 如果 left_sibling_id 指向某个节点，那么新节点应该插入到该节点的父节点下
        if node.left_sibling_id and node.left_sibling_id != node.id:
            left_sibling = self.nodes_map.get(node.left_sibling_id)
            if left_sibling and left_sibling.parent:
                return left_sibling.parent

        # 第三优先级：使用启发式规则
        # 返回候选列表中最后一个节点（假设是最可能的父节点）
        if candidate_nodes:
            return candidate_nodes[-1]

        return None

    def _calculate_levels(self):
        """
        计算每个节点的层级（level）

        根节点 level=1，每往下一层 +1
        """
        def set_level(node: TreeNode, current_level: int):
            node.level = current_level
            for child in node.children:
                set_level(child, current_level + 1)

        for root in self.root_nodes:
            set_level(root, 1)

    def _build_result(self) -> Dict[str, Any]:
        """
        构建最终结果

        Returns:
            包含树结构和统计信息的字典
        """
        # 序列化树结构
        tree_structure = [root.to_dict(include_children=True) for root in self.root_nodes]

        # 统计层级分布
        level_distribution = defaultdict(int)
        for node in self.nodes_map.values():
            if node.level:
                level_distribution[f"level_{node.level}"] += 1

        # 统计置信度分布
        confidence_distribution = defaultdict(int)
        for node in self.nodes_map.values():
            confidence_distribution[node.confidence] += 1

        return {
            "tree": tree_structure,
            "summary": {
                "total_headings": len(self.nodes_map),
                "root_nodes": len(self.root_nodes),
                "level_distribution": dict(level_distribution),
                "confidence_distribution": dict(confidence_distribution)
            }
        }

    def print_tree(self, max_depth: Optional[int] = None):
        """
        打印树结构（调试用）

        Args:
            max_depth: 最大打印深度，None 表示打印所有层级
        """
        def print_node(node: TreeNode, depth: int = 0, prefix: str = ""):
            if max_depth is not None and depth >= max_depth:
                return

            # 打印当前节点
            indent = "  " * depth
            text_preview = node.text[:40] if node.text else "(无文本)"
            print(f"{indent}{prefix}[L{node.level}] {node.id}: {text_preview} ({node.heading_type})")

            # 递归打印子节点
            for i, child in enumerate(node.children):
                is_last = (i == len(node.children) - 1)
                child_prefix = "└─ " if is_last else "├─ "
                print_node(child, depth + 1, child_prefix)

        print("\n" + "="*80)
        print("树结构预览:")
        print("="*80)
        for i, root in enumerate(self.root_nodes):
            print(f"\n根节点 #{i+1}:")
            print_node(root)
        print("="*80 + "\n")


# 便捷函数
def construct_tree_from_predictions(
    predictions: List[Dict[str, Any]],
    candidates_map: Optional[Dict[str, Dict[str, Any]]] = None,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    从大模型预测结果构建层级树（便捷函数）

    Args:
        predictions: 大模型预测的标题列表
        candidates_map: 可选的候选项映射（id -> 原始候选数据）
        verbose: 是否打印详细信息

    Returns:
        层级树结构
    """
    constructor = TreeConstructor(verbose=verbose)
    return constructor.build_tree_from_predictions(predictions, candidates_map)


if __name__ == "__main__":
    # 测试示例
    print("""
TreeConstructor - 基于 Detect-Order-Construct 论文的树构建算法
================================================================

核心思路：
1. 大模型预测每个标题的 parent_id 和 left_sibling_id
2. 按阅读顺序逐个插入标题，构建层级树
3. 每次插入时，融合 parent 和 sibling 的打分，选择最佳插入位置

使用方法：
----------

from tender_ontology.utils.document_struct.tree import TreeConstructor

# 创建树构建器
constructor = TreeConstructor(verbose=True)

# 从预测结果构建树
predictions = [
    {
        "id": 1,
        "is_heading": True,
        "heading_type": "section",
        "parent_id": 1,  # 指向自己 = 根节点
        "left_sibling_id": 1,
        "confidence": "high",
        "reasoning": "第一章标题"
    },
    {
        "id": 5,
        "is_heading": True,
        "heading_type": "subsection",
        "parent_id": 1,  # 父节点是 id=1
        "left_sibling_id": 5,  # 指向自己 = 该层第一个
        "confidence": "high",
        "reasoning": "第一章的第一个小节"
    },
    # ...
]

result = constructor.build_tree_from_predictions(predictions)

# 打印树结构
constructor.print_tree(max_depth=3)
    """)

    # 简单测试
    test_predictions = [
        {
            "id": 1,
            "is_heading": True,
            "heading_type": "section",
            "parent_id": 1,
            "left_sibling_id": 1,
            "confidence": "high",
            "reasoning": "第一章"
        },
        {
            "id": 5,
            "is_heading": True,
            "heading_type": "subsection",
            "parent_id": 1,
            "left_sibling_id": 5,
            "confidence": "high",
            "reasoning": "第一章第一节"
        },
        {
            "id": 10,
            "is_heading": True,
            "heading_type": "subsection",
            "parent_id": 1,
            "left_sibling_id": 5,
            "confidence": "high",
            "reasoning": "第一章第二节"
        },
        {
            "id": 20,
            "is_heading": True,
            "heading_type": "section",
            "parent_id": 20,
            "left_sibling_id": 1,
            "confidence": "high",
            "reasoning": "第二章"
        }
    ]

    test_candidates_map = {
        "1": {"id": 1, "text": "第一章 项目概述", "page": 1},
        "5": {"id": 5, "text": "一、项目背景", "page": 2},
        "10": {"id": 10, "text": "二、项目目标", "page": 3},
        "20": {"id": 20, "text": "第二章 技术方案", "page": 5}
    }

    print("\n" + "="*80)
    print("运行测试示例...")
    print("="*80)

    constructor = TreeConstructor(verbose=True)
    result = constructor.build_tree_from_predictions(
        test_predictions,
        test_candidates_map
    )

    constructor.print_tree()

    print("\n结果摘要:")
    print(result["summary"])