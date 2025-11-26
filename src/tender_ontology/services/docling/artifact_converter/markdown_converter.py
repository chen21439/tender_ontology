"""
MarkdownJsonConverter - 只提取段落和章节标题

用途：
1. 提取文档的主要文本内容（段落 + 标题）
2. 包含完整的 page、bbox、text 信息
3. 用于 Markdown 渲染或文档阅读
"""

import json
import re
from typing import Dict, List, Any
from pathlib import Path
from .base_converter import BaseConverter


class MarkdownJsonConverter(BaseConverter):
    """将 Docling JSON 转换为只包含段落和标题的 Markdown JSON"""

    # 零宽字符正则表达式：匹配常见的零宽字符
    ZERO_WIDTH_CHARS = re.compile(
        r'[\u200B\u200C\u200D\uFEFF\u00AD]'  # ZWSP, ZWNJ, ZWJ, BOM, Soft Hyphen
    )

    def __init__(self, debug: bool = False):
        """
        初始化转换器

        Args:
            debug: 是否启用调试输出
        """
        super().__init__(debug=debug)

    @staticmethod
    def remove_zero_width_chars(text: str) -> str:
        """
        移除字符串中的零宽字符

        Args:
            text: 输入文本

        Returns:
            清理后的文本
        """
        return MarkdownJsonConverter.ZERO_WIDTH_CHARS.sub('', text)

    def convert(self, docling_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换 Docling JSON，只提取段落和章节标题

        Args:
            docling_json: Docling 完整 JSON 数据

        Returns:
            只包含段落和标题的 JSON 数据
        """
        # 构建父子关系映射（用于判断 text 是否在表格内）
        parent_map = self._build_parent_map(docling_json)

        # 构建文档元素映射（用于排序）
        # 递归遍历 body 树，按照阅读顺序（children 的顺序）给每个元素分配序号
        element_order = {}
        self._build_reading_order(docling_json, element_order)

        # 收集段落和标题
        markdown_items = []
        texts_in_table = 0

        for item in docling_json.get("texts", []):
            label = item.get("label", "")

            # 只保留 text 和 section_header
            if label not in ["text", "section_header"]:
                continue

            self_ref = item.get("self_ref", "")

            # 始终跳过表格内的文本（表格内容不应该作为独立文本输出）
            if self._is_in_table(self_ref, parent_map):
                texts_in_table += 1
                continue

            order_idx = element_order.get(self_ref, 999999)

            text = self.remove_zero_width_chars(item.get("text", ""))

            # 提取所有 bbox
            bboxes = self._extract_all_bboxes(item)

            # 获取页码（取第一个 bbox 的页码）
            page = bboxes[0]["page"] if bboxes else None

            # 构建基本数据
            item_data = {
                "order": order_idx,
                "label": label,
                "text": text,
                "page": page,
                "bboxes": bboxes
            }

            # 如果是 section_header，添加 level 字段
            if label == "section_header" and "level" in item:
                item_data["level"] = item["level"]

            markdown_items.append(item_data)

        # 按文档顺序排序
        markdown_items.sort(key=lambda x: x["order"])

        # 移除临时的 order 字段，添加最终的 id
        items = []
        for idx, item in enumerate(markdown_items):
            item.pop("order", None)
            final_item = {
                "id": idx,
                "label": item["label"],
                "text": item["text"],
                "page": item["page"],
                "bboxes": item["bboxes"]
            }

            # 保留 level 字段（如果存在）
            if "level" in item:
                final_item["level"] = item["level"]

            items.append(final_item)

        if self.debug:
            print(f"  [DEBUG] 提取了 {len(items)} 个段落/标题")
            text_count = sum(1 for i in items if i["label"] == "text")
            header_count = sum(1 for i in items if i["label"] == "section_header")
            print(f"  [DEBUG] 其中: {header_count} 个标题, {text_count} 个段落")

        # 直接返回数组（不需要外层包装）
        return items

    def convert_and_save(
        self,
        docling_json: Dict[str, Any],
        output_path: Path
    ) -> None:
        """
        转换并保存为 JSON 文件

        Args:
            docling_json: Docling 完整 JSON 数据
            output_path: 输出文件路径
        """
        markdown_json = self.convert(docling_json)

        output_path.write_text(
            json.dumps(markdown_json, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

        if self.debug:
            print(f"  ✅ Markdown JSON 已保存: {output_path} (共 {len(markdown_json)} 个元素)")

    def _extract_all_bboxes(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        从 item 的 prov 字段中提取所有 bbox

        Args:
            item: 包含 prov 字段的元素

        Returns:
            bbox 列表，每个 bbox 包含 page, l, t, r, b, coord_origin, charspan
        """
        bboxes = []
        prov_list = item.get("prov", [])

        for p in prov_list:
            page_no = p.get("page_no")
            bbox = p.get("bbox")
            charspan = p.get("charspan")

            if bbox is None:
                continue

            bbox_data = {
                "page": page_no,
                "l": bbox.get("l"),
                "t": bbox.get("t"),
                "r": bbox.get("r"),
                "b": bbox.get("b"),
                "coord_origin": bbox.get("coord_origin", "BOTTOMLEFT")
            }

            # 可选：添加 charspan
            if charspan:
                bbox_data["charspan"] = charspan

            bboxes.append(bbox_data)

        return bboxes