"""
LabeledJsonConverter - 将 Docling JSON 转换为精简的 labeled 格式

功能：
1. 合并 texts 和 tables，按文档顺序排列
2. 提取核心字段：label, text, bbox, page_no
3. 将表格转换为 HTML 格式
"""

import json
from typing import Dict, List, Any, Optional
from pathlib import Path


class LabeledJsonConverter:
    """将 Docling 完整 JSON 转换为精简的 labeled JSON"""

    def __init__(self, debug: bool = False):
        """
        初始化转换器

        Args:
            debug: 是否启用调试输出
        """
        self.debug = debug
        self.ref_map = {}

    def convert(self, docling_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换 Docling JSON 为 labeled JSON

        Args:
            docling_json: Docling 完整 JSON 数据

        Returns:
            精简的 labeled JSON 数据
        """
        # 构建引用映射
        self.ref_map = self._build_ref_map(docling_json)

        if self.debug:
            print(f"  [DEBUG] ref_map 总共 {len(self.ref_map)} 个条目")
            for i, (k, v) in enumerate(list(self.ref_map.items())[:10]):
                print(f"    {k}: {v[:50] if len(v) > 50 else v}...")

        # 构建文档元素映射（用于排序）
        body_children = docling_json.get("body", {}).get("children", [])

        # 创建索引映射
        element_order = {}
        for idx, child in enumerate(body_children):
            cref = child.get("cref", "")
            element_order[cref] = idx

        # 收集所有元素（texts + tables）
        all_elements = []

        # 添加 texts
        for item in docling_json.get("texts", []):
            self_ref = item.get("self_ref", "")
            order_idx = element_order.get(self_ref, 999999)

            label = item.get("label", "unknown")
            text = item.get("text", "")

            # 提取 page_no 和 bbox
            page_no, bbox = self._extract_prov_info(item)

            all_elements.append({
                "order": order_idx,
                "label": label,
                "text": text,
                "page_no": page_no,
                "bbox": bbox
            })

        # 添加 tables
        for table_idx, table in enumerate(docling_json.get("tables", [])):
            self_ref = table.get("self_ref", "")
            order_idx = element_order.get(self_ref, 999999)

            # 提取 page_no 和 bbox
            page_no, bbox = self._extract_prov_info(table)

            # 转换表格为 HTML 字符串
            table_html = self._table_to_html(table.get("data", {}), table_idx)

            all_elements.append({
                "order": order_idx,
                "label": "table",
                "text": table_html,
                "page_no": page_no,
                "bbox": bbox
            })

        # 按文档顺序排序
        all_elements.sort(key=lambda x: x["order"])

        # 移除临时的 order 字段，添加最终的 id
        labeled_items = []
        for idx, elem in enumerate(all_elements):
            elem.pop("order", None)
            labeled_items.append({
                "id": idx,
                "label": elem["label"],
                "text": elem["text"],
                "page_no": elem["page_no"],
                "bbox": elem["bbox"]
            })

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

    def _extract_prov_info(self, item: Dict[str, Any]) -> tuple:
        """
        从 item 的 prov 字段中提取 page_no 和 bbox

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