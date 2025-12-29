"""
树构建工具

将扁平数据根据 parent_id 和 relation 还原成 children 树结构

三种关系类型：
- contain: 包含关系，当前节点直接添加为 parent_id 指向的父节点的 children
- equality: 平级关系，找到兄弟节点的父节点，添加为兄弟
- connect: 连接关系，找到前一行的父节点，添加到同一层级
"""

from typing import List, Dict, Any, Optional
from tender_ontology.config.logging_config import logger


class TreeBuilder:
    """树构建器"""

    # 关系类型常量
    RELATION_CONTAIN = "contain"
    RELATION_EQUALITY = "equality"
    RELATION_CONNECT = "connect"

    def __init__(self, verbose: bool = False):
        """
        初始化树构建器

        Args:
            verbose: 是否打印详细日志
        """
        self.verbose = verbose

    def _log(self, message: str):
        """打印日志"""
        if self.verbose:
            logger.info(f"[TreeBuilder] {message}")

    def build_tree(
        self,
        flat_data: List[Dict[str, Any]],
        id_field: str = "line_id",
        parent_id_field: str = "parent_id",
        relation_field: str = "relation"
    ) -> List[Dict[str, Any]]:
        """
        根据 parent_id 和 relation 将扁平数据构建成树结构

        Args:
            flat_data: 扁平数据列表，每个元素包含 line_id, parent_id, relation 等字段
            id_field: ID 字段名，默认 "line_id"
            parent_id_field: 父节点 ID 字段名，默认 "parent_id"
            relation_field: 关系类型字段名，默认 "relation"

        Returns:
            树结构列表（根节点列表）
        """
        if not flat_data:
            return []

        self._log(f"开始构建树，节点数: {len(flat_data)}")

        # 第一遍：创建 ID -> 节点映射
        id_map: Dict[str, Dict[str, Any]] = {}
        for item in flat_data:
            # 统一转为字符串，处理 int/str 类型不一致问题
            raw_id = item.get(id_field)
            if raw_id is None or raw_id == "":
                continue
            node_id = str(raw_id)

            # 创建节点副本，添加 children 字段
            node = {**item, "children": []}
            # 记录内部使用的实际父节点 ID（用于 equality 关系）
            node["_actual_parent_id"] = None
            id_map[node_id] = node

        self._log(f"ID 映射创建完成，有效节点数: {len(id_map)}")

        # 记录根节点
        root_nodes: List[Dict[str, Any]] = []

        # 第二遍：根据 relation 建立关系
        for item in flat_data:
            raw_node_id = item.get(id_field)
            if raw_node_id is None or raw_node_id == "":
                continue
            node_id = str(raw_node_id)
            if node_id not in id_map:
                continue

            node = id_map[node_id]
            raw_parent_id = item.get(parent_id_field)
            relation = item.get(relation_field, "") or ""

            # 判断是否为根节点：parent_id 为空、None、或 "null"/"None" 字符串
            is_root = (
                raw_parent_id is None or
                raw_parent_id == "" or
                str(raw_parent_id).lower() in ("null", "none")
            )

            if is_root:
                root_nodes.append(node)
                # 不设置 _actual_parent_id，让后续节点可以使用原始 parent_id
                self._log(f"根节点: {node_id}")
                continue

            parent_id = str(raw_parent_id)

            # 根据关系类型处理
            if relation == self.RELATION_CONTAIN:
                # contain: 直接添加为子节点
                self._handle_contain(node, parent_id, id_map)

            elif relation == self.RELATION_EQUALITY:
                # equality: 找到兄弟节点的父节点，添加为兄弟
                self._handle_equality(node, parent_id, id_map, root_nodes)

            elif relation == self.RELATION_CONNECT:
                # connect: 找到前一行的父节点，添加到同一层级
                self._handle_connect(node, parent_id, id_map, root_nodes, flat_data, id_field)

            else:
                # 未知关系类型，默认当作 contain 处理
                self._log(f"未知关系类型: {relation}，节点: {node_id}，按 contain 处理")
                self._handle_contain(node, parent_id, id_map)

        self._log(f"树构建完成，根节点数: {len(root_nodes)}")

        # 清理内部字段
        self._cleanup_internal_fields(root_nodes)

        return root_nodes

    def _handle_contain(
        self,
        node: Dict[str, Any],
        parent_id: str,
        id_map: Dict[str, Dict[str, Any]]
    ):
        """
        处理 contain 关系：直接添加为子节点

        Args:
            node: 当前节点
            parent_id: 父节点 ID
            id_map: ID -> 节点映射
        """
        if parent_id in id_map:
            parent_node = id_map[parent_id]
            parent_node["children"].append(node)
            node["_actual_parent_id"] = parent_id
            self._log(f"contain: {node.get('line_id')} -> {parent_id}")
        else:
            self._log(f"contain: 父节点 {parent_id} 不存在，节点 {node.get('line_id')} 成为孤儿")

    def _handle_equality(
        self,
        node: Dict[str, Any],
        parent_id: str,
        id_map: Dict[str, Dict[str, Any]],
        root_nodes: List[Dict[str, Any]]
    ):
        """
        处理 equality 关系：找到兄弟节点的父节点，添加为兄弟

        equality 的 parent_id 指向的是"兄弟节点"，需要找到兄弟的父节点
        优先使用 _actual_parent_id，如果没有则使用原始 parent_id

        Args:
            node: 当前节点
            parent_id: 兄弟节点 ID
            id_map: ID -> 节点映射
            root_nodes: 根节点列表
        """
        if parent_id not in id_map:
            self._log(f"equality: 兄弟节点 {parent_id} 不存在，节点 {node.get('line_id')} 成为根节点")
            root_nodes.append(node)
            # 不设置 _actual_parent_id，让后续节点可以使用原始 parent_id
            return

        sibling = id_map[parent_id]
        # 优先使用 _actual_parent_id，如果没有则使用原始 parent_id
        sibling_actual_parent = sibling.get("_actual_parent_id")
        sibling_original_parent = sibling.get("parent_id")

        # 确定要使用的父节点 ID
        grand_parent_id = None
        if sibling_actual_parent and sibling_actual_parent != "__ROOT__":
            grand_parent_id = str(sibling_actual_parent)
        elif sibling_original_parent not in (None, "", "null", "None"):
            grand_parent_id = str(sibling_original_parent)

        if grand_parent_id and grand_parent_id in id_map:
            # 添加到祖父节点的 children 中
            grand_parent = id_map[grand_parent_id]
            grand_parent["children"].append(node)
            node["_actual_parent_id"] = grand_parent_id
            self._log(f"equality: {node.get('line_id')} -> {grand_parent_id} (兄弟: {parent_id})")
        else:
            # 兄弟是真正的根节点（原始 parent_id 为空），当前节点也成为根节点
            root_nodes.append(node)
            # 不设置 _actual_parent_id，让后续节点可以使用原始 parent_id
            self._log(f"equality: {node.get('line_id')} 成为根节点 (兄弟 {parent_id} 是根节点)")

    def _handle_connect(
        self,
        node: Dict[str, Any],
        parent_id: str,
        id_map: Dict[str, Dict[str, Any]],
        root_nodes: List[Dict[str, Any]],
        flat_data: List[Dict[str, Any]],
        id_field: str
    ):
        """
        处理 connect 关系：找到前一行的父节点，添加到同一层级

        connect 的 parent_id 指向的是"前一个连接节点"，需要找到前一个节点的父节点
        优先使用 _actual_parent_id，如果没有则使用原始 parent_id

        Args:
            node: 当前节点
            parent_id: 前一个连接节点 ID
            id_map: ID -> 节点映射
            root_nodes: 根节点列表
            flat_data: 原始扁平数据
            id_field: ID 字段名
        """
        if parent_id not in id_map:
            self._log(f"connect: 前一节点 {parent_id} 不存在，节点 {node.get('line_id')} 成为根节点")
            root_nodes.append(node)
            return

        prev_node = id_map[parent_id]
        # 优先使用 _actual_parent_id，如果没有则使用原始 parent_id
        prev_actual_parent = prev_node.get("_actual_parent_id")
        prev_original_parent = prev_node.get("parent_id")

        # 确定要使用的父节点 ID
        actual_parent_id = None
        if prev_actual_parent and prev_actual_parent != "__ROOT__":
            actual_parent_id = str(prev_actual_parent)
        elif prev_original_parent not in (None, "", "null", "None"):
            actual_parent_id = str(prev_original_parent)

        if actual_parent_id and actual_parent_id in id_map:
            # 添加到前一节点的父节点的 children 中
            actual_parent = id_map[actual_parent_id]
            actual_parent["children"].append(node)
            node["_actual_parent_id"] = actual_parent_id
            self._log(f"connect: {node.get('line_id')} -> {actual_parent_id} (前一节点: {parent_id})")
        else:
            # 前一节点是真正的根节点，当前节点也成为根节点
            root_nodes.append(node)
            self._log(f"connect: {node.get('line_id')} 成为根节点 (前一节点 {parent_id} 是根节点)")

    def _cleanup_internal_fields(self, nodes: List[Dict[str, Any]]):
        """
        清理内部使用的字段

        Args:
            nodes: 节点列表
        """
        for node in nodes:
            # 移除内部字段
            node.pop("_actual_parent_id", None)

            # 如果 children 为空，移除该字段
            if not node.get("children"):
                node.pop("children", None)
            else:
                # 递归清理子节点
                self._cleanup_internal_fields(node["children"])


def build_tree_from_flat_data(
    flat_data: List[Dict[str, Any]],
    id_field: str = "line_id",
    parent_id_field: str = "parent_id",
    relation_field: str = "relation",
    verbose: bool = False
) -> List[Dict[str, Any]]:
    """
    便捷函数：将扁平数据构建成树结构

    Args:
        flat_data: 扁平数据列表
        id_field: ID 字段名
        parent_id_field: 父节点 ID 字段名
        relation_field: 关系类型字段名
        verbose: 是否打印详细日志

    Returns:
        树结构列表
    """
    builder = TreeBuilder(verbose=verbose)
    return builder.build_tree(flat_data, id_field, parent_id_field, relation_field)


# ============== 格式转换：predict tree -> extract_onto format ==============

# 标题类型的 class 值（这些类型会设置 title 字段）
TITLE_CLASSES = {"section", "chapter", "title", "heading", "volume"}


def convert_tree_to_onto_format(
    tree: List[Dict[str, Any]],
    page_heights: Optional[Dict[int, float]] = None,
    verbose: bool = False
) -> List[Dict[str, Any]]:
    """
    将 predict API 的树结构转换为 extract_onto API 需要的格式

    输入格式 (predict tree):
    {
        "line_id": 0,
        "text": "招标文件信息",
        "class": "section",
        "page": "0",
        "box": [238, 72, 358, 92],
        "children": [...]
    }

    输出格式 (extract_onto):
    {
        "pid": "P_00000",
        "title": "招标文件信息",
        "content": "招标文件信息",
        "location": [{"page": 1, "l": 238, "t": 72, "r": 358, "b": 92, "coord_origin": "TOPLEFT"}],
        "children": [...]
    }

    Args:
        tree: predict API 构建的树结构
        page_heights: 页码 -> 页面高度映射（用于坐标系转换，可选）
        verbose: 是否打印详细日志

    Returns:
        转换后的树结构列表
    """
    if not tree:
        return []

    result = []
    for node in tree:
        converted = _convert_node(node, page_heights, verbose)
        if converted:
            result.append(converted)

    if verbose:
        logger.info(f"[TreeConverter] 转换完成，根节点数: {len(result)}")

    return result


def _convert_node(
    node: Dict[str, Any],
    page_heights: Optional[Dict[int, float]] = None,
    verbose: bool = False
) -> Optional[Dict[str, Any]]:
    """
    转换单个节点

    Args:
        node: 原始节点
        page_heights: 页面高度映射
        verbose: 是否打印详细日志

    Returns:
        转换后的节点
    """
    if not node:
        return None

    # 提取原始字段
    line_id = node.get("line_id", "")
    text = node.get("text", "")
    node_class = node.get("class", "")
    page = node.get("page", "")
    box = node.get("box", [])
    children = node.get("children", [])
    parent_id = node.get("parent_id", "")
    relation = node.get("relation", "")

    # pid 直接使用 line_id 的值
    pid = line_id

    # 判断是否为标题类型
    is_title = node_class.lower() in TITLE_CLASSES if node_class else False

    # 设置 title 和 content
    title = text if is_title else ""
    content = text

    # 转换 location
    location = _convert_location(page, box, page_heights)

    # 构建转换后的节点
    converted = {
        "pid": pid,
        "title": title,
        "content": content,
        "location": location,
        "class": node_class,
        "parent_id": parent_id,
        "relation": relation
    }

    # 递归转换 children
    if children:
        converted_children = []
        for child in children:
            converted_child = _convert_node(child, page_heights, verbose)
            if converted_child:
                converted_children.append(converted_child)
        if converted_children:
            converted["children"] = converted_children

    return converted


def _convert_location(
    page: Any,
    box: List[Any],
    page_heights: Optional[Dict[int, float]] = None
) -> List[Dict[str, Any]]:
    """
    转换位置信息

    输入:
        page: "0" 或 "1|2" (跨页情况)
        box: [x1, y1, x2, y2] 或 [[x1,y1,x2,y2], [x1,y1,x2,y2]] (跨页情况)

    输出:
        [{"page": 1, "l": x1, "t": y1, "r": x2, "b": y2, "coord_origin": "TOPLEFT"}, ...]

    Args:
        page: 页码（字符串，可能是 "0" 或 "1|2"）
        box: 边界框坐标
        page_heights: 页面高度映射（用于坐标系转换）

    Returns:
        location 列表
    """
    if not page and page != 0:
        return []

    locations = []

    # 处理页码
    page_str = str(page)
    pages = page_str.split("|") if "|" in page_str else [page_str]

    # 处理 box
    # box 可能是 [x1, y1, x2, y2] 或 [[...], [...]] 格式
    boxes = []
    if box:
        if isinstance(box[0], list):
            # 多个 box（跨页情况）
            boxes = box
        else:
            # 单个 box
            boxes = [box]

    for i, page_num_str in enumerate(pages):
        try:
            # 页码从 0 开始转换为从 1 开始
            page_num = int(page_num_str) + 1

            # 获取对应的 box
            if i < len(boxes) and len(boxes[i]) >= 4:
                b = boxes[i]
                x1, y1, x2, y2 = float(b[0]), float(b[1]), float(b[2]), float(b[3])

                # 坐标系转换
                # 如果有 page_heights，转换为 TOPLEFT 坐标系
                page_height = page_heights.get(page_num) if page_heights else None

                if page_height:
                    # PDF 坐标系是左下角原点，需要转换为左上角原点
                    # 假设输入的 y1, y2 是 PDF 坐标系（y1 < y2，y1 是底部）
                    # 输出: t = page_height - y2, b = page_height - y1
                    new_t = round(page_height - y2, 4)
                    new_b = round(page_height - y1, 4)
                    locations.append({
                        "page": page_num,
                        "l": round(x1, 4),
                        "t": new_t,
                        "r": round(x2, 4),
                        "b": new_b,
                        "coord_origin": "TOPLEFT"
                    })
                else:
                    # 没有页面高度，直接使用原始坐标
                    # 假设输入已经是 TOPLEFT 坐标系
                    locations.append({
                        "page": page_num,
                        "l": round(x1, 4),
                        "t": round(y1, 4),
                        "r": round(x2, 4),
                        "b": round(y2, 4),
                        "coord_origin": "TOPLEFT"
                    })
        except (ValueError, TypeError, IndexError):
            continue

    return locations


def build_and_convert_tree(
    flat_data: List[Dict[str, Any]],
    page_heights: Optional[Dict[int, float]] = None,
    verbose: bool = False
) -> List[Dict[str, Any]]:
    """
    便捷函数：构建树并转换为 extract_onto 格式

    Args:
        flat_data: 扁平数据列表
        page_heights: 页面高度映射
        verbose: 是否打印详细日志

    Returns:
        转换后的树结构列表（extract_onto 格式）
    """
    # 1. 构建树
    tree = build_tree_from_flat_data(flat_data, verbose=verbose)

    # 2. 转换格式
    return convert_tree_to_onto_format(tree, page_heights, verbose)


# ============== 测试代码 ==============

if __name__ == "__main__":
    # 测试数据
    test_data = [
        {"line_id": "1", "parent_id": None, "relation": None, "content": "第一章"},
        {"line_id": "2", "parent_id": "1", "relation": "contain", "content": "1.1 节"},
        {"line_id": "3", "parent_id": "1", "relation": "contain", "content": "1.2 节"},
        {"line_id": "4", "parent_id": "3", "relation": "equality", "content": "1.3 节（与1.2平级）"},
        {"line_id": "5", "parent_id": "2", "relation": "contain", "content": "1.1.1 小节"},
        {"line_id": "6", "parent_id": "5", "relation": "connect", "content": "1.1.1 续（与1.1.1连接）"},
        {"line_id": "7", "parent_id": None, "relation": None, "content": "第二章"},
        {"line_id": "8", "parent_id": "7", "relation": "contain", "content": "2.1 节"},
    ]

    import json

    print("=" * 60)
    print("测试数据:")
    print("=" * 60)
    for item in test_data:
        print(f"  {item}")

    print("\n" + "=" * 60)
    print("构建树:")
    print("=" * 60)

    tree = build_tree_from_flat_data(test_data, verbose=True)

    print("\n" + "=" * 60)
    print("结果:")
    print("=" * 60)
    print(json.dumps(tree, ensure_ascii=False, indent=2))