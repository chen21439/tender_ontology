"""
推理服务模块

提供 predict API 调用功能
"""

from .predict_client import PredictClient

__all__ = ["PredictClient"]