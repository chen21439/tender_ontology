"""
Docling 相关配置
"""
from pathlib import Path
from pydantic_settings import BaseSettings


class DoclingSettings(BaseSettings):
    """Docling 服务配置"""

    # 模式配置
    offline_mode: bool = True  # 离线模式
    disable_table_recognition: bool = False  # 表格识别开关
    hierarchy_refinement: bool = False  # 层级修正插件
    hierarchy_raise_on_error: bool = False  # 出错时是否抛出异常

    # 输出路径
    output_base_dir: Path = Path("static/artifact/docling")
    json_output_dir: Path = Path("static/artifact/docling/json")
    markdown_output_dir: Path = Path("static/artifact/docling/markdown")
    labeled_output_dir: Path = Path("static/artifact/docling/labeled")
    hierarchy_output_dir: Path = Path("static/artifact/hierarchy")

    # 大模型API配置（用于层级分析）
    llm_api_key: str = ""
    llm_api_base: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"

    class Config:
        env_prefix = "DOCLING_"
        env_file = ".env"


# 全局配置实例
docling_settings = DoclingSettings()