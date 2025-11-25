"""
LabeledJsonConverter - 将 Docling JSON 转换为精简的 labeled 格式

功能：
1. 合并 texts 和 tables，按文档顺序排列
2. 提取核心字段：label, text, bbox, page_no
3. 将表格转换为 HTML 格式
"""

import json
import re
from typing import Dict, List, Any, Optional
from pathlib import Path
from .artifact_converter import BaseConverter


class LabeledJsonConverter(BaseConverter):
    """将 Docling 完整 JSON 转换为精简的 labeled JSON"""

    # 零宽字符正则表达式：匹配常见的零宽字符
    ZERO_WIDTH_CHARS = re.compile(
        r'[\u200B\u200C\u200D\uFEFF\u00AD]'  # ZWSP, ZWNJ, ZWJ, BOM, Soft Hyphen
    )

    def __init__(self, debug: bool = False, process_tables: bool = True, sort_by_page: bool = False):
        """
        初始化转换器

        Args:
            debug: 是否启用调试输出
            process_tables: 是否处理表格 (False 时跳过表格转换，节省时间)
            sort_by_page: 是否按页码+位置排序 (False 时按 Docling 文档顺序排序)
        """
        super().__init__(debug=debug)
        self.process_tables = process_tables
        self.sort_by_page = sort_by_page
        self.ref_map = {}

    @staticmethod
    def remove_zero_width_chars(text: str) -> str:
        """
        移除字符串中的零宽字符

        Args:
            text: 输入文本

        Returns:
            清理后的文本
        """
        return LabeledJsonConverter.ZERO_WIDTH_CHARS.sub('', text)

    def convert(self, docling_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换 Docling JSON 为 labeled JSON

        Args:
            docling_json: Docling 完整 JSON 数据

        Returns:
            精简的 labeled JSON 数据（每个 item 包含多个 bbox）
        """
        # 构建引用映射（用于表格单元格）
        self.ref_map = self._build_ref_map(docling_json)

        if self.debug:
            print(f"  [DEBUG] ref_map 总共 {len(self.ref_map)} 个条目")

        # 构建父子关系映射（用于判断 text 是否在表格内）
        parent_map = self._build_parent_map(docling_json)

        if self.debug:
            print(f"  [DEBUG] parent_map 总共 {len(parent_map)} 个条目")

        # 构建文档元素映射（用于排序）
        # 递归遍历 body 树，按照阅读顺序（children 的顺序）给每个元素分配序号
        element_order = {}
        self._build_reading_order(docling_json, element_order)

        # 收集所有元素（texts + tables）
        all_elements = []

        # 统计过滤的表格文本
        texts_in_table = 0

        # 添加 texts - 保留所有 bbox，但跳过表格内的 text
        for idx, item in enumerate(docling_json.get("texts", [])):
            self_ref = item.get("self_ref", "")

            # 始终跳过表格内的文本（表格内容不应该作为独立文本输出）
            if self._is_in_table(self_ref, parent_map):
                texts_in_table += 1
                continue

            order_idx = element_order.get(self_ref, 999999)

            label = item.get("label", "unknown")
            text = self.remove_zero_width_chars(item.get("text", ""))

            # 提取所有 bbox（不只是第一个）
            bboxes = self._extract_all_bboxes(item)

            # 获取第一个 bbox 的页码和位置（用于页码排序）
            first_page = bboxes[0]["page"] if bboxes else 9999
            first_top = bboxes[0]["t"] if bboxes else 9999

            element_data = {
                "order": order_idx,
                "page": first_page,
                "top": first_top,
                "label": label,
                "text": text,
                "bboxes": bboxes
            }

            # 如果是 section_header，添加 level 字段（如果存在）
            if label == "section_header" and "level" in item:
                element_data["level"] = item["level"]

            all_elements.append(element_data)

        if self.debug and texts_in_table > 0:
            print(f"  [DEBUG] 过滤掉 {texts_in_table} 个表格内的文本")

        # 添加 tables (只在 process_tables=True 时处理)
        if self.process_tables:
            for table_idx, table in enumerate(docling_json.get("tables", [])):
                self_ref = table.get("self_ref", "")
                order_idx = element_order.get(self_ref, 999999)

                # 提取所有 bbox
                bboxes = self._extract_all_bboxes(table)

                # 获取第一个 bbox 的页码和位置（用于页码排序）
                first_page = bboxes[0]["page"] if bboxes else 9999
                first_top = bboxes[0]["t"] if bboxes else 9999

                # 转换表格为 HTML 字符串
                table_html = self._table_to_html(table.get("data", {}), table_idx)

                all_elements.append({
                    "order": order_idx,
                    "page": first_page,
                    "top": first_top,
                    "label": "table",
                    "text": table_html,
                    "bboxes": bboxes
                })
        elif self.debug:
            table_count = len(docling_json.get("tables", []))
            if table_count > 0:
                print(f"  [DEBUG] 跳过 {table_count} 个表格的处理 (process_tables=False)")

        # 按文档顺序排序
        all_elements.sort(key=lambda x: x["order"])

        # 移除临时的 order 字段，添加最终的 id
        labeled_items = []
        for idx, elem in enumerate(all_elements):
            elem.pop("order", None)
            item_data = {
                "id": idx,
                "label": elem["label"],
                "text": elem["text"],
                "bboxes": elem["bboxes"]
            }

            # 保留 level 字段（如果存在）
            if "level" in elem:
                item_data["level"] = elem["level"]

            labeled_items.append(item_data)

        # 构建最终 JSON
        return {
            "document_name": docling_json.get("name", ""),
            "total_items": len(labeled_items),
            "items": labeled_items
        }

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
        labeled_json = self.convert(docling_json)

        output_path.write_text(
            json.dumps(labeled_json, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

        if self.debug:
            print(f"  ✅ Labeled JSON 已保存: {output_path} (共 {labeled_json['total_items']} 个元素)")

    def _build_ref_map(self, docling_json: Dict[str, Any]) -> Dict[str, str]:
        """
        构建 cref 到文本内容的映射

        Args:
            docling_json: Docling 完整 JSON 数据

        Returns:
            引用映射字典
        """
        ref_map = {}

        # 添加 texts 映射
        for item in docling_json.get("texts", []):
            self_ref = item.get("self_ref", "")
            text = item.get("text", "")
            if self_ref:
                ref_map[self_ref] = text

        # 添加 groups 映射（递归收集所有子文本）
        for group in docling_json.get("groups", []):
            self_ref = group.get("self_ref", "")
            children = group.get("children", [])

            # 收集所有子元素的文本
            group_texts = []
            for child in children:
                child_ref = child.get("cref", "")
                if child_ref in ref_map:
                    group_texts.append(ref_map[child_ref])

            if self_ref and group_texts:
                ref_map[self_ref] = " ".join(group_texts)

        return ref_map

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

    def _extract_prov_info(self, item: Dict[str, Any]) -> tuple:
        """
        从 item 的 prov 字段中提取 page_no 和 bbox（兼容旧版本）

        Args:
            item: 包含 prov 字段的元素

        Returns:
            (page_no, bbox) 元组
        """
        page_no = None
        bbox = None
        prov = item.get("prov", [])
        if prov and len(prov) > 0:
            page_no = prov[0].get("page_no")
            bbox = prov[0].get("bbox")

        return page_no, bbox

    def _table_to_html(
        self,
        table_data: Dict[str, Any],
        table_idx: int = 0
    ) -> str:
        """
        将 Docling 表格数据转换为 HTML 字符串

        Args:
            table_data: 表格数据（data 字段）
            table_idx: 表格索引（用于调试）

        Returns:
            HTML 格式的表格字符串
        """
        if not table_data or "grid" not in table_data:
            return "<table></table>"

        grid = table_data["grid"]
        rows_html = []

        if self.debug:
            print(f"  [DEBUG] Table {table_idx}: grid 有 {len(grid)} 行")

        for row_idx, row in enumerate(grid):
            cells_html = []
            for col_idx, cell in enumerate(row):
                # 优先从 cell.text 获取文本
                cell_text = cell.get("text", "")

                # DEBUG: 打印第一个表格的第一个单元格
                if self.debug and table_idx == 0 and row_idx == 0 and col_idx == 0:
                    print(f"  [DEBUG] 表格0 单元格[0][0]:")
                    print(f"    cell.text = '{cell_text}'")
                    print(f"    cell.ref = {cell.get('ref')}")
                    if "ref" in cell:
                        ref_cref = cell["ref"].get("cref", "")
                        print(f"    ref_cref = '{ref_cref}'")
                        print(f"    ref_cref in ref_map? {ref_cref in self.ref_map}")
                        if ref_cref in self.ref_map:
                            print(f"    ref_map['{ref_cref}'] = '{self.ref_map[ref_cref][:100]}'")

                # 如果 cell.text 为空，尝试从 ref 获取
                if not cell_text and "ref" in cell:
                    ref_cref = cell["ref"].get("cref", "")
                    if ref_cref in self.ref_map:
                        cell_text = self.ref_map[ref_cref]

                # 判断是表头还是普通单元格
                is_header = cell.get("column_header", False) or cell.get("row_header", False)
                tag = "th" if is_header else "td"

                # 处理跨行跨列
                attrs = []
                row_span = cell.get("row_span", 1)
                col_span = cell.get("col_span", 1)
                if row_span > 1:
                    attrs.append(f'rowspan="{row_span}"')
                if col_span > 1:
                    attrs.append(f'colspan="{col_span}"')

                attr_str = " " + " ".join(attrs) if attrs else ""
                cells_html.append(f"<{tag}{attr_str}>{cell_text}</{tag}>")

            rows_html.append("<tr>" + "".join(cells_html) + "</tr>")

        return "<table>" + "".join(rows_html) + "</table>"