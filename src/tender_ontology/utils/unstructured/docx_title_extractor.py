"""
DOCX 标题提取器

使用 unstructured 库从 docx 文件中读取元素，
并通过规则判断"可能是标题"的部分，输出到 txt 文件。

依赖安装：
    pip install "unstructured[docx]"
    pip install python-docx
"""

import re
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

from unstructured.partition.docx import partition_docx


def is_probably_title(el) -> bool:
    """
    判断一个元素是否可能是标题

    仅使用 unstructured 库自带的分类结果

    Args:
        el: unstructured 解析出的元素对象

    Returns:
        bool: 是否可能是标题
    """
    text = (el.text or "").strip()
    if not text:
        return False

    # 只使用库自带的类别判断
    cat = getattr(el, "category", None) or getattr(el, "type", None)
    if cat in ["Title", "Header", "SectionHeader", "ListItem"]:
        return True

    return False


def extract_titles_from_docx(
    docx_path: Union[str, Path],
    custom_filter: Optional[callable] = None,
    return_all_elements: bool = False
) -> tuple:
    """
    从 docx 文件中提取可能是标题的元素

    Args:
        docx_path: docx 文件路径
        custom_filter: 自定义过滤函数，接收元素返回 bool
        return_all_elements: 是否同时返回所有元素（用于获取标题后的内容）

    Returns:
        如果 return_all_elements=False: List[dict] 标题候选列表
        如果 return_all_elements=True: (List[dict], List) 标题候选列表和所有元素
    """
    docx_path = Path(docx_path)
    if not docx_path.exists():
        raise FileNotFoundError(f"文件不存在: {docx_path}")

    if not docx_path.suffix.lower() == ".docx":
        raise ValueError(f"不是 docx 文件: {docx_path}")

    # 使用 unstructured 解析 docx
    elements = partition_docx(str(docx_path))

    # 使用自定义过滤器或默认的标题判断函数
    filter_func = custom_filter if custom_filter else is_probably_title

    title_candidates = []
    for idx, el in enumerate(elements):
        if filter_func(el):
            cat = getattr(el, "category", None) or getattr(el, "type", None) or "Unknown"
            title_candidates.append({
                "text": el.text.strip(),
                "category": cat,
                "index": idx,
            })

    if return_all_elements:
        return title_candidates, elements
    return title_candidates


def extract_titles_to_txt(
    docx_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    custom_filter: Optional[callable] = None,
    include_metadata: bool = False
) -> tuple:
    """
    从 docx 文件中提取标题并写入文件
    - Title/Header/SectionHeader 写入 _unstructured_sectionHeader_only.md
    - Title/Header/SectionHeader + 下方内容 写入 _unstructured_title_with_id.md
    - ListItem 写入 _titles_{timestamp}.txt

    Args:
        docx_path: docx 文件路径
        output_path: 输出 txt 文件路径，默认为同目录下同名 .txt 文件
        custom_filter: 自定义过滤函数
        include_metadata: 是否在输出中包含元数据（类别、索引）

    Returns:
        tuple: (section_header_md_path, title_with_id_md_path, txt_path) 输出文件路径
    """
    docx_path = Path(docx_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 输出路径
    section_header_md_path = docx_path.parent / f"{docx_path.stem}_unstructured_sectionHeader_only.md"
    title_with_id_md_path = docx_path.parent / f"{docx_path.stem}_unstructured_title_with_id.md"
    if output_path is None:
        txt_path = docx_path.parent / f"{docx_path.stem}_titles_{timestamp}.txt"
    else:
        txt_path = Path(output_path)

    # 提取标题，同时获取所有元素
    titles, all_elements = extract_titles_from_docx(docx_path, custom_filter, return_all_elements=True)

    # 分离 ListItem 和其他类型
    header_types = [item for item in titles if item['category'] in ["Title", "Header", "SectionHeader"]]
    list_items = [item for item in titles if item['category'] == "ListItem"]

    # 写入 sectionHeader_only.md (只有标题)
    with open(section_header_md_path, "w", encoding="utf-8") as f:
        f.write(f"# {docx_path.stem} - 标题结构\n\n")
        f.write(f"> 提取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"> 共 {len(header_types)} 条\n\n")

        for item in header_types:
            if include_metadata:
                f.write(f"- [{item['category']}] (idx:{item['index']}) {item['text']}\n")
            else:
                f.write(f"- {item['text']}\n")

    # 写入 title_with_id.md (标题 + 下方内容)
    with open(title_with_id_md_path, "w", encoding="utf-8") as f:
        f.write(f"# {docx_path.stem} - 标题与内容\n\n")
        f.write(f"> 提取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"> 共 {len(header_types)} 条标题\n\n")

        for item in header_types:
            idx = item['index']
            # 写入标题
            f.write(f"## [{item['category']}] {item['text']}\n\n")

            # 获取下方内容（下一个元素）
            if idx + 1 < len(all_elements):
                next_el = all_elements[idx + 1]
                next_text = (next_el.text or "").strip()
                next_cat = getattr(next_el, "category", None) or getattr(next_el, "type", None)

                # 如果下一个不是标题类型，则作为内容输出
                if next_cat not in ["Title", "Header", "SectionHeader"] and next_text:
                    f.write(f"{next_text}\n")

            f.write("\n")

    # 写入 txt 文件 (ListItem)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"# 从 {docx_path.name} 提取的列表项 (ListItem)\n")
        f.write(f"# 共 {len(list_items)} 条\n")
        f.write("-" * 50 + "\n\n")

        for item in list_items:
            if include_metadata:
                f.write(f"(idx:{item['index']}) {item['text']}\n")
            else:
                f.write(f"{item['text']}\n")

    # 写入 paragraph_fulltext.json (所有段落，不含表格)
    paragraph_fulltext_path = docx_path.parent / f"{docx_path.stem}_unstructured_paragraph_fulltext.json"
    paragraphs = []
    for idx, el in enumerate(all_elements):
        cat = getattr(el, "category", None) or getattr(el, "type", None)
        text = (el.text or "").strip()

        # 排除表格相关类型
        if cat in ["Table", "TableChunk"]:
            continue

        if text:
            paragraphs.append({
                "id": f"unstructured-{idx}",
                "text": text,
                "category": cat,
                "index": idx
            })

    paragraph_fulltext_path.write_text(
        json.dumps(paragraphs, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    return section_header_md_path, title_with_id_md_path, txt_path, paragraph_fulltext_path


# ============== 命令行入口 ==============

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python docx_title_extractor.py <docx_file> [output_txt]")
        print("示例: python docx_title_extractor.py input.docx")
        print("      python docx_title_extractor.py input.docx output.txt")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        print(f"=" * 60)
        print(f"[Unstructured] 开始解析: {Path(input_file).name}")
        print(f"=" * 60)

        # 计时：partition_docx
        total_start = time.time()
        parse_start = time.time()

        docx_path = Path(input_file)
        elements = partition_docx(str(docx_path))

        parse_time = time.time() - parse_start
        print(f"[partition_docx] 解析完成，共 {len(elements)} 个元素，耗时: {parse_time:.2f} 秒")

        # 类别统计
        categories = {}
        for el in elements:
            cat = getattr(el, "category", None) or "Unknown"
            categories[cat] = categories.get(cat, 0) + 1

        print(f"\n[类别统计]")
        for cat, cnt in sorted(categories.items(), key=lambda x: -x[1]):
            print(f"  {cat}: {cnt}")

        # 打印前3个元素
        print(f"\n[前 3 个元素详情]")
        for i, el in enumerate(elements[:3]):
            cat = getattr(el, "category", None)
            text = (el.text or "")[:100] + ("..." if len(el.text or "") > 100 else "")
            print(f"\n--- Element [{i}] ---")
            print(json.dumps({
                "index": i,
                "type": type(el).__name__,
                "category": cat,
                "text": text,
                "text_length": len(el.text or "")
            }, ensure_ascii=False, indent=2))

        # 计时：文件写入
        write_start = time.time()

        section_header_md, title_with_id_md, txt_path, paragraph_fulltext = extract_titles_to_txt(
            input_file,
            output_file,
            include_metadata=True
        )

        write_time = time.time() - write_start
        total_time = time.time() - total_start

        print(f"\n[输出文件]")
        print(f"  - 标题结构: {section_header_md.name}")
        print(f"  - 标题+内容: {title_with_id_md.name}")
        print(f"  - 列表项: {txt_path.name}")
        print(f"  - 全文段落: {paragraph_fulltext.name}")

        # 统计
        titles, _ = extract_titles_from_docx(input_file, return_all_elements=True)
        header_count = sum(1 for t in titles if t['category'] in ["Title", "Header", "SectionHeader"])
        list_count = sum(1 for t in titles if t['category'] == "ListItem")

        print(f"\n[统计]")
        print(f"  - 标题 (Title/Header/SectionHeader): {header_count} 个")
        print(f"  - 列表项 (ListItem): {list_count} 个")

        print(f"\n[耗时统计]")
        print(f"  - partition_docx 解析: {parse_time:.2f} 秒")
        print(f"  - 文件写入: {write_time:.2f} 秒")
        print(f"  - 总耗时: {total_time:.2f} 秒")
        print(f"=" * 60)

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)