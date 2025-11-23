"""
文档层级目录构建示例

演示如何使用 hierarchy_builder 工具构建文档的层级目录结构
"""
import os
from pathlib import Path

from tender_ontology.utils.document_struct import (
    BaiduTextClient,
    process_document_hierarchy
)

# 获取项目根目录（examples 的父目录）
PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)  # 切换工作目录到项目根目录


def example_basic_usage():
    """基础用法示例"""
    print("=" * 80)
    print("示例1: 基础用法 - 构建文档层级目录")
    print("=" * 80)

    # 指定已标注的 JSON 文件路径
    json_path = "static/artifact/docling/城市大数据中心物业管理服务_tagged_20251123_175828.json"

    # 方式1：使用默认配置（自动创建客户端）
    result = process_document_hierarchy(
        json_path=json_path,
        include_sections_only=True,  # 只分析章节标题
        verbose=True,                # 显示详细信息
        save_results=True            # 保存结果到文件
    )

    print("\n处理完成!")
    print(f"结果保存到: {result.get('source_file')}")


def example_custom_client():
    """自定义客户端示例"""
    print("\n" + "=" * 80)
    print("示例2: 使用自定义文本客户端")
    print("=" * 80)

    # 创建自定义文本客户端
    client = BaiduTextClient(
        model="ernie-4.0-turbo-8k",  # 使用 ERNIE 4.0 Turbo
        api_key=None                 # 使用默认 API Key
    )

    json_path = "static/artifact/docling/城市大数据中心物业管理服务_tagged_20251123_175828.json"

    # 使用自定义客户端
    result = process_document_hierarchy(
        json_path=json_path,
        client=client,               # 传入自定义客户端
        include_sections_only=True,
        temperature=0.1,             # 自定义温度参数
        verbose=True
    )

    print("\n处理完成!")


def example_analyze_full_document():
    """分析完整文档示例（包含所有内容，不只是章节）"""
    print("\n" + "=" * 80)
    print("示例3: 分析完整文档（包含所有行）")
    print("=" * 80)

    json_path = "static/artifact/docling/城市大数据中心物业管理服务_tagged_20251123_175828.json"

    # 分析完整文档（包含所有行，不只是章节标题）
    result = process_document_hierarchy(
        json_path=json_path,
        include_sections_only=False,  # 包含所有内容
        verbose=True,
        save_results=True,
        output_dir="static/artifact/docling"  # 自定义输出目录
    )

    print("\n处理完成!")


def example_extract_sections_only():
    """只提取章节标题示例"""
    print("\n" + "=" * 80)
    print("示例4: 只提取章节标题（不调用 API）")
    print("=" * 80)

    from tender_ontology.utils.document_struct import (
        load_tagged_document,
        extract_text_content
    )

    json_path = "static/artifact/docling/城市大数据中心物业管理服务_tagged_20251123_175828.json"

    # 加载文档
    lines_data = load_tagged_document(json_path)
    print(f"总行数: {len(lines_data)}")

    # 只提取章节标题
    sections_text = extract_text_content(lines_data, include_sections_only=True)
    print(f"\n章节标题文本长度: {len(sections_text)} 字符")
    print(f"\n章节标题列表:\n{sections_text}")


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                        文档层级目录构建工具 - 使用示例                        ║
╚══════════════════════════════════════════════════════════════════════════════╝

本示例演示如何使用 hierarchy_builder 工具构建文档的层级目录结构。

前置条件:
1. 已标注的文档 JSON 文件（包含 class 字段标注）
2. 百度千帆 API Key（已内置默认 Key）

提示:
- 取消注释下面的示例代码来运行对应的示例
- 确保 JSON 文件路径正确
    """)

    # 示例1: 基础用法（推荐新手使用）
    example_basic_usage()

    # 示例2: 使用自定义客户端
    # example_custom_client()

    # 示例3: 分析完整文档
    # example_analyze_full_document()

    # 示例4: 只提取章节标题（不调用 API）
    # example_extract_sections_only()

    print("\n" + "=" * 80)
    print("所有示例执行完成!")
    print("=" * 80)