"""
TitleMarkdownConverter - 生成带 ID 锚点的 Markdown 文件

功能：
1. 基于页面坐标排序（page + top），保证从上到下的阅读顺序
2. 在章节标题后添加 {id=texts-N} 锚点标记
3. 表格转为 Markdown 格式
4. 可用于后续通过 ID 定位到具体位置（page、bbox）
"""

import re
from typing import Dict, List, Any
from pathlib import Path
from .base_converter import BaseConverter


class TitleMarkdownConverter(BaseConverter):
    """将 Docling JSON 转换为带 ID 锚点的 Markdown"""

    def __init__(self, debug: bool = False, process_tables: bool = True):
        """
        初始化转换器

        Args:
            debug: 是否启用调试输出
            process_tables: 是否处理表格
        """
        super().__init__(debug=debug)
        self.process_tables = process_tables
        self.ref_map = {}

    def convert(self, docling_json: Dict[str, Any]) -> str:
        """
        转换 Docling JSON 为带 ID 锚点的 Markdown

        Args:
            docling_json: Docling 完整 JSON 数据

        Returns:
            带 ID 锚点的 Markdown 字符串
        """
        # 构建引用映射（用于表格单元格）
        self.ref_map = self._build_ref_map(docling_json)

        # 构建父子关系映射（用于判断 text 是否在表格内）
        parent_map = self._build_parent_map(docling_json)

        # 构建文档元素映射（用于排序）
        element_order = {}
        self._build_reading_order(docling_json, element_order)

        # 收集所有元素（texts + tables）
        all_elements = []
        texts_in_table = 0

        # 添加 texts
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

            # 获取页面位置（使用基类方法）
            page_no, top = self.get_element_position(item)
            text = self.remove_zero_width_chars(item.get("text", ""))

            # 使用统一 ID
            node_id = self.normalize_id(self_ref)

            # 获取 DFS 顺序
            order_idx = element_order.get(self_ref, 999999)

            element_data = {
                "order": order_idx,
                "page_no": page_no,
                "top": top,
                "id": node_id,
                "label": label,
                "text": text
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

                # 转换表格为 HTML 字符串
                table_html = self._table_to_html(table.get("data", {}))

                # 跳过空表格
                if not table_html:
                    continue

                # 获取页面位置（使用基类方法）
                page_no, top = self.get_element_position(table)

                # 使用统一 ID
                node_id = self.normalize_id(self_ref)

                # 获取 DFS 顺序
                order_idx = element_order.get(self_ref, 999999)

                all_elements.append({
                    "order": order_idx,
                    "page_no": page_no,
                    "top": top,
                    "id": node_id,
                    "label": "table",
                    "text": table_html
                })

        # 统一排序：先按 body 树 DFS 顺序分页，然后页内按 bbox 位置排序
        all_elements = self.sort_elements_by_page_and_position(
            all_elements,
            page_key="page_no",
            top_key="top",
            order_key="order",
            use_topleft_coord=False  # 使用原始左下角坐标系的 top 值
        )

        # 移除临时字段
        for elem in all_elements:
            elem.pop("order", None)

        # 生成 Markdown（标题之间只保留头尾各2行内容）
        markdown_lines = []

        # 按标题分组，收集每个标题下的内容
        sections = []  # [(header_elem, [content_elems]), ...]
        current_header = None
        current_content = []

        for elem in all_elements:
            if elem["label"] == "section_header":
                # 保存上一个 section
                if current_header is not None or current_content:
                    sections.append((current_header, current_content))
                current_header = elem
                current_content = []
            else:
                current_content.append(elem)

        # 保存最后一个 section
        if current_header is not None or current_content:
            sections.append((current_header, current_content))

        # 生成 Markdown
        for header_elem, content_elems in sections:
            # 输出标题
            if header_elem is not None:
                level = header_elem.get("level", 1)
                prefix = "#" * level
                markdown_lines.append(f"{prefix} {header_elem['text']} {{id={header_elem['id']}}}\n")

            # 输出内容（头尾各保留2行）
            if len(content_elems) <= 4:
                # 内容少于等于4行，全部输出
                for elem in content_elems:
                    self._append_element_to_markdown(elem, markdown_lines)
            else:
                # 头2行
                for elem in content_elems[:2]:
                    self._append_element_to_markdown(elem, markdown_lines)
                # 省略标记
                markdown_lines.append(f"... (省略 {len(content_elems) - 4} 项内容) ...\n\n")
                # 尾2行
                for elem in content_elems[-2:]:
                    self._append_element_to_markdown(elem, markdown_lines)

        markdown_content = "".join(markdown_lines)

        if self.debug:
            header_count = sum(1 for e in all_elements if e["label"] == "section_header")
            text_count = sum(1 for e in all_elements if e["label"] == "text")
            table_count = sum(1 for e in all_elements if e["label"] == "table")
            print(f"  [DEBUG] 生成 Markdown: {header_count} 个标题, {text_count} 个段落, {table_count} 个表格")

        return markdown_content

    def _append_element_to_markdown(self, elem: Dict[str, Any], markdown_lines: List[str]) -> None:
        """
        将单个元素添加到 Markdown 行列表

        Args:
            elem: 元素数据
            markdown_lines: Markdown 行列表（会被修改）
        """
        label = elem["label"]
        text = elem["text"]
        node_id = elem["id"]

        if label == "text":
            # 普通段落
            markdown_lines.append(f"{text}\n\n")
        elif label == "list_item":
            # 列表项
            markdown_lines.append(f"- {text}\n")
        elif label == "table":
            # 表格：转为 Markdown 格式，行数较多时只保留前后各2行
            table_md = self._table_to_markdown(text)
            if table_md:
                markdown_lines.append(f"{table_md}\n\n")
        else:
            # 其他类型
            markdown_lines.append(f"{text}\n\n")

    def _table_to_markdown(self, table_html: str) -> str:
        """
        将表格 HTML 转换为 Markdown 表格格式，只保留前后各2行

        Args:
            table_html: 完整的表格 HTML

        Returns:
            Markdown 格式的表格
        """
        import re

        # 提取所有 <tr>...</tr> 行
        rows = re.findall(r'<tr>.*?</tr>', table_html, re.DOTALL)

        if not rows:
            return ""

        # 将每行转换为 Markdown 格式
        def row_to_markdown(row_html: str) -> str:
            # 提取所有单元格内容
            cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row_html, re.DOTALL)
            # 清理单元格内容，去除多余空白和换行
            cells = [re.sub(r'\s+', ' ', cell).strip() for cell in cells]
            return "| " + " | ".join(cells) + " |"

        # 转换所有行
        md_rows = [row_to_markdown(row) for row in rows]

        if len(md_rows) <= 4:
            # 行数少于等于4，保留全部
            # 添加表头分隔行（在第一行后）
            if len(md_rows) >= 1:
                col_count = md_rows[0].count("|") - 1
                separator = "|" + "|".join(["---"] * col_count) + "|"
                md_rows.insert(1, separator)
            return "\n".join(md_rows)

        # 前2行 + 省略标记 + 后2行
        head_rows = md_rows[:2]
        tail_rows = md_rows[-2:]
        omitted_count = len(md_rows) - 4

        # 添加表头分隔行
        col_count = head_rows[0].count("|") - 1
        separator = "|" + "|".join(["---"] * col_count) + "|"

        result = [head_rows[0], separator, head_rows[1]]
        result.append(f"| ... (省略 {omitted_count} 行) ... |")
        result.extend(tail_rows)

        return "\n".join(result)

    def convert_and_save(
        self,
        docling_json: Dict[str, Any],
        output_path: Path
    ) -> None:
        """
        转换并保存为 Markdown 文件

        Args:
            docling_json: Docling 完整 JSON 数据
            output_path: 输出文件路径
        """
        markdown_content = self.convert(docling_json)

        output_path.write_text(markdown_content, encoding='utf-8')

        if self.debug:
            print(f"  ✅ Title Markdown 已保存: {output_path}")

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

        # 添加 groups 映射
        for group in docling_json.get("groups", []):
            self_ref = group.get("self_ref", "")
            children = group.get("children", [])

            group_texts = []
            for child in children:
                child_ref = child.get("cref", "")
                if child_ref in ref_map:
                    group_texts.append(ref_map[child_ref])

            if self_ref and group_texts:
                ref_map[self_ref] = " ".join(group_texts)

        return ref_map

    def _table_to_html(self, table_data: Dict[str, Any]) -> str:
        """
        将 Docling 表格数据转换为 HTML 字符串

        Args:
            table_data: 表格数据（data 字段）

        Returns:
            HTML 格式的表格字符串
        """
        if not table_data or "grid" not in table_data:
            return ""

        grid = table_data["grid"]
        if not grid:  # grid 为空数组
            return ""

        rows_html = []

        for row in grid:
            cells_html = []
            for cell in row:
                cell_text = cell.get("text", "")

                if not cell_text and "ref" in cell:
                    ref_cref = cell["ref"].get("cref", "")
                    if ref_cref in self.ref_map:
                        cell_text = self.ref_map[ref_cref]

                is_header = cell.get("column_header", False) or cell.get("row_header", False)
                tag = "th" if is_header else "td"

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
