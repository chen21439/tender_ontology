"""
FulltextJsonConverter - 生成完整文档内容（统一 ID 体系）

功能：
1. 基于 labeled.json 的逻辑，保留完整的文档遍历顺序
2. 使用统一的 ID 体系：id = normalize(self_ref)，如 '#/texts/5' -> 'texts-5'
3. 保留表格内容（转 HTML）
4. 添加 docling_ref 字段用于追溯
5. 所有 artifact 可通过相同的 ID 相互关联
"""

import json
from typing import Dict, List, Any
from pathlib import Path
from .base_converter import BaseConverter


class FulltextJsonConverter(BaseConverter):
    """将 Docling JSON 转换为完整文档内容（统一 ID 体系）"""

    def __init__(self, debug: bool = False, process_tables: bool = True, convert_to_topleft: bool = True):
        """
        初始化转换器

        Args:
            debug: 是否启用调试输出
            process_tables: 是否处理表格
            convert_to_topleft: 是否将坐标转换为左上角坐标系（默认 True）
        """
        super().__init__(debug=debug, convert_to_topleft=convert_to_topleft)
        self.process_tables = process_tables
        self.ref_map = {}

    def convert(self, docling_json: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        转换 Docling JSON 为 fulltext JSON（数组格式）

        Args:
            docling_json: Docling 完整 JSON 数据

        Returns:
            元素数组，每个元素包含统一的 ID
        """
        # 提取页面高度（用于坐标转换）
        if self.convert_to_topleft:
            self._extract_page_heights(docling_json)

        # 构建引用映射（用于表格单元格）
        self.ref_map = self._build_ref_map(docling_json)

        if self.debug:
            print(f"  [DEBUG] ref_map 总共 {len(self.ref_map)} 个条目")

        # 构建父子关系映射（用于判断 text 是否在表格内）
        parent_map = self._build_parent_map(docling_json)

        if self.debug:
            print(f"  [DEBUG] parent_map 总共 {len(parent_map)} 个条目")

        # 构建文档元素映射（用于排序）
        element_order = {}
        self._build_reading_order(docling_json, element_order)

        # 收集所有元素（texts + tables）
        all_elements = []
        texts_in_table = 0

        # 添加 texts - 保留所有 bbox，但跳过表格内的 text 和页眉页脚
        skipped_headers_footers = 0
        for item in docling_json.get("texts", []):
            self_ref = item.get("self_ref", "")
            label = item.get("label", "unknown")

            # 跳过页眉和页脚
            if label in ("page_header", "page_footer"):
                skipped_headers_footers += 1
                continue

            # 跳过表格内的文本
            if self._is_in_table(self_ref, parent_map):
                texts_in_table += 1
                continue

            order_idx = element_order.get(self_ref, 999999)
            text = self.remove_zero_width_chars(item.get("text", ""))

            # 提取所有 bbox
            bboxes = self._extract_all_bboxes(item)

            # 获取第一个 bbox 的页码
            first_page = bboxes[0]["page"] if bboxes else None

            # 使用统一 ID
            node_id = self.normalize_id(self_ref)

            # 获取 top 值用于页内排序（使用原始 prov 中的 top，不受坐标转换影响）
            page_no, top = self.get_element_position(item)

            element_data = {
                "order": order_idx,
                "top": top,  # 用于页内排序
                "id": node_id,
                "docling_ref": self_ref,
                "label": label,
                "text": text,
                "page": first_page,
                "bboxes": bboxes
            }

            # 如果是 section_header，添加 level 字段
            if label == "section_header" and "level" in item:
                element_data["level"] = item["level"]

            all_elements.append(element_data)

        if self.debug and skipped_headers_footers > 0:
            print(f"  [DEBUG] 过滤掉 {skipped_headers_footers} 个页眉/页脚")

        if self.debug and texts_in_table > 0:
            print(f"  [DEBUG] 过滤掉 {texts_in_table} 个表格内的文本")

        # 添加 tables (如果启用)
        if self.process_tables:
            for table in docling_json.get("tables", []):
                self_ref = table.get("self_ref", "")
                order_idx = element_order.get(self_ref, 999999)

                # 提取所有 bbox
                bboxes = self._extract_all_bboxes(table)

                # 获取第一个 bbox 的页码
                first_page = bboxes[0]["page"] if bboxes else None

                # 转换表格为 HTML 字符串
                table_html = self._table_to_html(table.get("data", {}))

                # 使用统一 ID
                node_id = self.normalize_id(self_ref)

                # 获取 top 值用于页内排序
                page_no, top = self.get_element_position(table)

                all_elements.append({
                    "order": order_idx,
                    "top": top,  # 用于页内排序
                    "id": node_id,
                    "docling_ref": self_ref,
                    "label": "table",
                    "text": table_html,
                    "page": first_page,
                    "bboxes": bboxes
                })
        elif self.debug:
            table_count = len(docling_json.get("tables", []))
            if table_count > 0:
                print(f"  [DEBUG] 跳过 {table_count} 个表格的处理 (process_tables=False)")

        # 统一排序：先按 body 树 DFS 顺序分页，然后页内按 bbox 位置排序
        all_elements = self.sort_elements_by_page_and_position(
            all_elements,
            page_key="page",
            top_key="top",
            order_key="order",
            use_topleft_coord=False  # 使用原始左下角坐标系的 top 值
        )

        # 移除临时字段
        items = []
        for elem in all_elements:
            elem.pop("order", None)
            elem.pop("top", None)
            items.append(elem)

        if self.debug:
            print(f"  [DEBUG] 提取了 {len(items)} 个元素")
            text_count = sum(1 for i in items if i["label"] == "text")
            header_count = sum(1 for i in items if i["label"] == "section_header")
            table_count = sum(1 for i in items if i["label"] == "table")
            print(f"  [DEBUG] 其中: {header_count} 个标题, {text_count} 个段落, {table_count} 个表格")

        return items

    def convert_and_save(
        self,
        docling_json: Dict[str, Any],
        output_path: Path
    ) -> None:
        """
        转换并保存为 JSON 文件（直接保存数组）

        Args:
            docling_json: Docling 完整 JSON 数据
            output_path: 输出文件路径
        """
        fulltext_items = self.convert(docling_json)

        output_path.write_text(
            json.dumps(fulltext_items, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

        if self.debug:
            print(f"  ✅ Fulltext JSON 已保存: {output_path} (共 {len(fulltext_items)} 个元素)")

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

        如果启用了 convert_to_topleft，会自动将坐标从左下角坐标系转换为左上角坐标系

        Args:
            item: 包含 prov 字段的元素

        Returns:
            bbox 列表
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

            # 坐标转换（如果启用）
            if self.convert_to_topleft:
                bbox_data = self._convert_bbox_to_topleft(bbox_data)

            bboxes.append(bbox_data)

        return bboxes

    def _table_to_html(self, table_data: Dict[str, Any]) -> str:
        """
        将 Docling 表格数据转换为 HTML 字符串

        Args:
            table_data: 表格数据（data 字段）

        Returns:
            HTML 格式的表格字符串
        """
        if not table_data or "grid" not in table_data:
            return "<table></table>"

        grid = table_data["grid"]
        rows_html = []

        for row in grid:
            cells_html = []
            for cell in row:
                # 优先从 cell.text 获取文本
                cell_text = cell.get("text", "")

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