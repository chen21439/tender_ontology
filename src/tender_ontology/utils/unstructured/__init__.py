"""
Unstructured 文档处理工具模块

提供基于 unstructured 库的文档解析功能，
主要用于从 docx 等文档中提取标题和结构信息。
"""

from .docx_title_extractor import (
    extract_titles_from_docx,
    extract_titles_to_txt,
    is_probably_title,
)

from .unstructured_heading_extractor import UnstructuredHeadingExtractor

__all__ = [
    "extract_titles_from_docx",
    "extract_titles_to_txt",
    "is_probably_title",
    "UnstructuredHeadingExtractor",
]