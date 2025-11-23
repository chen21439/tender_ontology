"""
完整文档处理流程脚本

一键执行文档解析 + 层级分析
"""

import argparse
import json
from pathlib import Path

from tender_ontology.services.docling import DoclingInferenceService, HierarchyAnalyzer


def main():
    parser = argparse.ArgumentParser(
        description="完整文档处理流程（解析 + 层级分析）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 处理 PDF 文件（解析 + 层级分析）
  python -m tender_ontology.scripts.run_full_pipeline --file document.pdf

  # 只进行解析，不做层级分析
  python -m tender_ontology.scripts.run_full_pipeline --file document.pdf --no-hierarchy

  # 使用自定义 LLM API
  python -m tender_ontology.scripts.run_full_pipeline --file document.pdf --api-key sk-xxx
        """
    )

    parser.add_argument(
        "--file",
        "-f",
        type=str,
        required=True,
        help="输入文件路径（PDF 或 DOCX）"
    )

    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        help="输出目录（默认使用配置文件中的路径）"
    )

    parser.add_argument(
        "--no-hierarchy",
        action="store_true",
        help="不进行层级分析"
    )

    parser.add_argument(
        "--offline",
        action="store_true",
        help="启用离线模式"
    )

    parser.add_argument(
        "--api-key",
        type=str,
        help="LLM API 密钥（层级分析用）"
    )

    parser.add_argument(
        "--api-base",
        type=str,
        help="LLM API 基础 URL"
    )

    parser.add_argument(
        "--model",
        type=str,
        help="LLM 模型名称"
    )

    args = parser.parse_args()

    # 验证文件存在
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"❌ 错误: 文件不存在: {file_path}")
        return 1

    print("="*80)
    print("🚀 完整文档处理流程")
    print("="*80)

    # ===== 步骤 1: 文档解析 =====
    print("\n[步骤 1/2] 文档解析...")
    service = DoclingInferenceService(
        output_dir=Path(args.output_dir) if args.output_dir else None,
        offline_mode=args.offline
    )

    try:
        parse_results = service.infer(
            file_path=file_path,
            save_markdown=True,
            save_json=True,
            save_labeled=True,
            save_doctags=False
        )
    except Exception as e:
        print(f"❌ 文档解析失败: {e}")
        return 1

    # ===== 步骤 2: 层级分析 =====
    if not args.no_hierarchy and parse_results.get("labeled_path"):
        print("\n[步骤 2/2] 层级分析...")

        labeled_path = Path(parse_results["labeled_path"])

        try:
            # 读取 labeled JSON
            with open(labeled_path, encoding='utf-8') as f:
                labeled_data = json.load(f)

            # 创建分析器
            analyzer = HierarchyAnalyzer(
                api_key=args.api_key,
                api_base=args.api_base,
                model=args.model
            )

            # 确定输出路径
            from tender_ontology.config.docling_settings import docling_settings
            hierarchy_output_path = (
                docling_settings.hierarchy_output_dir
                / f"{labeled_path.stem}_hierarchy.json"
            )

            # 执行分析
            hierarchy_result = analyzer.analyze_and_save(
                labeled_data=labeled_data,
                output_path=hierarchy_output_path
            )

            # 显示摘要
            summary = hierarchy_result.get("summary", {})
            print(f"\n📊 层级分析结果:")
            print(f"  - 总标题数: {summary.get('total', 0)}")
            print(f"  - 层级分布: {summary.get('distribution', {})}")
            print(f"  - 置信度: {summary.get('confidence', 'unknown')}")

            parse_results["hierarchy_path"] = str(hierarchy_output_path)

        except ValueError as e:
            print(f"⚠️  跳过层级分析: {e}")
            print("   请设置环境变量 DOCLING_LLM_API_KEY 或使用 --api-key 参数")
        except Exception as e:
            print(f"⚠️  层级分析失败: {e}")
    else:
        print("\n[步骤 2/2] 跳过层级分析")

    # ===== 完成 =====
    print("\n" + "="*80)
    print("✅ 处理完成!")
    print("="*80)
    print("\n📋 生成文件:")
    for key, path in parse_results.items():
        if key.endswith("_path") and path:
            print(f"  - {Path(path).name}")
    print()

    return 0


if __name__ == "__main__":
    exit(main())