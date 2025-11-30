"""
DOCX XML 加载器

从 docx 文件中读取 OOXML (word/document.xml)，建立段落索引，
支持通过 locator 信息定位到具体的 <w:p> 元素。

功能：
1. 解压 docx -> 读取 word/document.xml 和 word/styles.xml
2. 建立索引：para_id -> <w:p>、flat_index -> <w:p>
3. 根据 locator 定位 <w:p> 元素
4. 提取 <w:p> 的样式信息（pStyle、outlineLvl、numPr）
"""

import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from zipfile import ZipFile
from dataclasses import dataclass

from lxml import etree


# OOXML 命名空间
OOXML_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


@dataclass
class ParagraphLocator:
    """段落定位信息"""
    para_id: Optional[str] = None
    path: Optional[str] = None
    flat_index: Optional[int] = None
    text_hash: Optional[str] = None


@dataclass
class ParagraphStyle:
    """段落样式信息"""
    style_id: Optional[str] = None          # pStyle 的 val
    style_name: Optional[str] = None        # 样式名称（从 styles.xml 获取）
    outline_level: Optional[int] = None     # outlineLvl (0=一级标题, 1=二级标题...)
    num_id: Optional[str] = None            # numPr/numId
    ilvl: Optional[str] = None              # numPr/ilvl (编号层级)
    based_on: Optional[str] = None          # 基于哪个样式
    is_heading_style: bool = False          # 是否是标题样式


class DocxXmlLoader:
    """DOCX XML 加载器"""

    def __init__(self, docx_path: Union[str, Path], verbose: bool = False):
        """
        初始化加载器

        Args:
            docx_path: docx 文件路径
            verbose: 是否打印详细信息
        """
        self.docx_path = Path(docx_path)
        self.verbose = verbose

        # XML 根节点
        self.document_root: Optional[etree._Element] = None
        self.styles_root: Optional[etree._Element] = None
        self.numbering_root: Optional[etree._Element] = None

        # 索引
        self.by_para_id: Dict[str, etree._Element] = {}
        self.by_index: List[etree._Element] = []
        self.by_text_hash: Dict[str, List[etree._Element]] = {}

        # 样式映射
        self.styles_map: Dict[str, ParagraphStyle] = {}

        # 标题样式 ID 集合
        self.heading_style_ids: set = set()

    def load(self) -> "DocxXmlLoader":
        """
        加载 docx 文件，解析 XML 并建立索引

        Returns:
            self (支持链式调用)
        """
        if not self.docx_path.exists():
            raise FileNotFoundError(f"文件不存在: {self.docx_path}")

        with ZipFile(self.docx_path) as z:
            # 读取 document.xml
            document_xml = z.read("word/document.xml")
            self.document_root = etree.fromstring(document_xml)

            # 读取 styles.xml (可选)
            try:
                styles_xml = z.read("word/styles.xml")
                self.styles_root = etree.fromstring(styles_xml)
                self._parse_styles()
            except KeyError:
                if self.verbose:
                    print("[DocxXmlLoader] 未找到 styles.xml")

            # 读取 numbering.xml (可选)
            try:
                numbering_xml = z.read("word/numbering.xml")
                self.numbering_root = etree.fromstring(numbering_xml)
            except KeyError:
                if self.verbose:
                    print("[DocxXmlLoader] 未找到 numbering.xml")

        # 建立段落索引
        self._build_paragraph_index()

        if self.verbose:
            print(f"[DocxXmlLoader] 加载完成: {self.docx_path.name}")
            print(f"  - 段落数: {len(self.by_index)}")
            print(f"  - para_id 索引: {len(self.by_para_id)}")
            print(f"  - 样式数: {len(self.styles_map)}")
            print(f"  - 标题样式: {self.heading_style_ids}")

        return self

    def _parse_styles(self):
        """解析 styles.xml，提取样式信息"""
        if self.styles_root is None:
            return

        # 查找所有样式定义
        for style_el in self.styles_root.xpath(".//w:style", namespaces=OOXML_NS):
            style_id = style_el.get("{%s}styleId" % OOXML_NS["w"])
            style_type = style_el.get("{%s}type" % OOXML_NS["w"])

            if not style_id or style_type != "paragraph":
                continue

            style_info = ParagraphStyle(style_id=style_id)

            # 样式名称
            name_el = style_el.find("w:name", namespaces=OOXML_NS)
            if name_el is not None:
                style_info.style_name = name_el.get("{%s}val" % OOXML_NS["w"])

            # basedOn
            based_on_el = style_el.find("w:basedOn", namespaces=OOXML_NS)
            if based_on_el is not None:
                style_info.based_on = based_on_el.get("{%s}val" % OOXML_NS["w"])

            # outlineLvl (在 pPr 下)
            outline_el = style_el.find(".//w:outlineLvl", namespaces=OOXML_NS)
            if outline_el is not None:
                try:
                    style_info.outline_level = int(outline_el.get("{%s}val" % OOXML_NS["w"]))
                except (ValueError, TypeError):
                    pass

            # 判断是否是标题样式
            if style_info.style_name:
                name_lower = style_info.style_name.lower()
                if "heading" in name_lower or name_lower.startswith("标题"):
                    style_info.is_heading_style = True
                    self.heading_style_ids.add(style_id)

            if style_info.outline_level is not None:
                style_info.is_heading_style = True
                self.heading_style_ids.add(style_id)

            # basedOn 包含 Heading
            if style_info.based_on and "heading" in style_info.based_on.lower():
                style_info.is_heading_style = True
                self.heading_style_ids.add(style_id)

            self.styles_map[style_id] = style_info

    def _build_paragraph_index(self):
        """建立段落索引"""
        if self.document_root is None:
            return

        # 查找 body 下所有 <w:p>
        paragraphs = self.document_root.xpath(".//w:body//w:p", namespaces=OOXML_NS)

        for idx, p in enumerate(paragraphs):
            # para_id 索引 (w14:paraId)
            para_id = p.get("{%s}paraId" % OOXML_NS["w14"])
            if para_id:
                self.by_para_id[para_id] = p

            # flat_index 索引
            self.by_index.append(p)

            # text_hash 索引
            text = self._extract_paragraph_text(p)
            text_hash = self._compute_text_hash(text)
            if text_hash not in self.by_text_hash:
                self.by_text_hash[text_hash] = []
            self.by_text_hash[text_hash].append(p)

    def _extract_paragraph_text(self, p: etree._Element) -> str:
        """提取段落文本"""
        texts = []
        for t in p.xpath(".//w:t", namespaces=OOXML_NS):
            if t.text:
                texts.append(t.text)
        return "".join(texts)

    def _compute_text_hash(self, text: str) -> str:
        """计算文本 hash"""
        normalized = text.strip().replace(" ", "").replace("\n", "")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]

    def locate_paragraph(self, locator: Union[ParagraphLocator, dict]) -> Optional[etree._Element]:
        """
        根据 locator 定位 <w:p> 元素

        优先级：
        1. para_id 精确匹配
        2. flat_index + text_hash 校验
        3. text_hash 全表搜索

        Args:
            locator: 定位信息

        Returns:
            <w:p> 元素，未找到返回 None
        """
        if isinstance(locator, dict):
            locator = ParagraphLocator(
                para_id=locator.get("para_id"),
                path=locator.get("path"),
                flat_index=locator.get("flat_index"),
                text_hash=locator.get("text_hash")
            )

        # 1. para_id 精确匹配
        if locator.para_id and locator.para_id in self.by_para_id:
            if self.verbose:
                print(f"[locate] 通过 para_id 命中: {locator.para_id}")
            return self.by_para_id[locator.para_id]

        # 2. flat_index + text_hash 校验
        if locator.flat_index is not None:
            try:
                p = self.by_index[locator.flat_index]
                if locator.text_hash:
                    actual_hash = self._compute_text_hash(self._extract_paragraph_text(p))
                    if actual_hash == locator.text_hash:
                        if self.verbose:
                            print(f"[locate] 通过 flat_index + text_hash 命中: {locator.flat_index}")
                        return p
                else:
                    if self.verbose:
                        print(f"[locate] 通过 flat_index 命中: {locator.flat_index}")
                    return p
            except IndexError:
                pass

        # 3. text_hash 全表搜索
        if locator.text_hash and locator.text_hash in self.by_text_hash:
            matches = self.by_text_hash[locator.text_hash]
            if matches:
                if self.verbose:
                    print(f"[locate] 通过 text_hash 命中: {locator.text_hash} (共 {len(matches)} 个)")
                return matches[0]

        if self.verbose:
            print(f"[locate] 未找到匹配的段落")
        return None

    def get_paragraph_style(self, p: etree._Element) -> ParagraphStyle:
        """
        获取段落的样式信息

        Args:
            p: <w:p> 元素

        Returns:
            ParagraphStyle
        """
        style = ParagraphStyle()

        # 获取 pPr
        pPr = p.find("w:pPr", namespaces=OOXML_NS)
        if pPr is None:
            return style

        # pStyle
        pStyle = pPr.find("w:pStyle", namespaces=OOXML_NS)
        if pStyle is not None:
            style_id = pStyle.get("{%s}val" % OOXML_NS["w"])
            style.style_id = style_id

            # 从 styles_map 获取更多信息
            if style_id in self.styles_map:
                base_style = self.styles_map[style_id]
                style.style_name = base_style.style_name
                style.based_on = base_style.based_on
                style.is_heading_style = base_style.is_heading_style

                # 继承 outline_level
                if base_style.outline_level is not None:
                    style.outline_level = base_style.outline_level

        # outlineLvl (段落级别，优先于样式级别)
        outline_el = pPr.find("w:outlineLvl", namespaces=OOXML_NS)
        if outline_el is not None:
            try:
                style.outline_level = int(outline_el.get("{%s}val" % OOXML_NS["w"]))
                style.is_heading_style = True
            except (ValueError, TypeError):
                pass

        # numPr (编号)
        numPr = pPr.find("w:numPr", namespaces=OOXML_NS)
        if numPr is not None:
            numId = numPr.find("w:numId", namespaces=OOXML_NS)
            ilvl = numPr.find("w:ilvl", namespaces=OOXML_NS)

            if numId is not None:
                style.num_id = numId.get("{%s}val" % OOXML_NS["w"])
            if ilvl is not None:
                style.ilvl = ilvl.get("{%s}val" % OOXML_NS["w"])

        return style

    def get_paragraph_text(self, p: etree._Element) -> str:
        """获取段落文本"""
        return self._extract_paragraph_text(p)

    def is_heading_style(self, style_id: str) -> bool:
        """判断样式 ID 是否是标题样式"""
        return style_id in self.heading_style_ids


# ============== 命令行入口 ==============

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("用法: python docx_xml_loader.py <docx_file> [para_index]")
        print("示例:")
        print("  python docx_xml_loader.py input.docx")
        print("  python docx_xml_loader.py input.docx 5")
        sys.exit(1)

    docx_file = sys.argv[1]
    para_index = int(sys.argv[2]) if len(sys.argv) > 2 else None

    loader = DocxXmlLoader(docx_file, verbose=True)
    loader.load()

    print(f"\n{'=' * 60}")
    print(f"[样式映射]")
    print(f"{'=' * 60}")
    for style_id, style in list(loader.styles_map.items())[:10]:
        print(f"  {style_id}: {style.style_name} (heading={style.is_heading_style}, outlineLvl={style.outline_level})")

    if para_index is not None:
        print(f"\n{'=' * 60}")
        print(f"[段落 {para_index} 详情]")
        print(f"{'=' * 60}")

        if para_index < len(loader.by_index):
            p = loader.by_index[para_index]
            text = loader.get_paragraph_text(p)
            style = loader.get_paragraph_style(p)

            print(f"  文本: {text[:100]}{'...' if len(text) > 100 else ''}")
            print(f"  样式: {json.dumps(style.__dict__, ensure_ascii=False, indent=4)}")
        else:
            print(f"  索引超出范围 (总共 {len(loader.by_index)} 个段落)")
