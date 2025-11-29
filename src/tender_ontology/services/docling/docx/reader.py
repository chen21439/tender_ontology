"""
DocxReader - 使用 docling 读取 DOCX 文件

功能：
1. 按阅读顺序遍历文档（从上到下）
2. 提取文本段落和表格
3. 输出为 TXT 格式保存

结论：
- 同一份 DOCX 用同一版本的 docling、同样配置解析，结果是确定的（基本一致）
- docling 内部是按版面/阅读顺序抽取的
- 推荐思路：先"整份文档 → 统一结构"（DoclingDocument），再按需要拿 texts/tables/body 做业务逻辑
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import time


class DocxReader:
    """使用 docling 读取 DOCX 文件"""

    def __init__(self, debug: bool = False):
        """
        初始化 DOCX 阅读器

        Args:
            debug: 是否启用调试输出
        """
        self.debug = debug
        self._converter = None

    def _get_converter(self):
        """懒加载 DocumentConverter"""
        if self._converter is None:
            from docling.document_converter import DocumentConverter
            self._converter = DocumentConverter()
        return self._converter

    def read(self, docx_path: str | Path) -> Dict[str, Any]:
        """
        读取 DOCX 文件，返回结构化数据

        Args:
            docx_path: DOCX 文件路径

        Returns:
            包含文档内容的字典：
            {
                "file_name": "xxx.docx",
                "total_items": 10,
                "items": [
                    {"type": "text", "label": "paragraph", "content": "..."},
                    {"type": "table", "rows": [[...], [...]]},
                    ...
                ]
            }
        """
        docx_path = Path(docx_path)
        if not docx_path.exists():
            raise FileNotFoundError(f"文件不存在: {docx_path}")

        if self.debug:
            print(f"[DocxReader] 开始读取: {docx_path.name}")

        # 使用 docling 转换（带计时）
        convert_start = time.time()
        converter = self._get_converter()
        result = converter.convert(str(docx_path))
        doc = result.document
        convert_elapsed = time.time() - convert_start

        if self.debug:
            print(f"[DocxReader] 转换完成，耗时: {convert_elapsed:.2f}秒")
            print(f"[DocxReader] doc.texts 数量: {len(doc.texts) if hasattr(doc, 'texts') else 'N/A'}")
            print(f"[DocxReader] doc.tables 数量: {len(doc.tables) if hasattr(doc, 'tables') else 'N/A'}")

        # 方式1：直接从 texts 获取（更可靠）
        items = []

        # 提取文本
        if hasattr(doc, "texts") and doc.texts:
            for text_item in doc.texts:
                label = getattr(text_item, "label", "text")
                text = getattr(text_item, "text", "")
                if text.strip():
                    items.append({
                        "type": "text",
                        "label": str(label) if label else "text",
                        "content": text
                    })

        # 提取表格
        if hasattr(doc, "tables") and doc.tables:
            for table_item in doc.tables:
                table_data = self._extract_table(table_item)
                if table_data:
                    items.append({
                        "type": "table",
                        "rows": table_data
                    })

        if self.debug:
            print(f"[DocxReader] 读取完成，共 {len(items)} 个元素")

        return {
            "file_name": docx_path.name,
            "total_items": len(items),
            "items": items
        }

    def _walk_body(self, node, items: List[Dict], doc) -> None:
        """
        递归遍历 body 树，提取文本和表格

        Args:
            node: 当前节点
            items: 结果列表（会被修改）
            doc: DoclingDocument 对象
        """
        # 获取节点引用的具体 item
        if hasattr(node, "item_ref") and node.item_ref is not None:
            item_ref = node.item_ref
            class_name = item_ref.__class__.__name__

            if class_name == "TextItem" or hasattr(item_ref, "text"):
                # 文本类型
                label = getattr(item_ref, "label", "text")
                text = getattr(item_ref, "text", "")
                if text.strip():  # 跳过空文本
                    items.append({
                        "type": "text",
                        "label": str(label) if label else "text",
                        "content": text
                    })

            elif class_name == "TableItem" or hasattr(item_ref, "data"):
                # 表格类型
                table_data = self._extract_table(item_ref)
                if table_data:
                    items.append({
                        "type": "table",
                        "rows": table_data
                    })

        # 递归处理子节点
        children = getattr(node, "children", None)
        if children:
            for child in children:
                self._walk_body(child, items, doc)

    def _extract_table(self, table_item) -> List[List[str]]:
        """
        提取表格数据

        Args:
            table_item: 表格对象

        Returns:
            二维数组，每行是一个字符串列表
        """
        rows = []
        try:
            data = getattr(table_item, "data", None)
            if data is None:
                return rows

            # 尝试不同的表格数据结构
            grid = getattr(data, "grid", None)
            if grid:
                for row in grid:
                    row_cells = []
                    for cell in row:
                        cell_text = getattr(cell, "text", "")
                        row_cells.append(cell_text)
                    rows.append(row_cells)
            else:
                # 尝试 rows 属性
                data_rows = getattr(data, "rows", None)
                if data_rows:
                    for row in data_rows:
                        cells = getattr(row, "cells", [])
                        row_cells = [getattr(c, "text", "") for c in cells]
                        rows.append(row_cells)
        except Exception as e:
            if self.debug:
                print(f"[DocxReader] 提取表格失败: {e}")

        return rows

    def read_to_fulltext(self, docx_path: str | Path) -> List[Dict[str, Any]]:
        """
        读取 DOCX 文件，输出与 PDF fulltext.json 兼容的格式

        Args:
            docx_path: DOCX 文件路径

        Returns:
            与 PDF fulltext.json 格式兼容的列表：
            [
                {"text": "...", "label": "section_header", "prov": [{"page_no": 1}]},
                {"text": "...", "label": "paragraph", "prov": [{"page_no": 1}]},
                ...
            ]
        """
        result = self.read(docx_path)
        fulltext_items = []

        for item in result["items"]:
            if item["type"] == "text":
                # 转换 label 格式
                label = item.get("label", "").lower()
                if "section_header" in label:
                    normalized_label = "section_header"
                elif "title" in label:
                    normalized_label = "title"
                elif "list_item" in label:
                    normalized_label = "list_item"
                else:
                    normalized_label = "paragraph"

                fulltext_items.append({
                    "text": item["content"],
                    "label": normalized_label,
                    "prov": [{"page_no": 1}]  # DOCX 没有页码，统一设为1
                })

            elif item["type"] == "table":
                # 表格转为文本表示
                table_text = self._table_to_text(item["rows"])
                fulltext_items.append({
                    "text": table_text,
                    "label": "table",
                    "prov": [{"page_no": 1}]
                })

        return fulltext_items

    def _table_to_text(self, rows: List[List[str]]) -> str:
        """将表格转为文本表示"""
        lines = []
        for row in rows:
            lines.append(" | ".join(row))
        return "\n".join(lines)

    def generate_auxiliary_files(
        self,
        docx_path: str | Path,
        output_dir: Path
    ) -> Dict[str, Path]:
        """
        生成模型调用所需的辅助文件（与 PDF 流程兼容）

        Args:
            docx_path: DOCX 文件路径
            output_dir: 输出目录

        Returns:
            生成的文件路径字典：
            {
                "fulltext_path": Path,
                "header_only_path": Path,
                "title_md_path": Path
            }
        """
        import json

        docx_path = Path(docx_path)
        base_name = docx_path.stem

        # 1. 读取并生成 fulltext 格式数据
        fulltext_data = self.read_to_fulltext(docx_path)

        # 2. 保存 _docx_fulltext.json
        fulltext_path = output_dir / f"{base_name}_docx_fulltext.json"
        fulltext_path.write_text(
            json.dumps(fulltext_data, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        if self.debug:
            print(f"[DocxReader] 已保存: {fulltext_path.name}")

        # 3. 生成 _docx_sectionHeader_only.md（仅标题）
        header_lines = []
        for item in fulltext_data:
            if item["label"] == "section_header":
                header_lines.append(item["text"])

        header_only_path = output_dir / f"{base_name}_docx_sectionHeader_only.md"
        header_only_path.write_text("\n".join(header_lines), encoding='utf-8')
        if self.debug:
            print(f"[DocxReader] 已保存: {header_only_path.name}（{len(header_lines)} 个标题）")

        # 4. 生成 _docx_title_with_id.md（带 ID 的标题）
        title_lines = []
        header_id = 0
        for item in fulltext_data:
            if item["label"] == "section_header":
                title_lines.append(f"[H{header_id}] {item['text']}")
                header_id += 1

        title_md_path = output_dir / f"{base_name}_docx_title_with_id.md"
        title_md_path.write_text("\n".join(title_lines), encoding='utf-8')
        if self.debug:
            print(f"[DocxReader] 已保存: {title_md_path.name}")

        return {
            "fulltext_path": str(fulltext_path),
            "header_only_path": str(header_only_path),
            "title_md_path": str(title_md_path),
            "header_count": len(header_lines)
        }

    def read_to_text(self, docx_path: str | Path) -> str:
        """
        读取 DOCX 文件并转换为带标签的文本

        Args:
            docx_path: DOCX 文件路径

        Returns:
            带标签的文本内容：
            - 段落: <p pid="序号">内容</p>
            - 章节标题: <p pid="序号" type="section_header">内容</p>
            - 表格: <table><tr><td><p>单元格内容</p></td>...</tr>...</table>
        """
        result = self.read(docx_path)
        lines = []
        pid = 0  # 段落序号

        for item in result["items"]:
            if item["type"] == "text":
                content = item["content"]
                label = item.get("label", "").lower()

                # 判断是否是章节标题
                if "section_header" in label or "title" in label:
                    lines.append(f'<p pid="{pid}" type="section_header">{content}</p>')
                else:
                    lines.append(f'<p pid="{pid}">{content}</p>')
                pid += 1

            elif item["type"] == "table":
                table_lines = ["<table>"]
                for row in item["rows"]:
                    row_cells = []
                    for cell in row:
                        row_cells.append(f"<td><p>{cell}</p></td>")
                    table_lines.append(f"<tr>{''.join(row_cells)}</tr>")
                table_lines.append("</table>")
                lines.append("\n".join(table_lines))

        return "\n".join(lines)

    def read_and_save(
        self,
        docx_path: str | Path,
        output_dir: Optional[str | Path] = None,
        task_id: Optional[str] = None
    ) -> Path:
        """
        读取 DOCX 文件并保存为 TXT

        Args:
            docx_path: DOCX 文件路径
            output_dir: 输出目录（默认为 static/upload/{task_id}/）
            task_id: 任务 ID

        Returns:
            输出文件路径
        """
        docx_path = Path(docx_path)

        # 确定输出目录
        if output_dir:
            output_dir = Path(output_dir)
        elif task_id:
            # 使用 static/upload/{task_id}/ 目录
            project_root = Path(__file__).parent.parent.parent.parent.parent.parent
            output_dir = project_root / "static" / "upload" / task_id
        else:
            output_dir = docx_path.parent

        output_dir.mkdir(parents=True, exist_ok=True)

        # 读取并转换为文本
        text_content = self.read_to_text(docx_path)

        # 生成输出文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = docx_path.stem
        output_path = output_dir / f"{base_name}_{timestamp}.txt"

        # 保存
        output_path.write_text(text_content, encoding="utf-8")

        if self.debug:
            print(f"[DocxReader] 已保存: {output_path}")

        return output_path


def test_docx_reader(task_id: str):
    """
    测试 DOCX 阅读器

    从 static/upload/{task_id}/ 目录中查找 DOCX 文件并读取

    Args:
        task_id: 任务 ID
    """
    print("=" * 60)
    print("[测试] DocxReader DOCX 读取测试")
    print("=" * 60)
    print(f"[测试] 任务 ID: {task_id}")

    # 构建任务目录
    project_root = Path(__file__).parent.parent.parent.parent.parent.parent
    task_dir = project_root / "static" / "upload" / task_id

    print(f"[测试] 任务目录: {task_dir}")

    if not task_dir.exists():
        print(f"[测试] 错误: 目录不存在")
        return None

    # 查找 DOCX 文件
    docx_files = list(task_dir.glob("*.docx"))
    if not docx_files:
        print(f"[测试] 错误: 目录中没有 .docx 文件")
        print(f"[测试] 目录内容: {list(task_dir.glob('*'))[:10]}")
        return None

    docx_path = docx_files[0]
    print(f"[测试] 找到 DOCX 文件: {docx_path.name}")

    reader = DocxReader(debug=True)

    # 读取并保存
    output_path = reader.read_and_save(docx_path, output_dir=task_dir)

    print(f"\n[测试] 输出文件: {output_path}")

    # 显示前 1000 字符
    content = output_path.read_text(encoding="utf-8")
    print(f"\n[测试] 内容预览（前 1000 字符）:")
    print("-" * 40)
    print(content[:1000])
    if len(content) > 1000:
        print(f"\n... 还有 {len(content) - 1000} 字符 ...")
    print("-" * 40)

    return output_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python -m tender_ontology.services.docling.docx.reader <task_id>")
        print("示例: python -m tender_ontology.services.docling.docx.reader 25112810181731940156")
        print("\n会自动从 static/upload/{task_id}/ 目录查找 .docx 文件")
        sys.exit(1)

    task_id = sys.argv[1]
    test_docx_reader(task_id)