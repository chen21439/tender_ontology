"""
Docling 文档推理服务

提供 PDF/DOCX 文档的结构化推理功能
"""

import os
import time
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Union

from tender_ontology.config.docling_settings import docling_settings
from .converter import LabeledJsonConverter


class DoclingInferenceService:
    """Docling 文档推理服务"""

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        offline_mode: Optional[bool] = None,
        disable_table_recognition: Optional[bool] = None,
        hierarchy_refinement: Optional[bool] = None
    ):
        """
        初始化推理服务

        Args:
            output_dir: 输出目录，默认使用配置中的路径
            offline_mode: 是否离线模式
            disable_table_recognition: 是否禁用表格识别
            hierarchy_refinement: 是否启用层级修正
        """
        self.output_dir = output_dir or docling_settings.output_base_dir
        self.offline_mode = offline_mode if offline_mode is not None else docling_settings.offline_mode
        self.disable_table_recognition = (
            disable_table_recognition
            if disable_table_recognition is not None
            else docling_settings.disable_table_recognition
        )
        self.hierarchy_refinement = (
            hierarchy_refinement
            if hierarchy_refinement is not None
            else docling_settings.hierarchy_refinement
        )

        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 设置离线模式
        if self.offline_mode:
            os.environ["HF_HUB_OFFLINE"] = "1"

    def infer(
        self,
        file_path: Union[str, Path],
        save_markdown: bool = True,
        save_json: bool = True,
        save_labeled: bool = True,
        save_doctags: bool = False
    ) -> Dict[str, Any]:
        """
        对文档进行推理

        Args:
            file_path: 文件路径 (PDF 或 DOCX)
            save_markdown: 是否保存 Markdown
            save_json: 是否保存完整 JSON
            save_labeled: 是否保存 labeled JSON
            save_doctags: 是否保存 doctags

        Returns:
            包含推理结果和文件路径的字典
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 检测文件类型
        file_ext = file_path.suffix.lower()
        is_pdf = file_ext == ".pdf"
        is_docx = file_ext in [".docx", ".doc"]

        if not (is_pdf or is_docx):
            raise ValueError(f"不支持的文件格式: {file_ext}")

        print(f"\n{'='*80}")
        print(f"🚀 Docling {'PDF' if is_pdf else 'DOCX'} 推理")
        print(f"{'='*80}")
        print(f"输入文件: {file_path}")
        print(f"离线模式: {self.offline_mode}")
        if is_pdf:
            print(f"表格识别: {'❌ 已关闭' if self.disable_table_recognition else '✅ 已启用'}")

        # 导入 docling 依赖
        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.datamodel.base_models import InputFormat
            from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
        except ImportError as e:
            raise ImportError(f"docling 未安装: {e}. 请运行: poetry add docling")

        # 创建转换器
        print("\n[1/3] 初始化 DocumentConverter...")
        if is_pdf:
            opts = PdfPipelineOptions(
                do_ocr=False,
                do_table_structure=not self.disable_table_recognition,
                generate_page_images=False,
                generate_picture_images=False,
                generate_table_images=False
            )
            converter = DocumentConverter(
                allowed_formats=[InputFormat.PDF],
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=opts,
                        backend=PyPdfiumDocumentBackend
                    )
                }
            )
        else:
            converter = DocumentConverter(allowed_formats=[InputFormat.DOCX])

        # 执行转换
        print(f"[2/3] 正在提取{'PDF' if is_pdf else 'DOCX'}文档结构...")
        start_time = time.time()
        result = converter.convert(source=str(file_path))
        inference_time = time.time() - start_time

        # 层级修正（可选）
        if self.hierarchy_refinement and is_pdf:
            print("      🔁 正在进行标题层级修正...")
            try:
                from hierarchical.postprocessor import ResultPostprocessor
                ResultPostprocessor(result, source=str(file_path)).process()
                print("      ✅ 标题层级修正完成")
            except ImportError:
                print("      ⚠️  docling-hierarchical-pdf 未安装，跳过层级修正")
            except Exception as e:
                print(f"      ⚠️  层级修正失败: {e}")

        doc = result.document

        # 保存结果
        print("[3/3] 保存结果...")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        doc_name = file_path.stem

        results = {
            "document_name": doc_name,
            "inference_time": inference_time,
            "timestamp": timestamp
        }

        # 1. Markdown
        if save_markdown:
            md_path = self.output_dir / f"{doc_name}_{timestamp}.md"
            md_path.write_text(doc.export_to_markdown(), encoding='utf-8')
            results["markdown_path"] = str(md_path)
            print(f"  ✅ Markdown 已保存: {md_path.name}")

        # 2. 完整 JSON
        json_data = None
        if save_json or save_labeled:
            json_path = self.output_dir / f"{doc_name}_{timestamp}.json"

            if hasattr(doc, 'export_to_json'):
                json_content = doc.export_to_json()
                json_data = json.loads(json_content)
            else:
                from pydantic import BaseModel

                def json_serializer(obj):
                    if hasattr(obj, '__str__') and type(obj).__name__ == 'AnyUrl':
                        return str(obj)
                    if isinstance(obj, BaseModel):
                        return obj.model_dump()
                    return str(obj)

                json_data = doc.model_dump()
                json_content = json.dumps(json_data, ensure_ascii=False, indent=2, default=json_serializer)

            if save_json:
                json_path.write_text(json_content, encoding='utf-8')
                results["json_path"] = str(json_path)
                print(f"  ✅ JSON 已保存: {json_path.name}")

        # 3. Labeled JSON
        if save_labeled and json_data:
            labeled_path = self.output_dir / f"{doc_name}_{timestamp}_labeled.json"
            converter = LabeledJsonConverter(debug=False)
            converter.convert_and_save(json_data, labeled_path)
            results["labeled_path"] = str(labeled_path)
            print(f"  ✅ Labeled JSON 已保存: {labeled_path.name}")

        # 4. Doctags
        if save_doctags:
            doctags_path = self.output_dir / f"{doc_name}_{timestamp}.doctags"
            doctags_content = doc.export_to_doctags()
            doctags_path.write_text(doctags_content, encoding='utf-8')
            results["doctags_path"] = str(doctags_path)
            print(f"  ✅ Doctags 已保存: {doctags_path.name}")

        print(f"\n✅ 推理完成! 耗时: {inference_time:.2f} 秒")
        print(f"{'='*80}\n")

        return results