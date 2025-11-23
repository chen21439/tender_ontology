"""
文档层级分析脚本

使用大模型 API 对 labeled JSON 进行语义层级分析，构建文档目录树
"""

import argparse
import json
from pathlib import Path

from tender_ontology.services.docling import HierarchyAnalyzer
from tender_ontology.config.docling_settings import docling_settings


def main():
    parser = argparse.ArgumentParser(
        description="文档层级分析工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 分析 labeled JSON 文件
  python -m tender_ontology.scripts.run_hierarchy_analysis --file document_labeled.json

  # 指定输出路径
  python -m tender_ontology.scripts.run_hierarchy_analysis --file document_labeled.json --output result.json

  # 使用自定义 API 配置
  python -m tender_ontology.scripts.run_hierarchy_analysis --file document_labeled.json --api-key sk-xxx --model gpt-4
        """
    )

    parser.add_argument(
        "--file",
        "-f",
        type=str,
        required=True,
        help="输入的 labeled JSON 文件路径"
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="输出文件路径（默认保存到配置的 hierarchy_output_dir）"
    )

    parser.add_argument(
        "--api-key",
        type=str,
        help="LLM API 密钥（默认使用配置文件中的值）"
    )

    parser.add_argument(
        "--api-base",
        type=str,
        help="LLM API 基础 URL（默认使用配置文件中的值）"
    )

    parser.add_argument(
        "--model",
        type=str,
        help="LLM 模型名称（默认使用配置文件中的值）"
    )

    parser.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="采样温度（0-1，默认 0.1）"
    )

    args = parser.parse_args()

    # 验证文件存在
    input_path = Path(args.file)
    if not input_path.exists():
        print(f"❌ 错误: 文件不存在: {input_path}")
        return 1

    # 读取 labeled JSON
    try:
        with open(input_path, encoding='utf-8') as f:
            labeled_data = json.load(f)
    except Exception as e:
        print(f"❌ 读取文件失败: {e}")
        return 1

    # 确定输出路径
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = (
            docling_settings.hierarchy_output_dir
            / f"{input_path.stem}_hierarchy.json"
        )

    # 创建分析器
    try:
        analyzer = HierarchyAnalyzer(
            api_key=args.api_key,
            api_base=args.api_base,
            model=args.model
        )
    except ValueError as e:
        print(f"❌ 初始化失败: {e}")
        print("请设置环境变量 DOCLING_LLM_API_KEY 或使用 --api-key 参数")
        return 1

    # 执行分析
    try:
        result = analyzer.analyze_and_save(
            labeled_data=labeled_data,
            output_path=output_path
        )

        # 显示摘要
        summary = result.get("summary", {})
        print("\n📊 分析结果:")
        print(f"  - 总标题数: {summary.get('total', 0)}")
        print(f"  - 层级分布: {summary.get('distribution', {})}")
        print(f"  - 置信度: {summary.get('confidence', 'unknown')}")

        if summary.get('notes'):
            print(f"  - 备注:")
            for note in summary['notes']:
                print(f"    • {note}")

        print(f"\n💾 结果已保存: {output_path}")

        return 0

    except Exception as e:
        print(f"❌ 分析失败: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
