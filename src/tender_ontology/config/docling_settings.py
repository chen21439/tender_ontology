"""
Docling 相关配置
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings


def _get_project_root() -> Path:
    """获取项目根目录（包含 pyproject.toml 的目录）"""
    current = Path(__file__).resolve()
    # 从当前文件向上查找，直到找到包含 pyproject.toml 的目录
    for parent in [current] + list(current.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    # 如果找不到，返回当前工作目录
    return Path.cwd()


# 项目根目录
PROJECT_ROOT = _get_project_root()


class DoclingSettings(BaseSettings):
    """Docling 服务配置"""

    # 模式配置
    offline_mode: bool = True  # 离线模式
    disable_table_recognition: bool = False  # 表格识别开关
    hierarchy_refinement: bool = True  # 层级修正插件（已启用）⬅️ 改这里
    hierarchy_raise_on_error: bool = False  # 出错时是否抛出异常

    # 输出路径（相对于项目根目录）
    output_base_dir: Path = PROJECT_ROOT / "static" / "artifact" / "docling"
    json_output_dir: Path = PROJECT_ROOT / "static" / "artifact" / "docling" / "json"
    markdown_output_dir: Path = PROJECT_ROOT / "static" / "artifact" / "docling" / "markdown"
    labeled_output_dir: Path = PROJECT_ROOT / "static" / "artifact" / "docling" / "labeled"
    hierarchy_output_dir: Path = PROJECT_ROOT / "static" / "artifact" / "hierarchy"

    # 大模型API配置（用于层级分析）
    llm_api_key: str = ""
    llm_api_base: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"

    class Config:
        env_prefix = "DOCLING_"
        env_file = ".env"


# 全局配置实例
docling_settings = DoclingSettings()