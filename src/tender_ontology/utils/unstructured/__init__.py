"""
Unstructured 文档处理工具模块

提供基于 unstructured 库的文档解析功能，
主要用于从 docx 等文档中提取标题和结构信息。

注意：使用懒加载，避免启动时自动加载 unstructured 库
"""

__all__ = [
    "extract_titles_from_docx",
    "extract_titles_to_txt",
    "is_probably_title",
    "UnstructuredHeadingExtractor",
    "batch_extract_xml_from_docx",
]


def __getattr__(name):
    """懒加载，只在实际使用时才导入"""
    if name in ("extract_titles_from_docx", "extract_titles_to_txt", "is_probably_title"):
        from .docx_title_extractor import (
            extract_titles_from_docx,
            extract_titles_to_txt,
            is_probably_title,
        )
        return locals()[name]
    elif name == "UnstructuredHeadingExtractor":
        from .unstructured_heading_extractor import UnstructuredHeadingExtractor
        return UnstructuredHeadingExtractor
    elif name == "batch_extract_xml_from_docx":
        from .unstructured_heading_extractor import UnstructuredHeadingExtractor
        return UnstructuredHeadingExtractor.batch_extract_xml_from_docx
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")