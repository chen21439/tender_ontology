"""
taggedPDF 工具模块
基于 pdfplumber 从 Tagged PDF 中提取 MCID → 文本映射

核心功能：
- 解析 PDF 结构树 (structure_tree)
- 建立 MCID 到文本内容的映射
- 提取带有语义标签的文档结构

参考实现：pdfplumber CLI 中的 add_text_to_mcids 函数
"""

from .tagged_pdf_extractor import (
    TaggedPDFExtractor,
    extract_structure_with_text,
    get_mcid_text_mapping,
    extract_tagged_elements,
)

from .models import (
    StructureElement,
    MCIDTextMapping,
    TaggedDocument,
)

__all__ = [
    # 主要提取器
    "TaggedPDFExtractor",
    # 便捷函数
    "extract_structure_with_text",
    "get_mcid_text_mapping",
    "extract_tagged_elements",
    # 数据模型
    "StructureElement",
    "MCIDTextMapping",
    "TaggedDocument",
]
