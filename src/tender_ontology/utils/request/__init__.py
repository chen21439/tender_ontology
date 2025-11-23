"""
请求工具模块
提供统一的 AI 请求接口
"""

from .ai_client import AIClient, get_global_client, reset_global_client
from .batch_manager import BatchManager, get_default_batch_manager, reset_default_batch_manager
from .batch_processor import (
    BatchProcessor,
    get_default_batch_processor,
    reset_default_batch_processor,
    merge_candidates_with_dedup
)

__all__ = [
    "AIClient",
    "get_global_client",
    "reset_global_client",
    "BatchManager",
    "get_default_batch_manager",
    "reset_default_batch_manager",
    "BatchProcessor",
    "get_default_batch_processor",
    "reset_default_batch_processor",
    "merge_candidates_with_dedup"
]