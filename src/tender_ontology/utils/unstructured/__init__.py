"""
Unstructured 文档处理工具模块

提供基于 unstructured 库的文档解析功能，
主要用于从 docx 等文档中提取标题和结构信息。

模块结构：
- docx_preprocessor: DOCX 版本检测与 paraId 预处理
- docx_xml_loader: DOCX XML 加载与段落定位
- heading_validator: 标题二次判定
- heading_prompt: 标题提取提示词
- qwen_heading_api: 千问 API 调用
- chapter_processor: 章节切分与 Stage 2 处理
- unstructured_heading_extractor: 主流程协调器

注意：使用懒加载，避免启动时自动加载 unstructured 库
"""

__all__ = [
    # 旧版兼容
    "extract_titles_from_docx",
    "extract_titles_to_txt",
    "is_probably_title",
    # 主类
    "UnstructuredHeadingExtractor",
    # 新模块
    "preprocess_docx_if_needed",
    "get_docx_version_info",
    "QwenHeadingAPI",
    "ChapterProcessor",
    "DocxXmlLoader",
    "HeadingValidator",
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
    elif name in ("preprocess_docx_if_needed", "get_docx_version_info"):
        from .docx_preprocessor import preprocess_docx_if_needed, get_docx_version_info
        return locals()[name]
    elif name == "QwenHeadingAPI":
        from .qwen_heading_api import QwenHeadingAPI
        return QwenHeadingAPI
    elif name == "ChapterProcessor":
        from .chapter_processor import ChapterProcessor
        return ChapterProcessor
    elif name == "DocxXmlLoader":
        from .docx_xml_loader import DocxXmlLoader
        return DocxXmlLoader
    elif name == "HeadingValidator":
        from .heading_validator import HeadingValidator
        return HeadingValidator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")