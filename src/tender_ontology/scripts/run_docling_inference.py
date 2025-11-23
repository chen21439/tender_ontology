"""
Docling 文档推理脚本

直接运行此脚本进行文档解析，生成 Markdown、JSON、Labeled JSON 等格式
"""

import argparse
from pathlib import Path

from tender_ontology.services.docling import DoclingInferenceService

# ============ 默认配置区域 ============
DEFAULT_FILE = r"E:\programFile\AIProgram\modelTrain\HRDoc\pdf\深圳市大数据服务中心.pdf"
# DEFAULT_FILE = r"E:\path\to\your\document.docx"  # DOCX 示例
DEFAULT_OUTPUT_DIR = None  # None 表示使用配置文件中的路径
# ======================================


def main():
    parser = argparse.ArgumentParser(
        description="Docling 文档推理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 直接运行（使用默认文件路径）
  python -m tender_ontology.scripts.run_docling_inference

  # 解析指定 PDF 文件
  python -m tender_ontology.scripts.run_docling_inference --file document.pdf

  # 解析 DOCX 文件，只生成 Markdown
  python -m tender_ontology.scripts.run_docling_inference --file document.docx --no-json --no-labeled

  # 解析并生成所有格式（包括 doctags）
  python -m tender_ontology.scripts.run_docling_inference --file document.pdf --doctags
        """
    )

    parser.add_argument(
        "--file",
        "-f",
        type=str,
        default=DEFAULT_FILE,
        help=f"输入文件路径（PDF 或 DOCX），默认: {DEFAULT_FILE}"
    )

    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        help="输出目录（默认使用配置文件中的路径）"
    )

    parser.add_argument(
        "--no-markdown",
        action="store_true",
        help="不生成 Markdown 文件"
    )

    parser.add_argument(
        "--no-json",
        action="store_true",
        help="不生成完整 JSON 文件"
    )

    parser.add_argument(
        "--no-labeled",
        action="store_true",
        help="不生成 labeled JSON 文件"
    )

    parser.add_argument(
        "--doctags",
        action="store_true",
        help="生成 doctags 文件"
    )

    parser.add_argument(
        "--offline",
        action="store_true",
        help="启用离线模式"
    )

    parser.add_argument(
        "--no-table-recognition",
        action="store_true",
        help="禁用表格识别"
    )

    parser.add_argument(
        "--hierarchy-refinement",
        action="store_true",
        help="启用层级修正（需要安装 docling-hierarchical-pdf）"
    )

    args = parser.parse_args()

    # 验证文件存在
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"❌ 错误: 文件不存在: {file_path}")
        return 1

    # 创建推理服务
    service = DoclingInferenceService(
        output_dir=Path(args.output_dir) if args.output_dir else None,
        offline_mode=args.offline,
        disable_table_recognition=args.no_table_recognition,
        hierarchy_refinement=args.hierarchy_refinement
    )

    # 执行推理
    try:
        results = service.infer(
            file_path=file_path,
            save_markdown=not args.no_markdown,
            save_json=not args.no_json,
            save_labeled=not args.no_labeled,
            save_doctags=args.doctags
        )

        print("\n📋 生成文件列表:")
        for key, path in results.items():
            if key.endswith("_path") and path:
                print(f"  - {Path(path).name}")

        return 0

    except Exception as e:
        print(f"❌ 推理失败: {e}")
        return 1


if __name__ == "__main__":
    exit(main())