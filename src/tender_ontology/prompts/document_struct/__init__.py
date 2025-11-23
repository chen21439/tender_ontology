"""
document_struct prompts 模块
提供文档结构分析相关的提示词模板
"""

from .document_layout_analysis_prompt import DOCUMENT_LAYOUT_ANALYSIS_PROMPT
from .document_hierarchy_prompt import DOCUMENT_HIERARCHY_PROMPT
from .document_relation_prediction_prompt import (
    RELATION_PREDICTION_PROMPT,
    get_relation_prediction_prompt
)
from .image_understanding_prompt import (
    BASIC_IMAGE_PROMPT,
    DOCUMENT_IMAGE_WITH_JSON_PROMPT,
    TABLE_RECOGNITION_PROMPT,
    HEADING_RECOGNITION_PROMPT,
    DOCUMENT_LINE_TAGGING_PROMPT,
)

__all__ = [
    "DOCUMENT_LAYOUT_ANALYSIS_PROMPT",
    "DOCUMENT_HIERARCHY_PROMPT",
    "RELATION_PREDICTION_PROMPT",
    "get_relation_prediction_prompt",
    "BASIC_IMAGE_PROMPT",
    "DOCUMENT_IMAGE_WITH_JSON_PROMPT",
    "TABLE_RECOGNITION_PROMPT",
    "HEADING_RECOGNITION_PROMPT",
    "DOCUMENT_LINE_TAGGING_PROMPT",
]