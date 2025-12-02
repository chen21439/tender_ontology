"""
PDF 任务相关数据模型
"""

from pydantic import BaseModel
from typing import Optional, Dict, Any


class PDFProcessResponse(BaseModel):
    """PDF 处理统一响应"""
    success: bool
    errCode: Optional[str] = None
    errMsg: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    success: bool
    errCode: Optional[str] = None
    errMsg: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class PageRequest(BaseModel):
    """分页请求"""
    pageNum: int = 1
    pageSize: int = 10


class PageDataResponse(BaseModel):
    """分页数据响应"""
    total: str
    pageSize: str
    pageTotal: str
    pageNum: str
    dataList: list


class PageResponse(BaseModel):
    """分页响应"""
    success: bool
    errCode: Optional[str] = None
    errMsg: Optional[str] = None
    data: PageDataResponse