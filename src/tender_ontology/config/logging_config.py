"""
日志配置模块

使用 loguru 实现：
- 按日期自动轮转日志文件
- 同时输出到控制台和文件
- 自动保留指定天数的日志
- 自动压缩旧日志
"""

import sys
from pathlib import Path
from loguru import logger

from tender_ontology.config.settings import settings

# 标志：是否已初始化
_initialized = False


def setup_logging(
    log_dir: str = "log",
    retention: str = "30 days",
    rotation: str = "00:00",
    compression: str = "zip",
    log_level: str = "INFO"
):
    """
    配置日志系统

    Args:
        log_dir: 日志目录
        retention: 日志保留时间，如 "30 days"
        rotation: 日志轮转时间，如 "00:00" 表示每天午夜
        compression: 压缩格式，如 "zip", "gz"
        log_level: 日志级别
    """
    global _initialized
    if _initialized:
        return logger

    print(f"[LoggingConfig] 正在初始化日志系统...")

    # 创建日志目录
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 根据环境设置日志级别
    if settings.debug:
        log_level = "DEBUG"

    # 移除默认的 handler
    logger.remove()

    # 添加控制台输出（使用 stdout 以便 PyCharm 能正确显示）
    logger.add(
        sys.stdout,
        level=log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
        colorize=True,
    )

    # 添加文件输出 - 按日期轮转
    logger.add(
        f"{log_dir}/{{time:YYYY-MM-DD}}.log",
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation=rotation,      # 每天午夜轮转
        retention=retention,    # 保留30天
        compression=compression, # 压缩旧日志
        encoding="utf-8",
        enqueue=True,           # 异步写入，提高性能
    )

    # 添加错误日志单独文件
    logger.add(
        f"{log_dir}/error_{{time:YYYY-MM-DD}}.log",
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation=rotation,
        retention=retention,
        compression=compression,
        encoding="utf-8",
        enqueue=True,
    )

    _initialized = True
    logger.info(f"日志系统初始化完成，环境: {settings.env}, 级别: {log_level}, 目录: {log_dir}")

    return logger


# 模块加载时自动初始化日志配置
setup_logging()

# 导出 logger 实例供其他模块使用
__all__ = ["logger", "setup_logging"]
