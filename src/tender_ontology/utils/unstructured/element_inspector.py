"""
Element 结构检查工具

用于查看 unstructured 解析出的 element 的完整数据结构
"""

import json
from pathlib import Path
from typing import Union, List, Optional
from unstructured.partition.docx import partition_docx


class ElementInspector:
    """Element 结构检查器"""

    def __init__(self, docx_path: Union[str, Path]):
        """
        初始化检查器

        Args:
            docx_path: docx 文件路径
        """
        self.docx_path = Path(docx_path)
        self.elements = None

    def parse(self) -> List:
        """解析 docx 文件"""
        print(f"[ElementInspector] 解析文件: {self.docx_path.name}")
        self.elements = partition_docx(str(self.docx_path))
        print(f"[ElementInspector] 共解析出 {len(self.elements)} 个元素")
        return self.elements

    def inspect_element(self, el, index: int = 0) -> dict:
        """
        检查单个 element 的所有属性

        Args:
            el: unstructured element 对象
            index: 元素索引

        Returns:
            dict: 元素的所有属性
        """
        info = {
            "index": index,
            "type": type(el).__name__,
            "text": (el.text or "")[:200] + ("..." if len(el.text or "") > 200 else ""),
            "text_length": len(el.text or ""),
        }

        # 常用属性
        for attr in ["category", "type", "id", "element_id"]:
            val = getattr(el, attr, None)
            if val is not None:
                info[attr] = val

        # metadata
        if hasattr(el, "metadata"):
            metadata = el.metadata
            metadata_dict = {}

            # 尝试获取 metadata 的各种属性
            metadata_attrs = [
                "filename", "file_directory", "page_number", "last_modified",
                "filetype", "coordinates", "parent_id", "category_depth",
                "text_as_html", "languages", "emphasized_text_contents",
                "emphasized_text_tags", "is_continuation", "detection_class_prob"
            ]

            for attr in metadata_attrs:
                val = getattr(metadata, attr, None)
                if val is not None:
                    # 特殊处理 coordinates
                    if attr == "coordinates" and val:
                        try:
                            metadata_dict[attr] = {
                                "points": str(val.points) if hasattr(val, "points") else str(val),
                                "system": str(val.system) if hasattr(val, "system") else None
                            }
                        except:
                            metadata_dict[attr] = str(val)
                    else:
                        metadata_dict[attr] = val

            # 尝试 to_dict
            if hasattr(metadata, "to_dict"):
                try:
                    metadata_dict["_to_dict"] = metadata.to_dict()
                except:
                    pass

            info["metadata"] = metadata_dict

        # 尝试 to_dict
        if hasattr(el, "to_dict"):
            try:
                info["_element_to_dict"] = el.to_dict()
            except Exception as e:
                info["_element_to_dict_error"] = str(e)

        return info

    def print_elements(self, count: int = 3, start: int = 0, category_filter: Optional[str] = None):
        """
        打印指定数量的 element 结构

        Args:
            count: 打印数量
            start: 起始索引
            category_filter: 按类别过滤（如 "Title", "ListItem" 等）
        """
        if self.elements is None:
            self.parse()

        elements_to_print = []

        for idx, el in enumerate(self.elements):
            if idx < start:
                continue

            cat = getattr(el, "category", None) or getattr(el, "type", None)

            if category_filter and cat != category_filter:
                continue

            elements_to_print.append((idx, el))

            if len(elements_to_print) >= count:
                break

        print(f"\n{'=' * 80}")
        print(f"[ElementInspector] 打印 {len(elements_to_print)} 个元素")
        if category_filter:
            print(f"[ElementInspector] 过滤类别: {category_filter}")
        print(f"{'=' * 80}\n")

        for idx, el in elements_to_print:
            info = self.inspect_element(el, idx)
            print(f"--- Element [{idx}] ---")
            print(json.dumps(info, ensure_ascii=False, indent=2, default=str))
            print()

    def get_all_categories(self) -> dict:
        """获取所有类别及其数量"""
        if self.elements is None:
            self.parse()

        categories = {}
        for el in self.elements:
            cat = getattr(el, "category", None) or getattr(el, "type", None) or "Unknown"
            categories[cat] = categories.get(cat, 0) + 1

        return categories

    def print_category_summary(self):
        """打印类别统计"""
        categories = self.get_all_categories()

        print(f"\n{'=' * 80}")
        print(f"[ElementInspector] 类别统计")
        print(f"{'=' * 80}")

        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            print(f"  {cat}: {count}")

        print(f"{'=' * 80}\n")


# ============== 命令行入口 ==============

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python element_inspector.py <docx_file> [count] [category]")
        print("示例:")
        print("  python element_inspector.py input.docx")
        print("  python element_inspector.py input.docx 5")
        print("  python element_inspector.py input.docx 3 Title")
        print("  python element_inspector.py input.docx 3 ListItem")
        sys.exit(1)

    docx_file = sys.argv[1]
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    category = sys.argv[3] if len(sys.argv) > 3 else None

    inspector = ElementInspector(docx_file)
    inspector.parse()

    # 先打印类别统计
    inspector.print_category_summary()

    # 再打印指定数量的元素
    inspector.print_elements(count=count, category_filter=category)