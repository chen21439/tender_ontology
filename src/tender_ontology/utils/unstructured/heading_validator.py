"""
标题二次判定器

对 unstructured 解析出的元素进行二次判定，确定是否为标题及标题层级。

判定依据：
1. DOCX 样式信息（pStyle、outlineLvl、numPr）
2. 文本规则（第X章、第X条、一、二、等）
3. 上下文信息（前后是否有长正文块）

使用方式：
1. 先用 DocxXmlLoader 加载 docx XML
2. 对每个 element，通过 locator 定位到 <w:p>
3. 根据样式和文本规则判定是否为标题
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from lxml import etree

from .docx_xml_loader import DocxXmlLoader, ParagraphLocator, ParagraphStyle


@dataclass
class HeadingInfo:
    """标题判定结果"""
    is_heading: bool = False                    # 是否是标题
    heading_level: Optional[int] = None         # 标题层级 (0=一级, 1=二级...)
    heading_number: Optional[str] = None        # 编号 (如 "第一章", "一、")
    confidence: float = 0.0                     # 置信度 (0-1)
    evidence: List[str] = field(default_factory=list)  # 判定依据


class HeadingValidator:
    """标题二次判定器"""

    # 中文标题模式
    HEADING_PATTERNS = [
        # 册/部分/节 (一级)
        (re.compile(r'^第[一二三四五六七八九十百零\d]+[册部分节]'), 0, "volume"),
        # 章 (一级或二级)
        (re.compile(r'^第[一二三四五六七八九十百零\d]+章'), 1, "chapter"),
        # 条 (通常是二级或三级)
        (re.compile(r'^第[一二三四五六七八九十百零\d]+条'), 2, "article"),
        # 节 (章下的节)
        (re.compile(r'^第[一二三四五六七八九十百零\d]+节'), 2, "section"),
        # 中文编号 (一、二、三、)
        (re.compile(r'^[一二三四五六七八九十]+、'), 2, "chinese_num"),
        # 带括号的中文编号 (（一）（二）)
        (re.compile(r'^[（(][一二三四五六七八九十]+[）)]'), 3, "chinese_num_paren"),
        # 阿拉伯数字编号 (1. 2. 3.)
        (re.compile(r'^\d+[.、](?!\d)'), 3, "arabic_num"),
        # 带括号的阿拉伯数字 ((1) (2))
        (re.compile(r'^[（(]\d+[）)]'), 4, "arabic_num_paren"),
        # 多级编号 (1.1 1.1.1)
        (re.compile(r'^\d+\.\d+(?:\.\d+)*'), 3, "multi_level"),
        # 圈数字 ① ② ③
        (re.compile(r'^[①②③④⑤⑥⑦⑧⑨⑩]'), 4, "circle_num"),
    ]

    # 特殊标题关键词
    SPECIAL_HEADING_KEYWORDS = [
        "目录", "封面", "前言", "引言", "概述", "总则", "附则", "附录",
        "特别警示", "警示条款", "资格审查", "符合性审查", "评标方法",
        "用户需求", "技术规格", "商务条款", "投标须知", "招标公告"
    ]

    def __init__(self, loader: DocxXmlLoader, verbose: bool = False):
        """
        初始化判定器

        Args:
            loader: DocxXmlLoader 实例（已加载）
            verbose: 是否打印详细信息
        """
        self.loader = loader
        self.verbose = verbose

    def validate(
        self,
        element: Dict[str, Any],
        context_before: Optional[str] = None,
        context_after: Optional[str] = None
    ) -> HeadingInfo:
        """
        对单个 element 进行标题判定

        Args:
            element: unstructured 解析出的元素（包含 paragraph_locator）
            context_before: 前一个元素的文本（可选，用于上下文判断）
            context_after: 后一个元素的文本（可选，用于上下文判断）

        Returns:
            HeadingInfo
        """
        result = HeadingInfo()
        text = element.get("text", "").strip()

        if not text:
            return result

        # 获取 locator
        locator_dict = element.get("metadata", {}).get("paragraph_locator")
        if not locator_dict:
            # 没有 locator，只能用文本规则判定
            return self._validate_by_text_only(text)

        # 定位到 <w:p>
        p = self.loader.locate_paragraph(locator_dict)
        if p is None:
            # 定位失败，回退到纯文本判定
            return self._validate_by_text_only(text)

        # 获取样式信息
        style = self.loader.get_paragraph_style(p)

        # 1. 基于样式判定
        self._validate_by_style(result, style)

        # 2. 基于文本规则判定
        self._validate_by_text(result, text)

        # 3. 基于上下文判定（可选）
        if context_before or context_after:
            self._validate_by_context(result, text, context_before, context_after)

        # 综合判定
        self._finalize(result)

        if self.verbose and result.is_heading:
            print(f"[HeadingValidator] 判定为标题: {text[:30]}... (level={result.heading_level}, conf={result.confidence:.2f})")
            for e in result.evidence:
                print(f"    - {e}")

        return result

    def _validate_by_style(self, result: HeadingInfo, style: ParagraphStyle):
        """基于样式判定"""
        # outlineLvl 直接决定是标题
        if style.outline_level is not None:
            result.is_heading = True
            result.heading_level = style.outline_level
            result.confidence = max(result.confidence, 0.9)
            result.evidence.append(f"outlineLvl={style.outline_level}")

        # pStyle 是标题样式
        if style.is_heading_style:
            result.is_heading = True
            result.confidence = max(result.confidence, 0.85)
            result.evidence.append(f"pStyle={style.style_id} ({style.style_name})")

            # 从样式名提取层级
            if style.style_name:
                level = self._extract_level_from_style_name(style.style_name)
                if level is not None and result.heading_level is None:
                    result.heading_level = level

        # 有编号但不一定是标题（需要结合文本规则）
        if style.num_id:
            result.evidence.append(f"numPr: numId={style.num_id}, ilvl={style.ilvl}")

    def _validate_by_text(self, result: HeadingInfo, text: str):
        """基于文本规则判定"""
        # 检查标题模式
        for pattern, level, pattern_type in self.HEADING_PATTERNS:
            match = pattern.match(text)
            if match:
                result.is_heading = True
                result.heading_number = match.group(0)
                result.confidence = max(result.confidence, 0.7)
                result.evidence.append(f"text_pattern: {pattern_type} ({match.group(0)})")

                # 如果样式没给出层级，用文本规则的层级
                if result.heading_level is None:
                    result.heading_level = level
                break

        # 检查特殊关键词
        for keyword in self.SPECIAL_HEADING_KEYWORDS:
            if keyword in text and len(text) < 50:
                result.is_heading = True
                result.confidence = max(result.confidence, 0.6)
                result.evidence.append(f"special_keyword: {keyword}")
                if result.heading_level is None:
                    result.heading_level = 0  # 特殊标题默认一级
                break

    def _validate_by_context(
        self,
        result: HeadingInfo,
        text: str,
        context_before: Optional[str],
        context_after: Optional[str]
    ):
        """基于上下文判定"""
        # 如果后面跟着长正文，更可能是标题
        if context_after and len(context_after) > 100 and len(text) < 50:
            result.confidence = min(result.confidence + 0.1, 1.0)
            result.evidence.append("context: followed by long paragraph")

        # 如果文本很短且独立，更可能是标题
        if len(text) < 30:
            result.confidence = min(result.confidence + 0.05, 1.0)
            result.evidence.append("context: short standalone text")

    def _validate_by_text_only(self, text: str) -> HeadingInfo:
        """仅基于文本判定（无法定位到 XML 时的回退方案）"""
        result = HeadingInfo()
        self._validate_by_text(result, text)
        result.evidence.append("fallback: text-only validation")
        self._finalize(result)
        return result

    def _extract_level_from_style_name(self, style_name: str) -> Optional[int]:
        """从样式名提取层级"""
        # Heading 1, Heading 2, ...
        match = re.search(r'heading\s*(\d+)', style_name, re.IGNORECASE)
        if match:
            return int(match.group(1)) - 1  # Heading 1 -> level 0

        # 标题 1, 标题 2, ...
        match = re.search(r'标题\s*(\d+)', style_name)
        if match:
            return int(match.group(1)) - 1

        return None

    def _finalize(self, result: HeadingInfo):
        """综合判定，最终确定结果"""
        # 如果置信度太低，不认为是标题
        if result.confidence < 0.5:
            result.is_heading = False

        # 默认层级
        if result.is_heading and result.heading_level is None:
            result.heading_level = 0

    def validate_elements(
        self,
        elements: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        批量判定元素列表

        Args:
            elements: unstructured 解析出的元素列表

        Returns:
            增强后的元素列表（添加 heading_info 字段）
        """
        enriched = []

        for i, el in enumerate(elements):
            # 获取上下文
            context_before = elements[i - 1].get("text") if i > 0 else None
            context_after = elements[i + 1].get("text") if i < len(elements) - 1 else None

            # 判定
            heading_info = self.validate(el, context_before, context_after)

            # 增强元素
            enriched_el = el.copy()
            if "metadata" not in enriched_el:
                enriched_el["metadata"] = {}

            enriched_el["metadata"]["heading_info"] = {
                "is_heading": heading_info.is_heading,
                "heading_level": heading_info.heading_level,
                "heading_number": heading_info.heading_number,
                "confidence": heading_info.confidence,
                "evidence": heading_info.evidence
            }

            enriched.append(enriched_el)

        return enriched


def enrich_headings(
    docx_path: Union[str, Path],
    elements: List[Dict[str, Any]],
    verbose: bool = False
) -> List[Dict[str, Any]]:
    """
    一站式标题增强函数

    Args:
        docx_path: docx 文件路径
        elements: unstructured 解析出的元素列表
        verbose: 是否打印详细信息

    Returns:
        增强后的元素列表
    """
    # 加载 docx XML
    loader = DocxXmlLoader(docx_path, verbose=verbose)
    loader.load()

    # 创建判定器
    validator = HeadingValidator(loader, verbose=verbose)

    # 批量判定
    return validator.validate_elements(elements)


# ============== 命令行入口 ==============

if __name__ == "__main__":
    import sys
    import json
    from .docx_title_extractor import extract_titles_from_docx

    if len(sys.argv) < 2:
        print("用法: python heading_validator.py <docx_file>")
        print("示例: python heading_validator.py input.docx")
        sys.exit(1)

    docx_file = sys.argv[1]

    print(f"{'=' * 60}")
    print(f"[HeadingValidator] 开始处理: {Path(docx_file).name}")
    print(f"{'=' * 60}")

    # 1. 用 unstructured 提取元素
    print("\n[Step 1] 使用 unstructured 解析...")
    titles, all_elements = extract_titles_from_docx(docx_file, return_all_elements=True)

    # 转换为 dict 格式
    elements_dict = []
    for idx, el in enumerate(all_elements):
        cat = getattr(el, "category", None) or getattr(el, "type", None)
        el_dict = {
            "text": (el.text or "").strip(),
            "category": cat,
            "index": idx,
            "metadata": {}
        }

        # 如果有 paragraph_locator
        if hasattr(el, "metadata") and hasattr(el.metadata, "paragraph_locator"):
            el_dict["metadata"]["paragraph_locator"] = el.metadata.paragraph_locator

        elements_dict.append(el_dict)

    print(f"  解析出 {len(elements_dict)} 个元素")

    # 2. 标题增强
    print("\n[Step 2] 进行标题二次判定...")
    enriched = enrich_headings(docx_file, elements_dict, verbose=True)

    # 3. 统计结果
    heading_count = sum(1 for e in enriched if e.get("metadata", {}).get("heading_info", {}).get("is_heading"))
    print(f"\n[结果] 共判定出 {heading_count} 个标题")

    # 打印前 10 个标题
    print(f"\n[前 10 个标题]")
    count = 0
    for e in enriched:
        info = e.get("metadata", {}).get("heading_info", {})
        if info.get("is_heading"):
            text = e.get("text", "")[:50]
            level = info.get("heading_level", "?")
            conf = info.get("confidence", 0)
            print(f"  L{level} ({conf:.2f}): {text}")
            count += 1
            if count >= 10:
                break
