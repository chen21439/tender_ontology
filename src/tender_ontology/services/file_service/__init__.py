"""
文件处理服务

统一入口，根据文件类型分发到不同的处理器：
- PDF: 使用 Docling 处理
- DOCX: 使用 Unstructured 处理 + DOCX 转 PDF 服务
"""

from .service import FileService, get_file_service

__all__ = ["FileService", "get_file_service"]
