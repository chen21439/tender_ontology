"""
SectionHeaderConverter - 只提取章节标题(section_header)的转换器

用途：
1. 快速生成文档大纲/目录结构
2. 用于章节导航
3. 用于文档结构分析
"""

import json
from typing import Dict, List, Any
from pathlib import Path


class SectionHeaderConverter:
    """将 Docling JSON 转换为只包含 section_header 的 JSON"""

    def __init__(self, debug: bool = False):
        """
        初始化转换器

        Args:
            debug: 是否启用调试输出
        """
        self.debug = debug

    def convert(self, docling_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换 Docling JSON，只提取 section_header

        Args:
            docling_json: Docling 完整 JSON 数据

        Returns:
            只包含 section_header 的 JSON 数据
        """
        # 构建文档元素映射（用于排序）
        body_children = docling_json.get("body", {}).get("children", [])
        element_order = {}
        for idx, child in enumerate(body_children):
            cref = child.get("cref", "")
            if cref:
                element_order[cref] = idx

        # 收集所有 section_header
        section_headers = []

        for item in docling_json.get("texts", []):
            label = item.get("label", "")

            # 只保留 section_header
            if label != "section_header":
                continue

            self_ref = item.get("self_ref", "")
            order_idx = element_order.get(self_ref, 999999)

            text = item.get("text", "")

            # 提取所有 bbox
            bboxes = self._extract_all_bboxes(item)

            section_headers.append({
                "order": order_idx,
                "text": text,
                "bboxes": bboxes
            })

        # 按文档顺序排序
        section_headers.sort(key=lambda x: x["order"])

        # 移除临时的 order 字段，添加最终的 id
        headers = []
        for idx, header in enumerate(section_headers):
            header.pop("order", None)
            headers.append({
                "id": idx,
                "text": header["text"],
                "bboxes": header["bboxes"]
            })

        if self.debug:
            print(f"  [DEBUG] 提取了 {len(headers)} 个 section_header")

        # 构建最终 JSON
        return {
            "document_name": docling_json.get("name", ""),
            "total_headers": len(headers),
            "headers": headers
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
        headers_json = self.convert(docling_json)

        output_path.write_text(
            json.dumps(headers_json, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

        if self.debug:
            print(f"  ✅ Section Headers JSON 已保存: {output_path} (共 {headers_json['total_headers']} 个标题)")

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