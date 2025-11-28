"""
DOCX 文档处理模块

使用 docling 解析 DOCX 文件，按阅读顺序提取文本和表格
"""

from .reader import DocxReader

__all__ = ["DocxReader"]