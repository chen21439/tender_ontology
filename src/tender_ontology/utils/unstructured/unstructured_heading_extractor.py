"""
Unstructured 标题提取器

使用 unstructured 库解析 docx 文件，然后通过千问 API 进行标题层级分析。

流程：
1. 使用 unstructured 解析 docx，生成 _unstructured_sectionHeader_only.md 和 _unstructured_title_with_id.md
2. 使用 DocxXmlLoader + HeadingValidator 进行二次标题判定
3. 调用内部千问 API 进行两阶段标题提取
"""

import re
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

from unstructured.partition.docx import partition_docx

from .docx_xml_loader import DocxXmlLoader, ParagraphLocator
from .heading_validator import HeadingValidator, HeadingInfo


class UnstructuredHeadingExtractor:
    """Unstructured 标题提取器"""

    # 内部千问模型
    INTERNAL_MODEL = "qwen3-32b"

    def __init__(self, verbose: bool = True, inspect_elements: int = 3, enable_secondary_validation: bool = True):
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

        # 缓存 DocxXmlLoader 实例
        self._xml_loader: Optional[DocxXmlLoader] = None
        self._heading_validator: Optional[HeadingValidator] = None

    @property
    def INTERNAL_API_URL(self) -> str:
        """从配置读取千问 API URL"""
        from tender_ontology.config.settings import settings
        return settings.qwen_api_url

    # ========== Element 数据结构检查 ==========

    def _inspect_element(self, el, index: int = 0) -> dict:
        """
        检查单个 element 的所有属性

        Args:
            el: unstructured element 对象
            index: 元素索引

        Returns:
            dict: 元素的所有属性
        """
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
        """
        打印前 N 个元素的数据结构

        Args:
            elements: 元素列表
            count: 打印数量
        """
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

    # ========== 批量 XML 提取 ==========

    def batch_extract_xml(
        self,
        docx_path: Union[str, Path],
        elements: List,
        include_raw_xml: bool = False
    ) -> List[Dict[str, Any]]:
        """
        批量提取 unstructured 元素对应的 DOCX XML 信息

        只打开一次 DOCX 文件，根据每个元素的 metadata.paragraph_locator 定位到 <w:p>，
        提取样式信息、文本等。

        Args:
            docx_path: docx 文件路径
            elements: unstructured 解析出的元素列表
            include_raw_xml: 是否包含原始 XML 字符串（默认 False，减少内存占用）

        Returns:
            List[Dict]: 每个元素的 XML 信息
            [
                {
                    "index": 0,                    # 元素在 elements 中的索引
                    "category": "Title",           # unstructured 分类
                    "text": "第一章 ...",          # 元素文本
                    "located": True,               # 是否成功定位到 XML
                    "style_id": "Heading1",        # 样式 ID
                    "style_name": "标题 1",        # 样式名称
                    "outline_level": 0,            # 大纲级别
                    "is_heading_style": True,      # 是否标题样式
                    "num_id": "1",                 # 编号 ID
                    "ilvl": "0",                   # 编号层级
                    "xml_text": "第一章 ...",      # XML 中的文本
                    "raw_xml": "<w:p>...</w:p>",   # 原始 XML（可选）
                    "locator": {...}               # 定位信息
                },
                ...
            ]
        """
        docx_path = Path(docx_path)

        if self.verbose:
            print(f"\n{'=' * 70}")
            print(f"[批量 XML 提取] 开始")
            print(f"{'=' * 70}")
            print(f"  - 文件: {docx_path.name}")
            print(f"  - 元素数: {len(elements)}")
            print(f"  - 包含原始 XML: {include_raw_xml}")

        extract_start = time.time()

        # 加载 DOCX XML（只打开一次）
        if self._xml_loader is None or str(self._xml_loader.docx_path) != str(docx_path):
            self._xml_loader = DocxXmlLoader(docx_path, verbose=False)
            self._xml_loader.load()

        if self.verbose:
            print(f"\n  [DOCX XML 已加载]")
            print(f"    - 段落数: {len(self._xml_loader.by_index)}")
            print(f"    - para_id 索引数: {len(self._xml_loader.by_para_id)}")
            print(f"    - 样式数: {len(self._xml_loader.styles_map)}")

        results = []
        located_count = 0
        skipped_count = 0

        for idx, el in enumerate(elements):
            cat = getattr(el, "category", None) or getattr(el, "type", None)
            text = (el.text or "").strip()

            # 跳过表格
            if cat in ["Table", "TableChunk"]:
                skipped_count += 1
                continue

            # 构建结果
            result = {
                "index": idx,
                "category": cat,
                "text": text[:200] if text else "",  # 截断长文本
                "located": False,
                "style_id": None,
                "style_name": None,
                "outline_level": None,
                "is_heading_style": False,
                "alignment": None,  # 对齐方式: left, center, right, both
                "num_id": None,
                "ilvl": None,
                "xml_text": None,
                "locator": None
            }

            # 获取 locator
            locator_dict = {"flat_index": idx}
            if hasattr(el, "metadata"):
                metadata = el.metadata
                if hasattr(metadata, "paragraph_locator") and metadata.paragraph_locator:
                    locator_dict = metadata.paragraph_locator
                    result["locator"] = locator_dict

            # 定位到 XML <w:p>
            p = self._xml_loader.locate_paragraph(locator_dict)

            if p is not None:
                result["located"] = True
                located_count += 1

                # 获取 XML 中的文本
                xml_text = self._xml_loader.get_paragraph_text(p)
                result["xml_text"] = xml_text[:200] if xml_text else ""

                # 获取样式信息
                style = self._xml_loader.get_paragraph_style(p)
                result["style_id"] = style.style_id
                result["style_name"] = style.style_name
                result["outline_level"] = style.outline_level
                result["alignment"] = style.alignment
                result["num_id"] = style.num_id
                result["ilvl"] = style.ilvl

                # 判断是否是标题：原始标题样式 或 居中对齐
                is_heading = style.is_heading_style
                if style.alignment == "center":
                    is_heading = True
                result["is_heading_style"] = is_heading

                # 原始 XML（可选）
                if include_raw_xml:
                    from lxml import etree
                    result["raw_xml"] = etree.tostring(p, encoding='unicode', pretty_print=True)

            results.append(result)

        extract_time = time.time() - extract_start

        if self.verbose:
            print(f"\n  [提取完成]")
            print(f"    - 处理元素: {len(results)}")
            print(f"    - 成功定位: {located_count}")
            print(f"    - 跳过表格: {skipped_count}")
            print(f"    - 耗时: {extract_time:.2f} 秒")
            print(f"{'=' * 70}\n")

        return results

    @staticmethod
    def batch_extract_xml_from_docx(
        docx_path: Union[str, Path],
        include_raw_xml: bool = False,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        静态方法：从 DOCX 批量提取所有元素的 XML 信息

        一站式方法：先用 unstructured 解析，再批量提取 XML。

        Args:
            docx_path: docx 文件路径
            include_raw_xml: 是否包含原始 XML 字符串
            verbose: 是否打印详细信息

        Returns:
            {
                "elements": [...],       # unstructured 元素（原始）
                "xml_info": [...],       # 批量提取的 XML 信息
                "stats": {
                    "total_elements": int,
                    "located_count": int,
                    "heading_count": int,
                    "parse_time": float,
                    "extract_time": float
                }
            }

        使用示例:
            from tender_ontology.utils.unstructured import UnstructuredHeadingExtractor

            result = UnstructuredHeadingExtractor.batch_extract_xml_from_docx(
                "input.docx",
                include_raw_xml=True
            )

            for item in result["xml_info"]:
                if item["located"] and item["is_heading_style"]:
                    print(f"标题: {item['text']}, 样式: {item['style_name']}")
        """
        docx_path = Path(docx_path)

        if verbose:
            print(f"\n{'=' * 70}")
            print(f"[批量 XML 提取] 一站式处理")
            print(f"{'=' * 70}")
            print(f"  - 输入文件: {docx_path.name}")

        total_start = time.time()

        # Step 1: 使用 unstructured 解析
        parse_start = time.time()
        elements = partition_docx(str(docx_path))
        parse_time = time.time() - parse_start

        if verbose:
            print(f"\n  [Step 1] Unstructured 解析完成")
            print(f"    - 元素数: {len(elements)}")
            print(f"    - 耗时: {parse_time:.2f} 秒")

        # Step 2: 批量提取 XML
        extract_start = time.time()

        extractor = UnstructuredHeadingExtractor(verbose=False)
        xml_info = extractor.batch_extract_xml(
            docx_path,
            elements,
            include_raw_xml=include_raw_xml
        )
        extract_time = time.time() - extract_start

        # 统计
        located_count = sum(1 for item in xml_info if item["located"])
        heading_count = sum(1 for item in xml_info if item["is_heading_style"])

        if verbose:
            print(f"\n  [Step 2] XML 提取完成")
            print(f"    - 定位成功: {located_count}/{len(xml_info)}")
            print(f"    - 标题样式: {heading_count}")
            print(f"    - 耗时: {extract_time:.2f} 秒")

        total_time = time.time() - total_start

        if verbose:
            print(f"\n  [总耗时] {total_time:.2f} 秒")
            print(f"{'=' * 70}\n")

        return {
            "elements": elements,
            "xml_info": xml_info,
            "stats": {
                "total_elements": len(elements),
                "located_count": located_count,
                "heading_count": heading_count,
                "parse_time": parse_time,
                "extract_time": extract_time,
                "total_time": total_time
            }
        }

    # ========== 二次标题判定 ==========

    def _secondary_heading_validation(
        self,
        docx_path: Path,
        elements: List
    ) -> Dict[int, HeadingInfo]:
        """
        使用 DocxXmlLoader + HeadingValidator 对元素进行二次标题判定

        Args:
            docx_path: docx 文件路径
            elements: unstructured 解析出的元素列表

        Returns:
            Dict[int, HeadingInfo]: idx -> HeadingInfo 的映射
        """
        if self.verbose:
            print(f"\n{'=' * 70}")
            print(f"[二次判定] 开始")
            print(f"{'=' * 70}")
            print(f"\n[Step 1] 加载 DOCX XML...")

        validation_start = time.time()

        # 加载 XML
        self._xml_loader = DocxXmlLoader(docx_path, verbose=False)
        self._xml_loader.load()

        # 创建判定器
        self._heading_validator = HeadingValidator(self._xml_loader, verbose=False)

        if self.verbose:
            print(f"  - 段落数: {len(self._xml_loader.by_index)}")
            print(f"  - para_id 索引数: {len(self._xml_loader.by_para_id)}")
            print(f"  - 样式数: {len(self._xml_loader.styles_map)}")
            print(f"  - 标题样式 ID: {self._xml_loader.heading_style_ids}")

        # ========== Step 2: 挑选 3 个元素进行演示 ==========
        if self.verbose:
            print(f"\n[Step 2] 挑选 3 个元素演示定位过程")
            print(f"-" * 50)

            demo_count = 0
            for idx, el in enumerate(elements):
                if demo_count >= 3:
                    break

                cat = getattr(el, "category", None) or getattr(el, "type", None)
                text = (el.text or "").strip()

                if not text or cat in ["Table", "TableChunk"]:
                    continue

                print(f"\n--- 元素 [{idx}] ---")
                print(f"  [Unstructured 信息]")
                print(f"    category: {cat}")
                print(f"    text: {text[:50]}{'...' if len(text) > 50 else ''}")

                # 构建 locator
                locator_dict = {"flat_index": idx}
                if hasattr(el, "metadata"):
                    metadata = el.metadata
                    if hasattr(metadata, "paragraph_locator") and metadata.paragraph_locator:
                        locator_dict = metadata.paragraph_locator
                        print(f"    paragraph_locator: {locator_dict}")
                    else:
                        print(f"    paragraph_locator: (无，使用 flat_index={idx})")

                # 定位到 XML <w:p>
                print(f"\n  [XML 定位]")
                p = self._xml_loader.locate_paragraph(locator_dict)

                if p is not None:
                    # 获取 XML 中的文本
                    xml_text = self._xml_loader.get_paragraph_text(p)
                    print(f"    定位成功!")
                    print(f"    XML 文本: {xml_text[:50]}{'...' if len(xml_text) > 50 else ''}")

                    # 打印原始 XML（完整）
                    from lxml import etree
                    xml_str = etree.tostring(p, encoding='unicode', pretty_print=True)
                    print(f"\n  [原始 XML]")
                    print(xml_str)

                    # 获取样式信息
                    style = self._xml_loader.get_paragraph_style(p)
                    print(f"\n  [样式信息]")
                    print(f"    style_id: {style.style_id}")
                    print(f"    style_name: {style.style_name}")
                    print(f"    outline_level: {style.outline_level}")
                    print(f"    is_heading_style: {style.is_heading_style}")
                    print(f"    num_id: {style.num_id}, ilvl: {style.ilvl}")
                else:
                    print(f"    定位失败!")

                demo_count += 1

            print(f"\n{'-' * 50}")

        # ========== Step 3: 暂时跳过判定逻辑，只验证 XML 读取 ==========
        if self.verbose:
            print(f"\n[Step 3] 跳过二次判定（验证模式）")

        validation_time = time.time() - validation_start

        if self.verbose:
            print(f"  - 耗时: {validation_time:.2f} 秒")
            print(f"\n{'=' * 70}")

        # 暂时返回空，不做判定
        return {}

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

        # 使用 unstructured 解析
        parse_start = time.time()
        elements = partition_docx(str(docx_path))
        parse_time = time.time() - parse_start

        if self.verbose:
            print(f"[Unstructured] 共解析出 {len(elements)} 个元素，partition_docx 耗时: {parse_time:.2f} 秒")

        # 打印元素数据结构（如果设置了 inspect_elements）
        if self.inspect_elements > 0:
            self._print_elements_inspection(elements, self.inspect_elements)

        # ========== 批量提取 XML 信息（获取 alignment 等属性）==========
        xml_info_map = {}  # idx -> xml_info
        if self.enable_secondary_validation:
            xml_info_list = self.batch_extract_xml(docx_path, elements, include_raw_xml=False)
            for info in xml_info_list:
                xml_info_map[info["index"]] = info

        # ========== 二次标题判定 ==========
        secondary_headings = {}  # idx -> HeadingInfo
        if self.enable_secondary_validation:
            secondary_headings = self._secondary_heading_validation(docx_path, elements)

        # 提取标题类元素（结合 unstructured 分类 + 二次判定 + 居中对齐）
        header_types = []
        for idx, el in enumerate(elements):
            cat = getattr(el, "category", None) or getattr(el, "type", None)
            text = (el.text or "").strip()
            if not text:
                continue

            is_heading = False
            heading_source = None  # 标题来源
            alignment = None  # 对齐方式

            # 获取 XML 信息
            xml_info = xml_info_map.get(idx, {})
            if xml_info:
                alignment = xml_info.get("alignment")

            # 1. unstructured 原始分类
            if cat in ["Title", "Header", "SectionHeader"]:
                is_heading = True
                heading_source = f"unstructured:{cat}"

            # 2. 居中对齐判定为标题
            if alignment == "center":
                if not is_heading:
                    is_heading = True
                    heading_source = "align:center"
                else:
                    heading_source += " + align:center"

            # 3. 二次判定结果（可能纠正或补充）
            if idx in secondary_headings:
                info = secondary_headings[idx]
                if info.is_heading:
                    is_heading = True
                    if heading_source:
                        heading_source += f" + secondary(L{info.heading_level}, conf={info.confidence:.2f})"
                    else:
                        heading_source = f"secondary(L{info.heading_level}, conf={info.confidence:.2f})"

            if is_heading:
                header_types.append({
                    "text": text,
                    "category": cat,
                    "index": idx,
                    "id": f"P_{idx:05d}",
                    "source": heading_source,
                    "alignment": alignment,
                    "heading_info": secondary_headings.get(idx)
                })

        if self.verbose:
            unstructured_count = sum(1 for h in header_types if "unstructured:" in (h.get("source") or ""))
            secondary_count = sum(1 for h in header_types if "secondary" in (h.get("source") or "") and "unstructured:" not in (h.get("source") or ""))
            print(f"[Unstructured] 找到 {len(header_types)} 个标题类元素 (原始: {unstructured_count}, 二次判定补充: {secondary_count})")

        # 输出路径
        section_header_md_path = docx_path.parent / f"{docx_path.stem}_unstructured_sectionHeader_only.md"
        title_with_id_md_path = docx_path.parent / f"{docx_path.stem}_unstructured_title_with_id.md"

        # 写入 sectionHeader_only.md (只有标题)
        with open(section_header_md_path, "w", encoding="utf-8") as f:
            f.write(f"# {docx_path.stem} - 标题结构\n\n")
            f.write(f"> 提取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"> 共 {len(header_types)} 条\n\n")

            for item in header_types:
                if include_metadata:
                    # 构建属性字符串：{id=xxx} 或 {id=xxx, align=center}
                    attrs = f"id={item['id']}"
                    if item.get('alignment') == 'center':
                        attrs += ", align=center"
                    f.write(f"- [{item['category']}] {item['text']} {{{attrs}}}\n")
                else:
                    f.write(f"- {item['text']}\n")

        # 写入 title_with_id.md (标题 + 下方内容)
        with open(title_with_id_md_path, "w", encoding="utf-8") as f:
            f.write(f"# {docx_path.stem} - 标题与内容\n\n")
            f.write(f"> 提取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"> 共 {len(header_types)} 条标题\n\n")

            for item in header_types:
                idx = item['index']
                # 构建属性字符串：{id=xxx} 或 {id=xxx, align=center}
                attrs = f"id={item['id']}"
                if item.get('alignment') == 'center':
                    attrs += ", align=center"
                # 写入标题
                f.write(f"## [{item['category']}] {item['text']} {{{attrs}}}\n\n")

                # 获取下方内容（下一个元素）
                if idx + 1 < len(elements):
                    next_el = elements[idx + 1]
                    next_text = (next_el.text or "").strip()
                    next_cat = getattr(next_el, "category", None) or getattr(next_el, "type", None)

                    # 如果下一个不是标题类型，则作为内容输出
                    if next_cat not in ["Title", "Header", "SectionHeader"] and next_text:
                        f.write(f"{next_text}\n")

                f.write("\n")

        # 写入 fulltext.json (所有元素，含表格)
        fulltext_path = docx_path.parent / f"{docx_path.stem}_unstructured_fulltext.json"
        fulltext_items = []
        table_count = 0
        paragraph_count = 0  # 表格外段落计数

        for idx, el in enumerate(elements):
            cat = getattr(el, "category", None) or getattr(el, "type", None)
            text = (el.text or "").strip()

            # 表格使用 tNNN-rNNN-cNNN-pNNN 格式（3位数）
            if cat in ["Table", "TableChunk"]:
                # 尝试获取 text_as_html
                html_text = None
                if hasattr(el, "metadata") and hasattr(el.metadata, "text_as_html"):
                    html_text = el.metadata.text_as_html

                # 表格 ID: tNNN-r000-c000-p000（表格索引，行列段落暂为0）
                table_id = f"t{table_count:03d}-r000-c000-p000"

                if html_text:
                    fulltext_items.append({
                        "id": table_id,
                        "text": html_text,  # 使用 HTML 格式
                        "category": cat,
                        "index": idx,
                        "is_table": True
                    })
                    table_count += 1
                elif text:
                    # 没有 HTML，使用纯文本
                    fulltext_items.append({
                        "id": table_id,
                        "text": text,
                        "category": cat,
                        "index": idx,
                        "is_table": True
                    })
                    table_count += 1
            elif text:
                # 表格外段落使用 P_NNNNN 格式（5位数）
                fulltext_items.append({
                    "id": f"P_{paragraph_count:05d}",
                    "text": text,
                    "category": cat,
                    "index": idx
                })
                paragraph_count += 1

        fulltext_path.write_text(
            json.dumps(fulltext_items, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

        if self.verbose:
            print(f"[Unstructured] 已生成: {section_header_md_path.name}")
            print(f"[Unstructured] 已生成: {title_with_id_md_path.name}")
            print(f"[Unstructured] 已生成: {fulltext_path.name} ({len(fulltext_items)} 个元素, 含 {table_count} 个表格)")

        return section_header_md_path, title_with_id_md_path, elements, fulltext_path

    # ========== 阶段1：调用千问提取一二级标题 ==========

    def _build_level12_prompt(self) -> str:
        """构建一二级标题提取的提示词"""
        prompt = """/no_think
你是一个专业的文档结构分析引擎，专门负责识别招标文件中的一级标题和二级标题。

## 任务说明
从文档中找到所有的**一级标题**和**二级标题**，忽略三级及以下的标题。

## 层级判断规则

### 第一步：判断文档是否存在"册/部分/节"结构
先扫描全文，判断是否存在"第X册"、"第X部分"或"第X节"这样的顶层结构标题。

### 第二步：根据文档结构确定层级

**情况一：文档存在"册/部分/节"结构**
- 一级标题 `#`：**"第X册"、"第X部分"、"第X节"** 格式的标题
- 二级标题 `##`：**"第X章"** 格式的标题（挂载在册/部分/节下）

**情况二：文档不存在"册/部分/节"结构**
- 一级标题 `#`：**"第X章"** 格式的标题
- 二级标题 `##`：章下的主要分节（如"一、""二、"等）

### 补充说明
- **独立功能标题**（如"目录"、"封面"、"特别警示条款"、"资格性审查表"、"符合性审查表"、"评标方法"、"用户需求书"等）→ 作为一级标题 `#`
- 层级必须连续，不能跳级

## 输出要求
1. 仅在 ```markdown``` 代码块中返回找到的一级和二级标题
2. **必须保留每个标题后的 {id=...} 标识符**，原样附在标题行末尾
3. 只输出一级 `#` 和二级 `##` 标题，忽略更深层级

## 输出示例

**示例一（存在册/部分结构）：**
```markdown
# 第一册 专用条款 {id=P_00061}
## 第一章 招标公告 {id=P_00100}
## 第二章 投标须知 {id=P_00150}
# 第二册 通用条款 {id=P_00200}
## 第一章 总则 {id=P_00210}
```

**示例二（无册/部分结构，章为顶层）：**
```markdown
# 第一章 招标公告 {id=P_00010}
## 一、项目概况 {id=P_00015}
## 二、投标人资格要求 {id=P_00020}
# 第二章 投标须知 {id=P_00050}
## 一、投标文件的编制 {id=P_00055}
```

现在，请找出文档中所有的一级标题和二级标题。"""

        return prompt

    def _call_internal_qwen(
        self,
        content: str,
        system_prompt: str,
        save_response_path: Optional[Path] = None
    ) -> str:
        """
        调用内部千问 API

        Args:
            content: 用户内容
            system_prompt: 系统提示词
            save_response_path: 保存响应的路径（可选）

        Returns:
            API 响应文本
        """
        import requests

        payload = {
            "model": self.INTERNAL_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ],
            "temperature": 0.0,
            "top_p": 1.0,
            "repetition_penalty": 1.05,
            "max_tokens": 8192
        }

        if self.verbose:
            print(f"[Qwen] 调用内部 API: {self.INTERNAL_API_URL}")

        try:
            response = requests.post(
                self.INTERNAL_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=120
            )
            response.raise_for_status()
            result = response.json()

            # 保存完整响应
            if save_response_path:
                save_response_path = Path(save_response_path)
                save_response_path.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2),
                    encoding='utf-8'
                )
                if self.verbose:
                    print(f"[Qwen] 响应已保存: {save_response_path.name}")

            content_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            # 为响应添加 type 标记
            if content_text:
                content_text = self._enrich_markdown_with_type(content_text)

            if self.verbose:
                print(f"[Qwen] API 调用成功")

            return content_text

        except Exception as e:
            if self.verbose:
                print(f"[Qwen] API 调用失败: {e}")
            return ""

    def _enrich_markdown_with_type(self, markdown_content: str) -> str:
        """
        为 markdown 标题添加 type 标记

        规则：
        - 册/部分/节 → type=volume
        - 章 → type=chapter
        """
        volume_pattern = re.compile(r'第[一二三四五六七八九十\d]+[册部分节]')
        chapter_pattern = re.compile(r'第[一二三四五六七八九十\d]+章')

        enriched_lines = []
        for line in markdown_content.split('\n'):
            if line.strip().startswith('#'):
                if volume_pattern.search(line):
                    if '{id=' in line:
                        line = re.sub(r'\{id=', '{type=volume, id=', line)
                    else:
                        line = line.rstrip() + ' {type=volume}'
                elif chapter_pattern.search(line):
                    if '{id=' in line:
                        line = re.sub(r'\{id=', '{type=chapter, id=', line)
                    else:
                        line = line.rstrip() + ' {type=chapter}'
            enriched_lines.append(line)

        return '\n'.join(enriched_lines)

    def _parse_response(self, response: str) -> List[Dict[str, Any]]:
        """
        解析千问返回的 Markdown 响应

        Args:
            response: 千问返回的原始响应

        Returns:
            标题列表
        """
        # 提取 markdown 代码块
        markdown_match = re.search(r'```markdown\s*(.*?)\s*```', response, re.DOTALL)
        if markdown_match:
            markdown_content = markdown_match.group(1).strip()
        else:
            markdown_content = response.strip()

        # 正则匹配
        type_id_pattern = re.compile(r'\{type=(\w+),\s*id=([^}]+)\}')
        id_only_pattern = re.compile(r'\{id=([^}]+)\}')
        attr_pattern = re.compile(r'\{[^}]+\}')

        headings = []
        for line in markdown_content.split('\n'):
            line = line.strip()
            if line.startswith('#'):
                level = len(line) - len(line.lstrip('#'))
                text_with_attrs = line.lstrip('#').strip()

                type_id_match = type_id_pattern.search(text_with_attrs)
                if type_id_match:
                    node_type = type_id_match.group(1)
                    node_id = type_id_match.group(2)
                else:
                    id_match = id_only_pattern.search(text_with_attrs)
                    node_id = id_match.group(1) if id_match else None
                    node_type = None

                text = attr_pattern.sub('', text_with_attrs).strip()

                if text:
                    heading = {
                        "id": node_id,
                        "text": text,
                        "level": level,
                    }
                    if node_type:
                        heading["type"] = node_type
                    headings.append(heading)

        return headings

    def extract_level12_headings(
        self,
        sectionheader_md_path: Union[str, Path],
        save_response: bool = True
    ) -> List[Dict[str, Any]]:
        """
        阶段1：提取一二级标题

        Args:
            sectionheader_md_path: _sectionHeader_only.md 文件路径
            save_response: 是否保存响应

        Returns:
            标题列表
        """
        sectionheader_md_path = Path(sectionheader_md_path)

        if self.verbose:
            print(f"\n[阶段1] 提取一二级标题...")
            print(f"[阶段1] 输入文件: {sectionheader_md_path.name}")

        # 读取文件
        content = sectionheader_md_path.read_text(encoding='utf-8')

        # 构建保存路径
        save_path = None
        if save_response:
            base_name = sectionheader_md_path.stem.replace('_unstructured_sectionHeader_only', '')
            save_path = sectionheader_md_path.parent / f"{base_name}_unstructured_level12_response.json"

        # 调用 API
        prompt = self._build_level12_prompt()
        user_content = f"请分析以下文档内容，找出一级和二级标题：\n\n{content}"

        response = self._call_internal_qwen(user_content, prompt, save_path)

        if not response:
            return []

        # 保存 markdown 响应
        if save_response:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            md_path = sectionheader_md_path.parent / f"{base_name}_unstructured_level12_response_{timestamp}.md"
            md_path.write_text(response, encoding='utf-8')
            if self.verbose:
                print(f"[阶段1] Markdown 响应已保存: {md_path.name}")

        # 解析响应
        headings = self._parse_response(response)

        if self.verbose:
            print(f"[阶段1] 完成，共提取 {len(headings)} 个一二级标题")

        return headings

    # ========== 阶段2：并发提取章节子标题 ==========

    def _build_chapter_prompt(self) -> str:
        """构建章节内标题提取的提示词"""
        prompt = """/no_think
你是一个专业的文档结构分析引擎，负责识别章节内的标题层级结构。

## 任务说明
分析给定的**单个章节**内容，识别其中所有的标题并确定层级关系。

## 关键约束（必须遵守）
1. **整个输入内容属于同一个章节**，章节标题（第X章）是唯一的顶层标题
2. **只能有一个 `#` 一级标题**，就是章节标题本身
3. **章节内的所有其他标题都是该章节的后代**，必须从 `##` 开始

## 层级判断规则

根据数字序号识别候选标题：
- 中文数字：一、二、三、（一）（二）（三）
- 阿拉伯数字：1. 2. 3.、(1) (2) (3)、1) 2) 3)
- 其他格式：第X节、① ② ③ 等

## 输出要求
1. 仅在 ```markdown``` 代码块中返回识别到的标题
2. **必须保留每个标题后的 {id=...} 标识符**
3. 层级必须连续，不能跳级
4. **只输出一个 `#` 一级标题**

## 输出示例
```markdown
# 第一章 招标公告 {id=P_00100}
## 一、项目概况 {id=P_00105}
### 1. 项目名称 {id=P_00106}
### 2. 项目编号 {id=P_00107}
## 二、投标人资格要求 {id=P_00120}
```

现在，请分析以下章节内容，识别所有标题及其层级。"""

        return prompt

    def split_by_chapters(
        self,
        title_md_content: str,
        chapter_headings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        根据章节标题锚点切分 title_with_id.md 内容

        Args:
            title_md_content: title_with_id.md 的完整内容
            chapter_headings: 章节标题列表（type=chapter 的标题）

        Returns:
            章节列表
        """
        lines = title_md_content.split('\n')

        # 提取所有章节的 id 和位置
        chapter_positions = []
        id_pattern = re.compile(r'\{id=([^}]+)\}')

        for i, line in enumerate(lines):
            id_match = id_pattern.search(line)
            if id_match:
                line_id = id_match.group(1)
                for ch in chapter_headings:
                    if ch.get("id") == line_id:
                        chapter_positions.append({
                            "id": line_id,
                            "text": ch.get("text", ""),
                            "line_index": i
                        })
                        break

        if self.verbose:
            print(f"[章节切分] 找到 {len(chapter_positions)} 个章节锚点")

        # 切分章节内容
        chapters = []
        for i, ch_pos in enumerate(chapter_positions):
            start_line = ch_pos["line_index"]
            end_line = chapter_positions[i + 1]["line_index"] if i + 1 < len(chapter_positions) else len(lines)

            chapter_content = '\n'.join(lines[start_line:end_line])

            chapters.append({
                "id": ch_pos["id"],
                "text": ch_pos["text"],
                "content": chapter_content,
                "start_line": start_line,
                "end_line": end_line,
                "line_count": end_line - start_line
            })

            if self.verbose:
                print(f"  - {ch_pos['text'][:30]}... ({end_line - start_line} 行)")

        return chapters

    def extract_headings_by_chapters(
        self,
        title_md_path: Union[str, Path],
        chapter_headings: List[Dict[str, Any]],
        max_workers: int = 8
    ) -> List[Dict[str, Any]]:
        """
        阶段2：并发提取各章节的子标题

        Args:
            title_md_path: title_with_id.md 文件路径
            chapter_headings: 章节标题列表
            max_workers: 最大并发数

        Returns:
            各章节的标题结果列表
        """
        from tender_ontology.utils.request.ai_client import AIClient
        from tender_ontology.utils.request.batch_processor import BatchProcessor

        title_md_path = Path(title_md_path)

        if self.verbose:
            print(f"\n[阶段2] 并发提取章节子标题...")
            print(f"[阶段2] 输入文件: {title_md_path.name}")

        # 读取文件
        content = title_md_path.read_text(encoding='utf-8')

        # 切分章节
        chapters = self.split_by_chapters(content, chapter_headings)

        if not chapters:
            if self.verbose:
                print(f"[阶段2] 未找到任何章节")
            return []

        if self.verbose:
            print(f"[阶段2] 开始并发处理 {len(chapters)} 个章节 (max_workers={max_workers})")

        # 创建 AI 客户端
        ai_client = AIClient(
            model_name=self.INTERNAL_MODEL,
            base_url=self.INTERNAL_API_URL.replace("/v1/chat/completions", "/v1"),
            api_key="not-needed",
            temperature=0.0,
            top_p=0.7,
            repetition_penalty=1.05,
            max_tokens=8192,
            timeout=120.0
        )

        # 创建 BatchProcessor
        batch_processor = BatchProcessor(
            ai_client=ai_client,
            verbose=self.verbose,
            max_workers=max_workers
        )

        # 构建批次
        system_prompt = self._build_chapter_prompt()
        batches = []
        for chapter in chapters:
            user_prompt = f"请分析以下章节内容，识别所有标题及其层级：\n\n{chapter['content']}"
            context = {
                "chapter_id": chapter.get("id"),
                "chapter_text": chapter.get("text", "")
            }
            batches.append((system_prompt, user_prompt, context))

        # 定义解析函数（保留原始响应）
        def parse_response_with_raw(response_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
            headings = self._parse_response(response_text)
            return {
                "chapter_id": context.get("chapter_id"),
                "chapter_text": context.get("chapter_text"),
                "headings": headings,
                "raw_response": response_text
            }

        # 并发处理
        try:
            results = batch_processor.process_batches(
                batches=batches,
                parse_response_func=parse_response_with_raw,
                merge_results_func=lambda x: x,
                parallel=True
            )
        except Exception as e:
            if self.verbose:
                print(f"[阶段2] 处理失败: {e}")
            return []

        # 保存二阶段结果到 _unstructured_model.md
        self._save_stage2_model_md(title_md_path, results)

        if self.verbose:
            total_headings = sum(len(r.get("headings", [])) for r in results)
            print(f"[阶段2] 完成，共处理 {len(results)} 个章节，提取 {total_headings} 个标题")

        return results

    def _save_stage2_model_md(
        self,
        title_md_path: Path,
        chapter_results: List[Dict[str, Any]]
    ) -> Path:
        """
        保存二阶段模型响应结果为 markdown 文件

        Args:
            title_md_path: title_with_id.md 文件路径
            chapter_results: 各章节的结果（包含 raw_response）

        Returns:
            保存的文件路径
        """
        base_name = title_md_path.stem.replace('_unstructured_title_with_id', '')
        model_md_path = title_md_path.parent / f"{base_name}_unstructured_model.md"

        lines = []
        lines.append(f"# {base_name} - 模型层级分析结果\n")
        lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"> 章节数: {len(chapter_results)}\n")
        lines.append("-" * 80 + "\n")

        for i, result in enumerate(chapter_results):
            chapter_text = result.get("chapter_text", "未知章节")
            chapter_id = result.get("chapter_id", "")
            raw_response = result.get("raw_response", "")

            lines.append(f"\n## 章节 {i + 1}: {chapter_text} {{id={chapter_id}}}\n")

            # 提取 markdown 代码块内容
            markdown_match = re.search(r'```markdown\s*(.*?)\s*```', raw_response, re.DOTALL)
            if markdown_match:
                md_content = markdown_match.group(1).strip()
                lines.append(md_content)
            else:
                lines.append(raw_response.strip() if raw_response else "(无响应)")

            lines.append("\n")

        # 写入文件
        model_md_path.write_text("\n".join(lines), encoding='utf-8')

        if self.verbose:
            print(f"[阶段2] 模型响应已保存: {model_md_path.name}")

        return model_md_path

    def merge_stage2_results(
        self,
        level12_headings: List[Dict[str, Any]],
        chapter_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        聚合二阶段结果

        Args:
            level12_headings: 一阶段返回的一二级标题
            chapter_results: 二阶段返回的各章节结果

        Returns:
            聚合后的完整标题列表
        """
        # 检查是否存在 volume
        volume_pattern = re.compile(r'第[一二三四五六七八九十\d]+[册部分节]')
        has_volume = any(
            volume_pattern.search(h.get("text", ""))
            for h in level12_headings
        )

        if self.verbose:
            print(f"\n[聚合] 是否存在 volume 结构: {has_volume}")

        # 构建 chapter_id -> level 的映射
        chapter_level_map = {}
        for h in level12_headings:
            if h.get("type") == "chapter":
                chapter_level_map[h.get("id")] = h.get("level", 1)

        # 聚合结果
        all_headings = []

        for h in level12_headings:
            node_id = h.get("id")

            if h.get("type") == "chapter":
                all_headings.append(h)

                # 找到对应的二阶段结果
                chapter_result = next(
                    (r for r in chapter_results if r.get("chapter_id") == node_id),
                    None
                )

                if chapter_result:
                    chapter_original_level = chapter_level_map.get(node_id, 1)
                    level_offset = chapter_original_level - 1

                    # 添加子标题
                    for sub_h in chapter_result.get("headings", []):
                        if sub_h.get("id") != node_id:
                            adjusted_heading = sub_h.copy()
                            adjusted_heading["level"] = sub_h.get("level", 1) + level_offset
                            all_headings.append(adjusted_heading)

                    if self.verbose:
                        sub_count = len(chapter_result.get("headings", [])) - 1
                        print(f"[聚合] {h.get('text', '')[:20]}... -> {sub_count} 个子标题 (offset={level_offset})")
            else:
                all_headings.append(h)

        if self.verbose:
            print(f"[聚合] 总计 {len(all_headings)} 个标题")

        return all_headings

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

        level12_headings = self.extract_level12_headings(section_header_md_path)

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
            chapter_results = self.extract_headings_by_chapters(
                title_with_id_md_path,
                chapter_headings,
                max_workers=max_workers
            )

        # 聚合结果
        all_headings = self.merge_stage2_results(level12_headings, chapter_results)

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