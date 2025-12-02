"""
坐标转换工具

Docling 使用左下角坐标系（BOTTOMLEFT），即：
- 原点在页面左下角
- Y 轴向上为正
- t (top) 值大表示位置高

前端/常见系统使用左上角坐标系（TOPLEFT），即：
- 原点在页面左上角
- Y 轴向下为正
- t (top) 值小表示位置高

转换公式（需要知道页面高度）：
- new_t = page_height - old_b
- new_b = page_height - old_t
"""

from typing import Dict, Any, List, Optional, Union


def convert_bbox_to_topleft(
    bbox: Dict[str, Any],
    page_height: float
) -> Dict[str, Any]:
    """
    将单个 bbox 从左下角坐标系转换为左上角坐标系

    Args:
        bbox: 原始 bbox，包含 l, t, r, b, page 等字段
        page_height: 页面高度

    Returns:
        转换后的 bbox（新对象，不修改原始数据）
    """
    if not bbox:
        return bbox

    old_t = bbox.get("t", 0)
    old_b = bbox.get("b", 0)

    # 转换公式：y' = page_height - y
    # 左下角坐标系：t > b（top 值大，bottom 值小）
    # 左上角坐标系：t < b（top 值小，bottom 值大）
    new_bbox = {
        "page": bbox.get("page"),
        "l": bbox.get("l"),
        "t": round(page_height - old_t, 4),
        "r": bbox.get("r"),
        "b": round(page_height - old_b, 4),
        "coord_origin": "TOPLEFT"
    }

    # 保留可选字段
    if "charspan" in bbox:
        new_bbox["charspan"] = bbox["charspan"]

    return new_bbox


def convert_bboxes_to_topleft(
    bboxes: List[Dict[str, Any]],
    page_heights: Dict[int, float]
) -> List[Dict[str, Any]]:
    """
    批量转换 bbox 列表

    Args:
        bboxes: bbox 列表
        page_heights: 页码到页面高度的映射，如 {1: 841.89, 2: 841.89}

    Returns:
        转换后的 bbox 列表
    """
    if not bboxes:
        return bboxes

    result = []
    for bbox in bboxes:
        page_no = bbox.get("page")
        if page_no is not None and page_no in page_heights:
            new_bbox = convert_bbox_to_topleft(bbox, page_heights[page_no])
        else:
            # 没有页面高度信息，保持原样但标记
            new_bbox = bbox.copy()
            new_bbox["coord_origin"] = bbox.get("coord_origin", "BOTTOMLEFT")
        result.append(new_bbox)

    return result


def extract_page_heights_from_docling(docling_json: Dict[str, Any]) -> Dict[int, float]:
    """
    从 Docling JSON 中提取每页的高度信息

    Args:
        docling_json: Docling 完整 JSON 数据

    Returns:
        页码到页面高度的映射
    """
    page_heights = {}

    pages = docling_json.get("pages", {})
    for page_no_str, page_data in pages.items():
        try:
            page_no = int(page_no_str)
            size = page_data.get("size", {})
            height = size.get("height")
            if height is not None:
                page_heights[page_no] = height
        except (ValueError, TypeError):
            continue

    return page_heights


def convert_element_bboxes_to_topleft(
    element: Dict[str, Any],
    page_heights: Dict[int, float]
) -> Dict[str, Any]:
    """
    转换单个元素的 bboxes 字段

    Args:
        element: 包含 bboxes 字段的元素
        page_heights: 页码到页面高度的映射

    Returns:
        转换后的元素（新对象）
    """
    if not element:
        return element

    new_element = element.copy()

    if "bboxes" in element and element["bboxes"]:
        new_element["bboxes"] = convert_bboxes_to_topleft(
            element["bboxes"],
            page_heights
        )

    # 处理 location 字段（forward.json 使用）
    if "location" in element and element["location"]:
        new_element["location"] = convert_bboxes_to_topleft(
            element["location"],
            page_heights
        )

    return new_element


def convert_fulltext_to_topleft(
    fulltext_data: List[Dict[str, Any]],
    page_heights: Dict[int, float]
) -> List[Dict[str, Any]]:
    """
    转换 fulltext.json 中所有元素的坐标

    Args:
        fulltext_data: fulltext.json 数据（元素数组）
        page_heights: 页码到页面高度的映射

    Returns:
        转换后的数据
    """
    return [
        convert_element_bboxes_to_topleft(elem, page_heights)
        for elem in fulltext_data
    ]


def convert_tree_node_to_topleft(
    node: Dict[str, Any],
    page_heights: Dict[int, float]
) -> Dict[str, Any]:
    """
    递归转换树节点的坐标（用于 forward.json / tree.json）

    Args:
        node: 树节点
        page_heights: 页码到页面高度的映射

    Returns:
        转换后的节点
    """
    if not node:
        return node

    new_node = node.copy()

    # 转换 location 字段
    if "location" in node and node["location"]:
        new_node["location"] = convert_bboxes_to_topleft(
            node["location"],
            page_heights
        )

    # 转换 bboxes 字段（如果存在）
    if "bboxes" in node and node["bboxes"]:
        new_node["bboxes"] = convert_bboxes_to_topleft(
            node["bboxes"],
            page_heights
        )

    # 递归处理子节点
    if "children" in node and node["children"]:
        new_node["children"] = [
            convert_tree_node_to_topleft(child, page_heights)
            for child in node["children"]
        ]

    return new_node


def convert_forward_to_topleft(
    forward_data: Union[Dict[str, Any], List[Dict[str, Any]]],
    page_heights: Dict[int, float]
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    转换 forward.json 中所有节点的坐标

    Args:
        forward_data: forward.json 数据（可能是单个根节点或节点数组）
        page_heights: 页码到页面高度的映射

    Returns:
        转换后的数据
    """
    if isinstance(forward_data, list):
        return [
            convert_tree_node_to_topleft(node, page_heights)
            for node in forward_data
        ]
    else:
        return convert_tree_node_to_topleft(forward_data, page_heights)
