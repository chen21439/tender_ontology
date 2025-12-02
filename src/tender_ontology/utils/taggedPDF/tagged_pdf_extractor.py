"""
Tagged PDF 提取器

基于 pdfplumber 实现 MCID → 文本 的完整链路

核心逻辑参考 pdfplumber/cli.py 中的 add_text_to_mcids 函数：
1. 扫描所有页面，构建 page_number -> { mcid -> 文本 } 映射
2. 遍历 structure_tree，为每个有 mcids 的元素填充文本
"""
import json
from collections import defaultdict
from collections import deque
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    pdfplumber = None

# 支持直接运行和作为模块导入
try:
    from .models import StructureElement, MCIDTextMapping, TaggedDocument
except ImportError:
    from models import StructureElement, MCIDTextMapping, TaggedDocument


class TaggedPDFExtractor:
    """
    Tagged PDF 提取器

    从 Tagged PDF 中提取结构树和 MCID 对应的文本内容

    Usage:
        extractor = TaggedPDFExtractor("document.pdf")
        doc = extractor.extract()

        # 获取所有标题
        headings = doc.get_headings()

        # 获取结构树（带文本）
        tree = doc.structure_tree
    """

    def __init__(self, pdf_path: Union[str, Path], verbose: bool = False):
        """
        初始化提取器

        Args:
            pdf_path: PDF 文件路径
            verbose: 是否输出详细日志
        """
        if not PDFPLUMBER_AVAILABLE:
            raise ImportError(
                "pdfplumber 未安装。请运行: pip install pdfplumber"
            )

        self.pdf_path = Path(pdf_path)
        self.verbose = verbose
        self._pdf = None
        self._page_contents: Dict[int, Dict[int, str]] = defaultdict(lambda: defaultdict(str))
        self._mcid_mappings: Dict[int, Dict[int, MCIDTextMapping]] = defaultdict(dict)

    def _log(self, message: str):
        """输出日志"""
        if self.verbose:
            print(f"[TaggedPDFExtractor] {message}")

    def extract(self) -> TaggedDocument:
        """
        提取 Tagged PDF 的完整结构

        Returns:
            TaggedDocument 实例，包含结构树和 MCID 映射
        """
        self._log(f"开始处理: {self.pdf_path}")

        with pdfplumber.open(str(self.pdf_path)) as pdf:
            self._pdf = pdf

            # 检查是否为 Tagged PDF
            is_tagged = self._check_is_tagged(pdf)
            self._log(f"Tagged PDF: {is_tagged}")

            if not is_tagged:
                self._log("警告: 该 PDF 不是 Tagged PDF，结构树可能为空")

            # Step 1: 构建 MCID → 文本映射
            self._build_mcid_text_mapping(pdf)
            self._log(f"MCID 映射构建完成，共 {sum(len(v) for v in self._page_contents.values())} 个映射")

            # Step 2: 获取并处理结构树
            structure_tree = self._process_structure_tree(pdf)
            self._log(f"结构树处理完成，共 {len(structure_tree)} 个根元素")

            # 创建文档对象
            doc = TaggedDocument(
                file_path=str(self.pdf_path),
                page_count=len(pdf.pages),
                is_tagged=is_tagged,
                structure_tree=structure_tree,
                mcid_mappings=dict(self._mcid_mappings),
                metadata=pdf.metadata or {},
            )

            self._log("提取完成")
            return doc

    def _check_is_tagged(self, pdf) -> bool:
        """检查 PDF 是否为 Tagged PDF"""
        try:
            # 检查是否有结构树（尝试迭代但不完全转换）
            from pdfplumber.structure import PDFStructTree
            tree_iter = PDFStructTree(pdf)
            # 尝试获取第一个元素
            first_elem = next(iter(tree_iter), None)
            return first_elem is not None
        except Exception:
            return False

    def _build_mcid_text_mapping(self, pdf):
        """
        构建 MCID 到文本的映射

        这是核心逻辑，参考 pdfplumber CLI 的 add_text_to_mcids 实现：
        遍历每个页面的每个字符，根据 mcid 属性聚合文本
        """
        self._log("构建 MCID → 文本映射...")

        for page in pdf.pages:
            page_number = page.page_number  # 1-indexed
            text_contents = self._page_contents[page_number]

            # 用于存储每个 MCID 的字符列表
            mcid_chars: Dict[int, List[Dict]] = defaultdict(list)

            # 遍历页面上的所有字符
            for char in page.chars:
                mcid = char.get("mcid")
                if mcid is None:
                    continue

                # 累加文本
                text_contents[mcid] += char.get("text", "")
                mcid_chars[mcid].append(char)

            # 创建 MCIDTextMapping 对象
            for mcid, text in text_contents.items():
                self._mcid_mappings[page_number][mcid] = MCIDTextMapping(
                    page_number=page_number,
                    mcid=mcid,
                    text=text,
                    chars=mcid_chars.get(mcid, []),
                )

            if self.verbose and text_contents:
                self._log(f"  页面 {page_number}: {len(text_contents)} 个 MCID")

    def _process_structure_tree(self, pdf) -> List[StructureElement]:
        """
        处理结构树，为每个元素添加文本

        采用广度优先遍历，参考 pdfplumber CLI 的实现
        """
        self._log("处理结构树...")

        try:
            # 尝试安全地获取结构树
            raw_tree = self._get_structure_tree_safe(pdf)
        except Exception as e:
            self._log(f"获取结构树失败: {e}，将使用 MCID 直接构建")
            raw_tree = None

        if not raw_tree:
            # 如果没有结构树，用 MCID 映射直接构建简单结构
            return self._build_structure_from_mcid()

        # 先为原始树添加文本
        self._add_text_to_tree(raw_tree)

        # 转换为 StructureElement 对象
        return self._convert_tree(raw_tree)

    def _get_structure_tree_safe(self, pdf) -> Optional[List[Dict[str, Any]]]:
        """安全地获取结构树，处理可能的序列化错误"""
        try:
            from pdfplumber.structure import PDFStructTree

            result = []
            for elem in PDFStructTree(pdf):
                try:
                    # 手动转换，避免 deepcopy 问题
                    elem_dict = self._convert_struct_elem_to_dict(elem)
                    result.append(elem_dict)
                except Exception as e:
                    self._log(f"转换元素失败: {e}")
                    continue
            return result if result else None
        except Exception as e:
            self._log(f"获取结构树异常: {e}")
            return None

    def _convert_struct_elem_to_dict(self, elem) -> Dict[str, Any]:
        """手动将 StructElement 转换为字典，避免序列化问题"""
        result = {
            "type": getattr(elem, "type", "Unknown"),
            "page_number": getattr(elem, "page_number", None),
            "mcids": list(getattr(elem, "mcids", [])),
        }

        # 处理子元素
        children = getattr(elem, "children", [])
        if children:
            result["children"] = [
                self._convert_struct_elem_to_dict(child)
                for child in children
            ]

        # 复制其他简单属性
        for attr in ["alt", "lang", "actual_text", "title"]:
            val = getattr(elem, attr, None)
            if val is not None:
                result[attr] = val

        return result

    def _build_structure_from_mcid(self) -> List[StructureElement]:
        """当没有结构树时，从 MCID 映射直接构建简单结构"""
        self._log("使用 MCID 直接构建文档结构...")

        elements = []

        # 按页面组织内容
        for page_number in sorted(self._page_contents.keys()):
            page_texts = self._page_contents[page_number]

            # 为每个页面创建一个容器元素
            page_children = []

            for mcid in sorted(page_texts.keys()):
                text = page_texts[mcid]
                if text.strip():
                    # 创建一个通用的文本元素
                    child = StructureElement(
                        type="Text",
                        page_number=page_number,
                        mcids=[mcid],
                        text=[text],
                    )
                    page_children.append(child)

            if page_children:
                page_elem = StructureElement(
                    type="Page",
                    page_number=page_number,
                    children=page_children,
                )
                elements.append(page_elem)

        return elements

    def _add_text_to_tree(self, tree: List[Dict[str, Any]]):
        """
        为结构树的每个元素添加文本内容

        使用广度优先遍历，参考 pdfplumber CLI
        """
        queue = deque(tree)

        while queue:
            element = queue.popleft()

            # 处理子元素
            children = element.get("children", [])
            if children:
                queue.extend(children)

            # 获取页码
            page_number = element.get("page_number")
            if page_number is None:
                continue

            # 获取该页面的 MCID → 文本映射
            text_contents = self._page_contents.get(page_number, {})

            # 为该元素填充文本
            mcids = element.get("mcids", [])
            if mcids:
                element["text"] = [text_contents.get(mcid, "") for mcid in mcids]

    def _convert_tree(self, raw_tree: List[Dict[str, Any]]) -> List[StructureElement]:
        """将原始结构树转换为 StructureElement 对象"""
        return [self._convert_element(elem) for elem in raw_tree]

    def _convert_element(self, raw_element: Dict[str, Any]) -> StructureElement:
        """转换单个元素"""
        # 提取属性（排除已知字段）
        known_fields = {"type", "page_number", "mcids", "text", "children"}
        attributes = {k: v for k, v in raw_element.items() if k not in known_fields}

        # 递归转换子元素
        children = [
            self._convert_element(child)
            for child in raw_element.get("children", [])
        ]

        return StructureElement(
            type=raw_element.get("type", "Unknown"),
            page_number=raw_element.get("page_number"),
            mcids=raw_element.get("mcids", []),
            text=raw_element.get("text", []),
            attributes=attributes,
            children=children,
        )


def extract_structure_with_text(
    pdf_path: Union[str, Path],
    verbose: bool = False
) -> TaggedDocument:
    """
    从 Tagged PDF 提取带文本的结构树

    便捷函数，等价于:
        TaggedPDFExtractor(pdf_path, verbose).extract()

    Args:
        pdf_path: PDF 文件路径
        verbose: 是否输出详细日志

    Returns:
        TaggedDocument 实例
    """
    extractor = TaggedPDFExtractor(pdf_path, verbose=verbose)
    return extractor.extract()


def get_mcid_text_mapping(
    pdf_path: Union[str, Path],
    page_number: Optional[int] = None
) -> Dict[int, Dict[int, str]]:
    """
    获取 MCID 到文本的映射

    Args:
        pdf_path: PDF 文件路径
        page_number: 指定页码 (1-indexed)，None 表示所有页面

    Returns:
        如果指定页码: { mcid: text }
        如果不指定: { page_number: { mcid: text } }
    """
    if not PDFPLUMBER_AVAILABLE:
        raise ImportError("pdfplumber 未安装。请运行: pip install pdfplumber")

    result: Dict[int, Dict[int, str]] = defaultdict(dict)

    with pdfplumber.open(str(pdf_path)) as pdf:
        pages_to_process = [pdf.pages[page_number - 1]] if page_number else pdf.pages

        for page in pages_to_process:
            pn = page.page_number
            for char in page.chars:
                mcid = char.get("mcid")
                if mcid is not None:
                    if mcid not in result[pn]:
                        result[pn][mcid] = ""
                    result[pn][mcid] += char.get("text", "")

    if page_number:
        return result.get(page_number, {})
    return dict(result)


def extract_tagged_elements(
    pdf_path: Union[str, Path],
    element_types: Optional[List[str]] = None,
    verbose: bool = False
) -> List[Dict[str, Any]]:
    """
    提取指定类型的结构元素

    Args:
        pdf_path: PDF 文件路径
        element_types: 要提取的元素类型列表，如 ["H1", "H2", "P"]
                      None 表示提取所有类型
        verbose: 是否输出详细日志

    Returns:
        元素列表，每项包含 type, page_number, text
    """
    doc = extract_structure_with_text(pdf_path, verbose=verbose)
    results = []

    def collect_elements(elements: List[StructureElement]):
        for elem in elements:
            if element_types is None or elem.type in element_types:
                if elem.has_content:
                    results.append({
                        "type": elem.type,
                        "page_number": elem.page_number,
                        "text": elem.full_text,
                        "mcids": elem.mcids,
                    })
            collect_elements(elem.children)

    collect_elements(doc.structure_tree)
    return results


# ============================================================================
# CLI 和测试
# ============================================================================

def _print_structure_tree(elements: List[StructureElement], indent: int = 0):
    """打印结构树（调试用）"""
    for elem in elements:
        prefix = "  " * indent
        text_preview = elem.full_text[:40].replace("\n", " ") if elem.has_content else "(no text)"
        print(f"{prefix}- {elem.type} [page={elem.page_number}]: {text_preview}")
        _print_structure_tree(elem.children, indent + 1)


def _collect_elements_by_type(
    elements: List[StructureElement],
    target_types: List[str],
    results: List[Dict[str, Any]]
):
    """递归收集指定类型的元素"""
    for elem in elements:
        if elem.type in target_types and elem.has_content:
            results.append({
                "type": elem.type,
                "page_number": elem.page_number,
                "text": elem.full_text,
                "mcids": elem.mcids,
            })
        _collect_elements_by_type(elem.children, target_types, results)


def extract_and_save_to_txt(pdf_path: str, output_dir: str):
    """
    从 Tagged PDF 提取表格和段落，保存为 txt 文件

    Args:
        pdf_path: PDF 文件路径
        output_dir: 输出目录
    """
    import os

    print(f"\n{'='*60}")
    print(f"处理文件: {pdf_path}")
    print(f"输出目录: {output_dir}")
    print(f"{'='*60}\n")

    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)

    # 提取文档结构
    doc = extract_structure_with_text(pdf_path, verbose=True)

    print(f"\n文件: {doc.file_path}")
    print(f"页数: {doc.page_count}")
    print(f"Tagged: {doc.is_tagged}")

    if not doc.is_tagged:
        print("警告: 该 PDF 不是 Tagged PDF，可能无法提取结构化内容")

    # 收集段落 (P 类型)
    paragraphs = []
    paragraph_types = ["P", "Span", "Text"]
    _collect_elements_by_type(doc.structure_tree, paragraph_types, paragraphs)

    # 收集表格 (Table 类型)
    tables = []
    table_types = ["Table", "TR", "TD", "TH", "TBody", "THead", "TFoot"]
    _collect_elements_by_type(doc.structure_tree, table_types, tables)

    # 收集标题
    headings = doc.get_headings()

    # 保存段落到 txt
    paragraphs_file = os.path.join(output_dir, "paragraphs.txt")
    with open(paragraphs_file, "w", encoding="utf-8") as f:
        f.write(f"# 段落内容提取\n")
        f.write(f"# 来源: {pdf_path}\n")
        f.write(f"# 共 {len(paragraphs)} 个段落\n")
        f.write(f"{'='*60}\n\n")

        for i, p in enumerate(paragraphs, 1):
            text = p["text"].strip()
            if text:
                f.write(f"[段落 {i}] (页 {p['page_number']}, 类型: {p['type']})\n")
                f.write(f"{text}\n")
                f.write(f"\n{'-'*40}\n\n")

    print(f"\n段落已保存到: {paragraphs_file} (共 {len(paragraphs)} 个)")

    # 保存表格到 txt
    tables_file = os.path.join(output_dir, "tables.txt")
    with open(tables_file, "w", encoding="utf-8") as f:
        f.write(f"# 表格内容提取\n")
        f.write(f"# 来源: {pdf_path}\n")
        f.write(f"# 共 {len(tables)} 个表格元素\n")
        f.write(f"{'='*60}\n\n")

        for i, t in enumerate(tables, 1):
            text = t["text"].strip()
            if text:
                f.write(f"[表格元素 {i}] (页 {t['page_number']}, 类型: {t['type']})\n")
                f.write(f"{text}\n")
                f.write(f"\n{'-'*40}\n\n")

    print(f"表格已保存到: {tables_file} (共 {len(tables)} 个元素)")

    # 保存标题到 txt
    headings_file = os.path.join(output_dir, "headings.txt")
    with open(headings_file, "w", encoding="utf-8") as f:
        f.write(f"# 标题内容提取\n")
        f.write(f"# 来源: {pdf_path}\n")
        f.write(f"# 共 {len(headings)} 个标题\n")
        f.write(f"{'='*60}\n\n")

        for i, h in enumerate(headings, 1):
            text = h["text"].strip()
            if text:
                indent = "  " * (h["level"] - 1)
                f.write(f"{indent}[H{h['level']}] (页 {h['page_number']}): {text}\n")

    print(f"标题已保存到: {headings_file} (共 {len(headings)} 个)")

    # 保存完整结构树为 JSON
    structure_file = os.path.join(output_dir, "structure.json")
    with open(structure_file, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, ensure_ascii=False, indent=2)
    print(f"结构树已保存到: {structure_file}")

    print(f"\n{'='*60}")
    print("提取完成!")
    print(f"{'='*60}")

    return {
        "paragraphs_count": len(paragraphs),
        "tables_count": len(tables),
        "headings_count": len(headings),
        "output_dir": output_dir,
    }


if __name__ == "__main__":
    import sys
    import os

    # 默认测试路径
    DEFAULT_PDF_PATH = r"E:\programFile\AIProgram\tender_ontology\static\upload\25113013334324628923\深圳理工大学家具采购.pdf"
    DEFAULT_OUTPUT_DIR = r"E:\programFile\AIProgram\tender_ontology\static\upload\25113013334324628923"

    print("""
=================================================================
Tagged PDF 提取器 - 基于 pdfplumber

功能：
- 从 Tagged PDF 提取结构树
- 建立 MCID → 文本映射
- 提取标题、段落、表格等语义元素
- 将内容保存为 txt 文件

使用方法：
    # 命令行
    python tagged_pdf_extractor.py <pdf_path> [output_dir]

    # Python 代码
    from tender_ontology.utils.taggedPDF import (
        TaggedPDFExtractor,
        extract_structure_with_text,
    )

    doc = extract_structure_with_text("document.pdf")
    headings = doc.get_headings()
    paragraphs = doc.get_all_text_by_type("P")
=================================================================
    """)

    # 处理命令行参数
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        output_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(pdf_path)
    else:
        # 使用默认路径
        pdf_path = DEFAULT_PDF_PATH
        output_dir = DEFAULT_OUTPUT_DIR
        print(f"使用默认路径: {pdf_path}")

    # 检查文件是否存在
    if not os.path.exists(pdf_path):
        print(f"错误: 文件不存在 - {pdf_path}")
        sys.exit(1)

    try:
        result = extract_and_save_to_txt(pdf_path, output_dir)
        print(f"\n统计信息:")
        print(f"  - 段落数: {result['paragraphs_count']}")
        print(f"  - 表格元素数: {result['tables_count']}")
        print(f"  - 标题数: {result['headings_count']}")

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
