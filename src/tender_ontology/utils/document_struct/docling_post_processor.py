"""
Docling 后处理工具类 - 基于 docling-hierarchical-pdf 的层级修正

功能：
1. 从 PDF 元数据（TOC）提取层级结构
2. 基于样式和编号推断层级结构
3. 自动修正 Docling 的文档层级
4. 将 TextItem 和 SectionHeaderItem 相互转换

依赖：
- docling-hierarchical-pdf（需要将其复制到项目中）
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
from io import BytesIO
import json

# 添加 docling-hierarchical-pdf 到 Python 路径
HIERARCHICAL_PDF_DIR = Path(__file__).resolve().parents[5] / "docling-hierarchical-pdf-main"
if HIERARCHICAL_PDF_DIR.exists():
    sys.path.insert(0, str(HIERARCHICAL_PDF_DIR))


class DoclingPostProcessor:
    """
    Docling 后处理器 - 层级修正和结构优化

    使用 docling-hierarchical-pdf 的算法对 Docling 转换结果进行层级修正
    """

    def __init__(
        self,
        raise_on_error: bool = False,
        debug: bool = False
    ):
        """
        初始化后处理器

        Args:
            raise_on_error: 是否在错误时抛出异常（False 时仅打印警告）
            debug: 是否启用调试输出
        """
        self.raise_on_error = raise_on_error
        self.debug = debug

        # 动态导入 hierarchical 模块
        try:
            from hierarchical.postprocessor import ResultPostprocessor
            from hierarchical.hierarchy_builder import create_toc
            from hierarchical.hierarchy_builder_metadata import HierarchyBuilderMetadata
            from hierarchical.types.hierarchical_header import HierarchicalHeader

            self.ResultPostprocessor = ResultPostprocessor
            self.create_toc = create_toc
            self.HierarchyBuilderMetadata = HierarchyBuilderMetadata
            self.HierarchicalHeader = HierarchicalHeader

            self._available = True

        except ImportError as e:
            print(f"⚠️  无法导入 hierarchical 模块: {e}")
            print(f"   请确保 docling-hierarchical-pdf 在以下路径: {HIERARCHICAL_PDF_DIR}")
            self._available = False

    def is_available(self) -> bool:
        """检查 hierarchical 模块是否可用"""
        return self._available

    def process_result(
        self,
        result,  # ConversionResult from docling
        source: Optional[Union[str, Path, BytesIO]] = None
    ) -> None:
        """
        处理 Docling 转换结果，修正层级结构

        Args:
            result: Docling ConversionResult 对象
            source: PDF 源文件路径或字节流（用于提取 TOC）
                   - None: 使用 result.input.file
                   - str/Path: 文件路径
                   - BytesIO: 字节流

        Raises:
            ImportError: hierarchical 模块不可用
            Exception: 处理失败（仅当 raise_on_error=True）
        """
        if not self._available:
            raise ImportError("hierarchical 模块不可用，无法进行层级修正")

        try:
            if self.debug:
                print("\n" + "="*80)
                print("🔧 Docling 层级修正")
                print("="*80)

            # 调用 ResultPostprocessor
            processor = self.ResultPostprocessor(
                result=result,
                source=source,
                raise_on_error=self.raise_on_error
            )

            processor.process()

            if self.debug:
                print("✅ 层级修正完成")
                print("="*80 + "\n")

        except Exception as e:
            if self.raise_on_error:
                raise
            else:
                print(f"⚠️  层级修正失败: {e}")

    def extract_toc_from_pdf(
        self,
        result,  # ConversionResult
        source: Optional[Union[str, Path, BytesIO]] = None
    ) -> List[tuple]:
        """
        从 PDF 中提取目录（TOC）

        Args:
            result: Docling ConversionResult 对象
            source: PDF 源文件路径或字节流

        Returns:
            目录列表，每个元素为 (level, title, page, add_info) 元组
        """
        if not self._available:
            raise ImportError("hierarchical 模块不可用")

        try:
            builder = self.HierarchyBuilderMetadata(
                conv_res=result,
                source=source,
                raise_on_error=self.raise_on_error
            )

            toc = builder.toc

            if self.debug:
                print(f"📑 从 PDF 提取到 {len(toc)} 个目录项")
                for level, title, page, _ in toc[:5]:  # 打印前5个
                    print(f"   {'  ' * (level-1)}[H{level}] {title} (第{page}页)")
                if len(toc) > 5:
                    print(f"   ... 还有 {len(toc)-5} 个")

            return toc

        except Exception as e:
            if self.raise_on_error:
                raise
            else:
                print(f"⚠️  TOC 提取失败: {e}")
                return []

    def infer_hierarchy_from_metadata(
        self,
        result,  # ConversionResult
        source: Optional[Union[str, Path, BytesIO]] = None
    ) -> Optional['HierarchicalHeader']:
        """
        从 PDF 元数据推断层级结构

        Args:
            result: Docling ConversionResult 对象
            source: PDF 源文件路径或字节流

        Returns:
            层级树根节点（HierarchicalHeader），如果失败返回 None
        """
        if not self._available:
            raise ImportError("hierarchical 模块不可用")

        try:
            builder = self.HierarchyBuilderMetadata(
                conv_res=result,
                source=source,
                raise_on_error=self.raise_on_error
            )

            root = builder.infer()

            if self.debug:
                print("🌳 从 PDF 元数据构建层级树:")
                print(str(root))

            return root

        except Exception as e:
            if self.raise_on_error:
                raise
            else:
                print(f"⚠️  从元数据推断层级失败: {e}")
                return None

    def infer_hierarchy_from_style(
        self,
        headings: List[Dict[str, Any]]
    ) -> Optional['HierarchicalHeader']:
        """
        从标题样式推断层级结构（基于编号和字体）

        Args:
            headings: 标题列表，每个元素包含：
                - text: 标题文本
                - font_size: 字体大小
                - is_bold: 是否粗体
                - is_italic: 是否斜体
                - reference (可选): 文档引用

        Returns:
            层级树根节点（HierarchicalHeader），如果失败返回 None
        """
        if not self._available:
            raise ImportError("hierarchical 模块不可用")

        try:
            root = self.create_toc(headings)

            if self.debug:
                print("🌳 从样式构建层级树:")
                print(str(root))

            return root

        except Exception as e:
            if self.raise_on_error:
                raise
            else:
                print(f"⚠️  从样式推断层级失败: {e}")
                return None

    def extract_headers_from_result(
        self,
        result  # ConversionResult
    ) -> List[Dict[str, Any]]:
        """
        从 Docling 转换结果中提取标题信息（用于样式推断）

        Args:
            result: Docling ConversionResult 对象

        Returns:
            标题列表，每个元素包含 text, font_size, is_bold, is_italic, reference
        """
        headers = []

        try:
            for item, _ in result.document.iterate_items():
                # 只处理 SectionHeaderItem
                if item.__class__.__name__ != 'SectionHeaderItem':
                    continue

                # 提取第一个 prov 的信息
                if not item.prov or len(item.prov) == 0:
                    continue

                prov = item.prov[0]
                page_no = prov.page_no

                # 尝试从 layout 获取详细样式信息
                page = result.pages[page_no - 1]
                font_size = prov.bbox.height  # 默认使用 bbox 高度
                is_bold = False
                is_italic = False

                if page.predictions.layout:
                    for cluster in page.predictions.layout.clusters:
                        if not cluster or cluster.label != "section_header":
                            continue

                        first_cell = cluster.cells[0] if cluster.cells else None
                        if first_cell and page.size:
                            # 检查 bbox 是否匹配
                            cell_bbox = first_cell.rect.to_bounding_box().to_bottom_left_origin(
                                page_height=page.size.height
                            )
                            if prov.bbox.intersection_area_with(cell_bbox) > 0:
                                font_size = first_cell.rect.height
                                if hasattr(first_cell, 'font_name'):
                                    font_split = first_cell.font_name.split("-")
                                    if len(font_split) > 1:
                                        is_bold = "Bold" in font_split[1]
                                        is_italic = "Italic" in font_split[1]
                                break

                headers.append({
                    "text": " ".join(item.text.split("\n")),
                    "font_size": font_size,
                    "is_bold": is_bold,
                    "is_italic": is_italic,
                    "reference": item.self_ref
                })

            if self.debug:
                print(f"📋 提取到 {len(headers)} 个标题")
                for i, h in enumerate(headers[:3]):
                    print(f"   [{i}] {h['text'][:50]} (size={h['font_size']:.1f})")
                if len(headers) > 3:
                    print(f"   ... 还有 {len(headers)-3} 个")

        except Exception as e:
            print(f"⚠️  提取标题失败: {e}")

        return headers

    def export_hierarchy_to_json(
        self,
        root: 'HierarchicalHeader',
        output_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        将层级树导出为 JSON 格式

        Args:
            root: 层级树根节点
            output_path: 输出文件路径（可选）

        Returns:
            层级树的 JSON 表示
        """
        def node_to_dict(node: 'HierarchicalHeader') -> Dict[str, Any]:
            """递归转换节点为字典"""
            result = {}

            if node.text:
                result["text"] = node.text

            if node.index is not None:
                result["index"] = node.index

            if node.level_toc is not None:
                result["level_toc"] = node.level_toc

            if node.level_fontsize is not None:
                result["level_fontsize"] = node.level_fontsize

            if node.level_numerical:
                result["level_numerical"] = node.level_numerical

            if node.level_alpha:
                result["level_alpha"] = node.level_alpha

            if node.level_latin:
                result["level_latin"] = node.level_latin

            if node.doc_ref:
                result["doc_ref"] = node.doc_ref

            if node.children:
                result["children"] = [node_to_dict(child) for child in node.children]

            return result

        hierarchy_json = node_to_dict(root)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(hierarchy_json, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            if self.debug:
                print(f"💾 层级树已保存: {output_path}")

        return hierarchy_json


def process_docling_result_with_hierarchy(
    result,
    source: Optional[Union[str, Path, BytesIO]] = None,
    raise_on_error: bool = False,
    debug: bool = False
) -> None:
    """
    便捷函数：对 Docling 结果进行层级修正

    Args:
        result: Docling ConversionResult 对象
        source: PDF 源文件路径或字节流
        raise_on_error: 是否在错误时抛出异常
        debug: 是否启用调试输出

    Example:
        from docling.document_converter import DocumentConverter
        from tender_ontology.utils.document_struct.docling_post_processor import process_docling_result_with_hierarchy

        converter = DocumentConverter()
        result = converter.convert("document.pdf")

        # 层级修正
        process_docling_result_with_hierarchy(result, source="document.pdf", debug=True)

        # 现在 result.document 包含修正后的层级结构
    """
    processor = DoclingPostProcessor(raise_on_error=raise_on_error, debug=debug)

    if not processor.is_available():
        print("⚠️  hierarchical 模块不可用，跳过层级修正")
        return

    processor.process_result(result, source=source)
