"""
SectionHeaderOnlyConverter - 生成只包含标题的 Markdown 文件

功能：
1. 基于页面坐标排序（page + top），保证从上到下的阅读顺序
2. 只输出 section_header 类型的内容
3. 在标题后添加 {id=texts-N} 锚点标记
4. 用于模型分析标题层级结构
"""

from typing import Dict, List, Any
from pathlib import Path
from .base_converter import BaseConverter


class SectionHeaderOnlyConverter(BaseConverter):
    """将 Docling JSON 转换为只包含标题的 Markdown"""

    def __init__(self, debug: bool = False):
        """
        初始化转换器

        Args:
            debug: 是否启用调试输出
        """
        super().__init__(debug=debug)

    def convert(self, docling_json: Dict[str, Any]) -> str:
        """
        转换 Docling JSON 为只包含标题的 Markdown

        Args:
            docling_json: Docling 完整 JSON 数据

        Returns:
            只包含标题的 Markdown 字符串
        """
        # 构建文档元素映射（用于排序）
        element_order = {}
        self._build_reading_order(docling_json, element_order)

        # 收集所有 section_header
        headers = []
        skipped_count = 0

        for item in docling_json.get("texts", []):
            label = item.get("label", "")

            # 只处理 section_header
            if label != "section_header":
                skipped_count += 1
                continue

            self_ref = item.get("self_ref", "")
            text = self.remove_zero_width_chars(item.get("text", ""))

            # 获取页面位置（使用基类方法）
            page_no, top = self.get_element_position(item)

            # 使用统一 ID（使用基类方法）
            node_id = self.normalize_id(self_ref)

            # 获取 level
            level = item.get("level", 1)

            # 获取 DFS 顺序
            order_idx = element_order.get(self_ref, 999999)

            headers.append({
                "order": order_idx,
                "page_no": page_no,
                "top": top,
                "id": node_id,
                "text": text,
                "level": level
            })

        if self.debug:
            print(f"  [DEBUG] 找到 {len(headers)} 个标题，跳过 {skipped_count} 个非标题元素")

        # 统一排序：先按 body 树 DFS 顺序分页，然后页内按 bbox 位置排序
        headers = self.sort_elements_by_page_and_position(
            headers,
            page_key="page_no",
            top_key="top",
            order_key="order",
            use_topleft_coord=False  # 使用原始左下角坐标系的 top 值
        )

        # 移除临时字段
        for h in headers:
            h.pop("order", None)

        # 生成 Markdown
        markdown_lines = []
        for header in headers:
            level = header["level"]
            prefix = "#" * level
            markdown_lines.append(f"{prefix} {header['text']} {{id={header['id']}}}\n")

        markdown_content = "".join(markdown_lines)

        if self.debug:
            print(f"  [DEBUG] 生成 Markdown: {len(headers)} 个标题")

        return markdown_content

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
            print(f"  ✅ Section Header Only Markdown 已保存: {output_path}")
