"""
Unstructured 标题提取器

使用 unstructured 库解析 docx 文件，然后通过千问 API 进行标题层级分析。

流程：
1. 检测 DOCX 版本，如果是 Word 2007 则先添加 paraId
2. 使用 unstructured 解析 docx，生成 fulltext.md 和 sectionHeader_only.md
3. 使用 HeadingValidator 进行二次标题判定
4. 调用内部千问 API 进行两阶段标题提取

使用方式：
    from tender_ontology.utils.unstructured import UnstructuredHeadingExtractor

    extractor = UnstructuredHeadingExtractor()
    result = extractor.extract_full_hierarchy("input.docx")
"""

import re
import json
import time
import logging

# 关闭 unstructured 的 trace 日志
logging.getLogger("unstructured.trace").setLevel(logging.WARNING)

from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

from unstructured.partition.docx import partition_docx

from .docx_preprocessor import preprocess_docx_if_needed
from .docx_xml_loader import DocxXmlLoader
from .heading_validator import HeadingValidator, HeadingInfo
from .qwen_heading_api import QwenHeadingAPI
from .chapter_processor import ChapterProcessor


class UnstructuredHeadingExtractor:
    """Unstructured 标题提取器"""

    def __init__(
        self,
        verbose: bool = True,
        inspect_elements: int = 3,
        enable_secondary_validation: bool = True
    ):
        """
        初始化提取器

        Args:
            verbose: 是否打印详细信息
            inspect_elements: 解析后打印前 N 个元素的数据结构（默认3个）
            enable_secondary_validation: 是否启用二次标题判定（默认开启）
        """
        self.verbose = verbose
        self.inspect_elements = inspect_elements
        self.enable_secondary_validation = enable_secondary_validation

        # 缓存实例
        self._xml_loader: Optional[DocxXmlLoader] = None
        self._heading_validator: Optional[HeadingValidator] = None
        self._qwen_api = QwenHeadingAPI(verbose=verbose)
        self._chapter_processor = ChapterProcessor(verbose=verbose)

    # ========== Element 数据结构检查 ==========

    def _inspect_element(self, el, index: int = 0) -> dict:
        """检查单个 element 的所有属性"""
        info = {
            "index": index,
            "type": type(el).__name__,
            "text": (el.text or "")[:100] + ("..." if len(el.text or "") > 100 else ""),
            "text_length": len(el.text or ""),
        }

        # 常用属性
        for attr in ["category", "id", "element_id"]:
            val = getattr(el, attr, None)
            if val is not None:
                info[attr] = val

        # metadata
        if hasattr(el, "metadata"):
            metadata = el.metadata
            metadata_dict = {}

            metadata_attrs = [
                "filename", "page_number", "category_depth",
                "parent_id", "languages", "detection_class_prob"
            ]

            for attr in metadata_attrs:
                val = getattr(metadata, attr, None)
                if val is not None:
                    metadata_dict[attr] = val

            if metadata_dict:
                info["metadata"] = metadata_dict

        return info

    def _print_elements_inspection(self, elements: List, count: int = 3):
        """打印前 N 个元素的数据结构"""
        # 先统计类别
        categories = {}
        for el in elements:
            cat = getattr(el, "category", None) or "Unknown"
            categories[cat] = categories.get(cat, 0) + 1

        print(f"\n{'=' * 70}")
        print(f"[Element 数据结构检查]")
        print(f"{'=' * 70}")

        print(f"\n[类别统计]")
        for cat, cnt in sorted(categories.items(), key=lambda x: -x[1]):
            print(f"  {cat}: {cnt}")

        print(f"\n[前 {count} 个元素详情]")
        for i, el in enumerate(elements[:count]):
            info = self._inspect_element(el, i)
            print(f"\n--- Element [{i}] ---")
            print(json.dumps(info, ensure_ascii=False, indent=2, default=str))

        print(f"\n{'=' * 70}\n")

    # ========== 二次标题判定（使用 XML 样式信息）==========

    def _get_xml_info_for_elements(
        self,
        docx_path: Path,
        elements: List
    ) -> Dict[int, Dict[str, Any]]:
        """
        批量获取元素的 XML 信息（alignment, is_heading_style 等）

        这是简化版本，直接使用 unstructured 已提供的 paragraph_locator

        Args:
            docx_path: docx 文件路径
            elements: unstructured 解析出的元素列表

        Returns:
            idx -> xml_info 的映射
        """
        xml_start = time.time()

        # 加载 DOCX XML（只打开一次）
        if self._xml_loader is None or str(self._xml_loader.docx_path) != str(docx_path):
            self._xml_loader = DocxXmlLoader(docx_path, verbose=False)
            self._xml_loader.load()

        xml_info_map = {}

        for idx, el in enumerate(elements):
            cat = getattr(el, "category", None) or getattr(el, "type", None)
            text = (el.text or "").strip()

            # 跳过表格
            if cat in ["Table", "TableChunk"]:
                continue

            # 获取 locator
            locator_dict = {"flat_index": idx}
            if hasattr(el, "metadata"):
                metadata = el.metadata
                if hasattr(metadata, "paragraph_locator") and metadata.paragraph_locator:
                    locator_dict = metadata.paragraph_locator

            # 定位到 XML <w:p>
            p = self._xml_loader.locate_paragraph(locator_dict)

            if p is not None:
                style = self._xml_loader.get_paragraph_style(p)

                # 判断是否是标题
                is_heading = style.is_heading_style
                if style.alignment == "center":
                    is_heading = True

                # 假居中标题判定
                FAKE_CENTER_THRESHOLD = 2000
                MAX_TITLE_LENGTH = 50
                first_line = style.ind_first_line or 0
                is_fake_centered = (
                    first_line >= FAKE_CENTER_THRESHOLD
                    and len(text) <= MAX_TITLE_LENGTH
                    and style.alignment != "center"
                )
                if is_fake_centered:
                    is_heading = True

                xml_info_map[idx] = {
                    "located": True,
                    "alignment": style.alignment,
                    "is_heading_style": is_heading,
                    "is_fake_centered": is_fake_centered,
                    "ind_first_line": style.ind_first_line,
                    "style_id": style.style_id,
                    "style_name": style.style_name,
                    "outline_level": style.outline_level
                }

        xml_time = time.time() - xml_start
        if self.verbose:
            located_count = len(xml_info_map)
            print(f"[XML提取] 定位成功: {located_count}/{len(elements)} 个元素，耗时: {xml_time:.2f} 秒")

        return xml_info_map

    # ========== 阶段0：使用 unstructured 解析 docx ==========

    def parse_docx(
        self,
        docx_path: Union[str, Path],
        include_metadata: bool = True
    ) -> tuple:
        """
        使用 unstructured 解析 docx 文件，生成 markdown 和 json 文件

        Args:
            docx_path: docx 文件路径
            include_metadata: 是否在输出中包含元数据

        Returns:
            tuple: (section_header_md_path, title_with_id_md_path, elements, paragraph_fulltext_path)
        """
        docx_path = Path(docx_path)

        if not docx_path.exists():
            raise FileNotFoundError(f"文件不存在: {docx_path}")

        if not docx_path.suffix.lower() == ".docx":
            raise ValueError(f"不是 docx 文件: {docx_path}")

        if self.verbose:
            print(f"[Unstructured] 解析 docx 文件: {docx_path.name}")

        # Step 0: 检测 DOCX 版本，如果是 Word 2007 则添加 paraId
        docx_path, preprocessed = preprocess_docx_if_needed(docx_path, verbose=self.verbose)

        # Step 1: 使用 unstructured 解析
        parse_start = time.time()
        elements = partition_docx(str(docx_path))
        parse_time = time.time() - parse_start

        if self.verbose:
            print(f"[Unstructured] 共解析出 {len(elements)} 个元素，partition_docx 耗时: {parse_time:.2f} 秒")

        # 打印元素数据结构（如果设置了 inspect_elements）
        if self.inspect_elements > 0:
            self._print_elements_inspection(elements, self.inspect_elements)

        # Step 2: 批量提取 XML 信息（获取 alignment 等属性）
        xml_info_map = {}
        if self.enable_secondary_validation:
            xml_info_map = self._get_xml_info_for_elements(docx_path, elements)

        # ========== 构建 fulltext.md ==========
        idx_to_paragraph_id = {}
        idx_to_heading_candidate = {}

        table_count = 0
        paragraph_count = 0

        # 第一遍：分配 ID 并判断标题候选项
        for idx, el in enumerate(elements):
            cat = getattr(el, "category", None) or getattr(el, "type", None)
            text = (el.text or "").strip()

            if cat in ["Table", "TableChunk"]:
                table_id = f"t{table_count:03d}-r000-c000-p000"
                idx_to_paragraph_id[idx] = table_id
                idx_to_heading_candidate[idx] = False
                if text or (hasattr(el, "metadata") and hasattr(el.metadata, "text_as_html") and el.metadata.text_as_html):
                    table_count += 1
            elif text:
                para_id = f"P_{paragraph_count:05d}"
                idx_to_paragraph_id[idx] = para_id
                paragraph_count += 1

                # 判断是否是标题候选项
                is_heading_candidate = False
                xml_info = xml_info_map.get(idx, {})
                alignment = xml_info.get("alignment") if xml_info else None

                if cat in ["Title", "Header", "SectionHeader"]:
                    is_heading_candidate = True
                if alignment == "center":
                    is_heading_candidate = True
                if xml_info.get("is_fake_centered"):
                    is_heading_candidate = True

                idx_to_heading_candidate[idx] = is_heading_candidate

        # 第二遍：生成 fulltext.md
        fulltext_md_path = docx_path.parent / f"{docx_path.stem}_unstructured_fulltext.md"
        fulltext_lines = []
        fulltext_lines.append(f"# {docx_path.stem} - 全文内容\n")
        fulltext_lines.append(f"> 提取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        fulltext_lines.append("")

        actual_table_count = 0
        actual_paragraph_count = 0

        for idx, el in enumerate(elements):
            cat = getattr(el, "category", None) or getattr(el, "type", None)
            text = (el.text or "").strip()

            if cat in ["Table", "TableChunk"]:
                html_text = None
                if hasattr(el, "metadata") and hasattr(el.metadata, "text_as_html"):
                    html_text = el.metadata.text_as_html

                table_id = idx_to_paragraph_id.get(idx, f"t{actual_table_count:03d}-r000-c000-p000")

                if html_text:
                    fulltext_lines.append(f"[Table] {table_id}")
                    fulltext_lines.append(html_text)
                    fulltext_lines.append("")
                    actual_table_count += 1
                elif text:
                    fulltext_lines.append(f"[Table] {table_id}")
                    fulltext_lines.append(text)
                    fulltext_lines.append("")
                    actual_table_count += 1
            elif text:
                para_id = idx_to_paragraph_id.get(idx, f"P_{actual_paragraph_count:05d}")
                is_heading_candidate = idx_to_heading_candidate.get(idx, False)
                xml_info = xml_info_map.get(idx, {})
                alignment = xml_info.get("alignment") if xml_info else None

                # 构建属性字符串
                attrs = f"id={para_id}"
                if alignment == "center":
                    attrs += ", align=center"
                elif xml_info.get("is_fake_centered"):
                    attrs += ", fake_center"

                # 标题候选项带 # 前缀
                if is_heading_candidate:
                    fulltext_lines.append(f"# [{cat}] {text} {{{attrs}}}")
                else:
                    fulltext_lines.append(f"- [{cat}] {text} {{{attrs}}}")

                actual_paragraph_count += 1

        fulltext_md_path.write_text("\n".join(fulltext_lines), encoding='utf-8')

        if self.verbose:
            heading_candidate_count = sum(1 for v in idx_to_heading_candidate.values() if v)
            print(f"[Unstructured] 已生成: {fulltext_md_path.name} ({actual_paragraph_count} 个段落, {actual_table_count} 个表格, {heading_candidate_count} 个标题候选)")

        # ========== 提取标题类元素 ==========
        header_types = []
        for idx, el in enumerate(elements):
            cat = getattr(el, "category", None) or getattr(el, "type", None)
            text = (el.text or "").strip()
            if not text:
                continue

            is_heading = False
            heading_source = None
            alignment = None

            xml_info = xml_info_map.get(idx, {})
            if xml_info:
                alignment = xml_info.get("alignment")

            if cat in ["Title", "Header", "SectionHeader"]:
                is_heading = True
                heading_source = f"unstructured:{cat}"

            if alignment == "center":
                if not is_heading:
                    is_heading = True
                    heading_source = "align:center"
                else:
                    heading_source += " + align:center"

            if xml_info.get("is_fake_centered"):
                if not is_heading:
                    is_heading = True
                    first_line = xml_info.get("ind_first_line", 0)
                    heading_source = f"fake_center(firstLine={first_line})"
                else:
                    first_line = xml_info.get("ind_first_line", 0)
                    heading_source += f" + fake_center(firstLine={first_line})"

            if is_heading:
                para_id = idx_to_paragraph_id.get(idx, f"P_{idx:05d}")
                header_types.append({
                    "text": text,
                    "category": cat,
                    "index": idx,
                    "id": para_id,
                    "source": heading_source,
                    "alignment": alignment
                })

        if self.verbose:
            unstructured_count = sum(1 for h in header_types if "unstructured:" in (h.get("source") or ""))
            print(f"[Unstructured] 找到 {len(header_types)} 个标题类元素 (原始: {unstructured_count})")

        # 输出路径
        section_header_md_path = docx_path.parent / f"{docx_path.stem}_unstructured_sectionHeader_only.md"
        title_with_id_md_path = docx_path.parent / f"{docx_path.stem}_unstructured_title_with_id.md"

        # 写入 sectionHeader_only.md
        with open(section_header_md_path, "w", encoding="utf-8") as f:
            f.write(f"# {docx_path.stem} - 标题结构\n\n")
            f.write(f"> 提取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"> 共 {len(header_types)} 条\n\n")

            for item in header_types:
                if include_metadata:
                    attrs = f"id={item['id']}"
                    if item.get('alignment') == 'center':
                        attrs += ", align=center"
                    f.write(f"- [{item['category']}] {item['text']} {{{attrs}}}\n")
                else:
                    f.write(f"- {item['text']}\n")

        # 写入 title_with_id.md
        with open(title_with_id_md_path, "w", encoding="utf-8") as f:
            f.write(f"# {docx_path.stem} - 标题与内容\n\n")
            f.write(f"> 提取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"> 共 {len(header_types)} 条标题\n\n")

            for item in header_types:
                idx = item['index']
                attrs = f"id={item['id']}"
                if item.get('alignment') == 'center':
                    attrs += ", align=center"
                f.write(f"## [{item['category']}] {item['text']} {{{attrs}}}\n\n")

                if idx + 1 < len(elements):
                    next_el = elements[idx + 1]
                    next_text = (next_el.text or "").strip()
                    next_cat = getattr(next_el, "category", None) or getattr(next_el, "type", None)

                    if next_cat not in ["Title", "Header", "SectionHeader"] and next_text:
                        f.write(f"{next_text}\n")

                f.write("\n")

        if self.verbose:
            print(f"[Unstructured] 已生成: {section_header_md_path.name}")
            print(f"[Unstructured] 已生成: {title_with_id_md_path.name}")

        return section_header_md_path, title_with_id_md_path, elements, fulltext_md_path

    # ========== 完整流程 ==========

    def extract_full_hierarchy(
        self,
        docx_path: Union[str, Path],
        max_workers: int = 8
    ) -> Dict[str, Any]:
        """
        完整的标题层级提取流程

        阶段0: 使用 unstructured 解析 docx
        阶段1: 提取一二级标题
        阶段2: 并发对每个章节做层级重建

        Args:
            docx_path: docx 文件路径
            max_workers: 章节并发数

        Returns:
            {
                "section_header_md_path": Path,
                "title_with_id_md_path": Path,
                "level12_headings": [...],
                "chapter_results": [...],
                "all_headings": [...],
                "stage0_time": float,
                "stage1_time": float,
                "stage2_time": float,
                "total_time": float
            }
        """
        total_start = time.time()
        docx_path = Path(docx_path)

        if self.verbose:
            print(f"{'=' * 80}")
            print(f"[Unstructured 标题提取] 开始完整流程")
            print(f"{'=' * 80}")
            print(f"输入文件: {docx_path.name}\n")

        # 阶段0: 使用 unstructured 解析 docx
        stage0_start = time.time()
        if self.verbose:
            print(f"[阶段0] 使用 unstructured 解析 docx...")

        section_header_md_path, title_with_id_md_path, elements, paragraph_fulltext_path = self.parse_docx(docx_path)

        stage0_time = time.time() - stage0_start
        if self.verbose:
            print(f"[阶段0] 完成，耗时: {stage0_time:.2f} 秒\n")

        # 阶段1: 提取一二级标题
        stage1_start = time.time()

        level12_headings = self._qwen_api.extract_level12_headings(section_header_md_path)

        # 保存一二级标题
        level12_json_path = docx_path.parent / f"{docx_path.stem}_unstructured_level12.json"
        level12_json_path.write_text(
            json.dumps(level12_headings, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        if self.verbose:
            print(f"[阶段1] 一二级标题已保存: {level12_json_path.name}")

        # 筛选 chapter
        chapter_headings = [h for h in level12_headings if h.get("type") == "chapter"]

        stage1_time = time.time() - stage1_start
        if self.verbose:
            print(f"[阶段1] 找到 {len(chapter_headings)} 个章节标题")
            print(f"[阶段1] 耗时: {stage1_time:.2f} 秒\n")

        # 阶段2: 并发章节层级重建
        stage2_start = time.time()

        chapter_results = []
        if chapter_headings:
            chapter_results = self._chapter_processor.extract_headings_by_chapters(
                paragraph_fulltext_path,
                chapter_headings,
                level12_headings=level12_headings,
                max_workers=max_workers
            )

        # 聚合结果
        all_headings = self._chapter_processor.merge_stage2_results(level12_headings, chapter_results)

        stage2_time = time.time() - stage2_start
        total_time = time.time() - total_start

        # 保存最终结果
        all_headings_path = docx_path.parent / f"{docx_path.stem}_unstructured_headings.json"
        all_headings_path.write_text(
            json.dumps(all_headings, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        if self.verbose:
            print(f"\n[完成] 所有标题已保存: {all_headings_path.name}")

        # 生成 markdown 格式的层级结构
        md_lines = []
        for h in all_headings:
            level = h.get("level", 1)
            text = h.get("text", "")
            node_id = h.get("id", "")
            prefix = "#" * level
            md_lines.append(f"{prefix} {text} {{id={node_id}}}")

        hierarchy_md_path = docx_path.parent / f"{docx_path.stem}_unstructured_hierarchy.md"
        hierarchy_md_path.write_text("\n".join(md_lines), encoding='utf-8')
        if self.verbose:
            print(f"[完成] 层级结构已保存: {hierarchy_md_path.name}")

        if self.verbose:
            print(f"\n{'=' * 80}")
            print(f"[Unstructured 标题提取] 完成！")
            print(f"  - 一二级标题: {len(level12_headings)} 个")
            print(f"  - 章节数: {len(chapter_results)} 个")
            print(f"  - 总标题数: {len(all_headings)} 个")
            print(f"{'=' * 80}")
            print(f"[耗时统计]")
            print(f"  - 阶段0 (unstructured 解析): {stage0_time:.2f} 秒")
            print(f"  - 阶段1 (一二级标题提取): {stage1_time:.2f} 秒")
            print(f"  - 阶段2 (章节并发重建): {stage2_time:.2f} 秒")
            print(f"  - 总耗时: {total_time:.2f} 秒")
            print(f"{'=' * 80}")

        return {
            "section_header_md_path": section_header_md_path,
            "title_with_id_md_path": title_with_id_md_path,
            "level12_headings": level12_headings,
            "chapter_results": chapter_results,
            "all_headings": all_headings,
            "stage0_time": stage0_time,
            "stage1_time": stage1_time,
            "stage2_time": stage2_time,
            "total_time": total_time
        }


# ============== 命令行入口 ==============

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Unstructured 标题提取器")
    parser.add_argument(
        "docx_path",
        type=str,
        help="docx 文件路径"
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="章节并发数（默认：8）"
    )
    args = parser.parse_args()

    extractor = UnstructuredHeadingExtractor(verbose=True)

    try:
        result = extractor.extract_full_hierarchy(
            args.docx_path,
            max_workers=args.max_workers
        )

        print(f"\n[结果] 共提取 {len(result['all_headings'])} 个标题")

    except Exception as e:
        print(f"\n[错误] {e}")
        import traceback
        traceback.print_exc()