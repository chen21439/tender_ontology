"""
Docling 文档推理脚本

直接运行此脚本进行文档解析，生成 Markdown、JSON、Labeled JSON 等格式
"""

import argparse
from pathlib import Path

from tender_ontology.services.docling import DoclingInferenceService

# ============ 默认配置区域 ============
# DEFAULT_FILE = r"E:\programFile\AIProgram\modelTrain\HRDoc\pdf\深圳市大数据服务中心.pdf"
DEFAULT_FILE = r"E:\programFile\AIProgram\modelTrain\CompHRDoc\data\pdf\城市大数据中心物业管理服务.pdf"
# DEFAULT_FILE = r"E:\path\to\your\document.docx"  # DOCX 示例
DEFAULT_OUTPUT_DIR = None  # None 表示使用配置文件中的路径
# ======================================


def main():
    parser = argparse.ArgumentParser(
        description="Docling 文档推理工具 - 支持快速初筛和精细处理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用场景和最佳实践:

默认模式（快速初筛，推荐）⚡：
  python -m tender_ontology.scripts.run_docling_inference --file doc.pdf

  输出: Markdown + JSON + Labeled JSON (不含表格)
  特点: 速度快 5-10 倍，适合大量文档批处理
  原理: 禁用表格识别，labeled JSON 转换跳过表格处理

精细处理模式（需要表格）🎯：
  python -m tender_ontology.scripts.run_docling_inference --file doc.pdf \\
      --enable-table-recognition

  输出: Markdown + JSON + Labeled JSON (含 HTML 表格)
  特点: 完整表格识别，适合少量重要文档

其他场景:
  # 只要 Markdown
  python -m tender_ontology.scripts.run_docling_inference --file doc.pdf \\
      --no-json --no-labeled

  # 只要结构化数据（JSON + Labeled）
  python -m tender_ontology.scripts.run_docling_inference --file doc.pdf \\
      --no-markdown

  # 完整处理（所有格式 + doctags）
  python -m tender_ontology.scripts.run_docling_inference --file doc.pdf \\
      --enable-table-recognition --doctags

性能说明:
  - JSON 导出（含 bbox）：几乎无额外开销 (<5%)
  - Labeled JSON 转换：纯内存操作，很快 (<5%)
  - 表格识别：主要性能瓶颈 (60-80% 的时间)

  结论: 快速模式可以放心生成所有格式（Markdown + JSON + Labeled），
        只是禁用表格识别而已！
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
        "--online",
        action="store_true",
        help="启用在线模式（默认：离线模式，不检测模型更新）"
    )

    parser.add_argument(
        "--enable-table-recognition",
        action="store_true",
        help="启用表格识别（精细模式，默认：禁用）"
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

    # 默认禁用表格识别（快速模式），除非明确启用
    disable_table_recognition = not args.enable_table_recognition

    # 默认启用离线模式（不检测模型更新），除非明确启用在线模式
    offline_mode = not args.online

    # 创建推理服务
    service = DoclingInferenceService(
        output_dir=Path(args.output_dir) if args.output_dir else None,
        offline_mode=offline_mode,
        disable_table_recognition=disable_table_recognition,
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