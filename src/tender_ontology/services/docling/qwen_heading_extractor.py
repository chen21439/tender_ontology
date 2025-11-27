"""
千问标题提取服务

提供：
1. QwenHeadingExtractor: 上传文件模式 (fileid://)
2. QwenDirectExtractor: 直接传入内容模式（推荐，效果更好）
"""

from tender_ontology.services.docling.qwen_heading_extractor_file import QwenHeadingExtractor
from tender_ontology.services.docling.qwen_direct_extractor import QwenDirectExtractor

__all__ = ["QwenHeadingExtractor", "QwenDirectExtractor"]
