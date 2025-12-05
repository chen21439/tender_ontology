"""
DOCX 版本检测与预处理

主要功能：
1. 检测 DOCX 文件的 Word 版本
2. 为 Word 2007 文件自动添加 paraId（用于 unstructured 定位）

使用方式：
    from tender_ontology.utils.unstructured.docx_preprocessor import preprocess_docx_if_needed

    # 自动检测并处理 Word 2007 文件
    docx_path, was_processed = preprocess_docx_if_needed("input.docx")
"""

import uuid
import logging
import zipfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Union, Tuple

from lxml import etree


# Word 2010 命名空间
W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def get_docx_version_info(docx_path: Union[str, Path]) -> Dict[str, Any]:
    """
    获取 DOCX 文件的版本信息

    Args:
        docx_path: DOCX 文件路径

    Returns:
        {
            "application": "Microsoft Office Word",
            "app_version": "12.0000",
            "word_version": "Word 2007",
            "creator": "...",
            "needs_para_id": True/False
        }
    """
    docx_path = Path(docx_path)
    result = {
        "application": None,
        "app_version": None,
        "word_version": "Unknown",
        "creator": None,
        "needs_para_id": False
    }

    # 版本映射
    version_map = {
        "12": "Word 2007",
        "14": "Word 2010",
        "15": "Word 2013",
        "16": "Word 2016/2019/365"
    }

    try:
        with zipfile.ZipFile(docx_path, 'r') as zf:
            # 读取 app.xml
            if 'docProps/app.xml' in zf.namelist():
                app_xml = zf.read('docProps/app.xml')
                root = etree.fromstring(app_xml)
                ns = {'ep': 'http://schemas.openxmlformats.org/officeDocument/2006/extended-properties'}

                app_name = root.find('.//ep:Application', ns)
                app_version = root.find('.//ep:AppVersion', ns)

                if app_name is not None:
                    result["application"] = app_name.text
                if app_version is not None:
                    result["app_version"] = app_version.text
                    # 解析主版本号
                    major_version = app_version.text.split('.')[0] if app_version.text else None
                    if major_version:
                        result["word_version"] = version_map.get(major_version, f"Word (v{major_version})")
                        # Word 2007 (12.x) 需要添加 paraId
                        if major_version == "12":
                            result["needs_para_id"] = True

            # 读取 core.xml
            if 'docProps/core.xml' in zf.namelist():
                core_xml = zf.read('docProps/core.xml')
                root = etree.fromstring(core_xml)
                ns = {'dc': 'http://purl.org/dc/elements/1.1/'}

                creator = root.find('.//dc:creator', ns)
                if creator is not None:
                    result["creator"] = creator.text

    except Exception as e:
        logging.warning(f"获取 DOCX 版本信息失败: {e}")

    return result


def generate_para_id() -> str:
    """生成 8 位十六进制 ID（Word 格式）"""
    return uuid.uuid4().hex[:8].upper()


def add_para_ids_to_docx(
    input_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None
) -> Path:
    """
    为 DOCX 文件中的所有段落添加 paraId

    Args:
        input_path: 输入 DOCX 文件路径
        output_path: 输出文件路径（可选，默认覆盖原文件）

    Returns:
        输出文件路径
    """
    from docx import Document

    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path
    else:
        output_path = Path(output_path)

    doc = Document(str(input_path))

    # 注册命名空间
    etree.register_namespace("w14", W14_NS)

    used_ids = set()
    added_count = 0

    def process_paragraph(para_element):
        nonlocal added_count
        # 检查是否已有 paraId
        existing_id = para_element.get(f'{{{W14_NS}}}paraId')
        if existing_id:
            used_ids.add(existing_id)
            return

        # 生成唯一 ID
        new_id = generate_para_id()
        while new_id in used_ids:
            new_id = generate_para_id()
        used_ids.add(new_id)

        # 添加 paraId 属性
        para_element.set(f'{{{W14_NS}}}paraId', new_id)

        # 同时添加 textId
        text_id = generate_para_id()
        while text_id in used_ids:
            text_id = generate_para_id()
        used_ids.add(text_id)
        para_element.set(f'{{{W14_NS}}}textId', text_id)

        added_count += 1

    # 处理所有 w:p 元素（包括表格内的）
    for p_element in doc.element.body.iter(f'{{{W_NS}}}p'):
        process_paragraph(p_element)

    doc.save(str(output_path))

    logging.info(f"[DOCX预处理] 已为 {added_count} 个段落添加 paraId")

    return output_path


def preprocess_docx_if_needed(
    docx_path: Union[str, Path],
    verbose: bool = True
) -> Tuple[Path, bool]:
    """
    检测 DOCX 版本，如果需要则添加 paraId

    Args:
        docx_path: DOCX 文件路径
        verbose: 是否打印详细信息

    Returns:
        (处理后的文件路径, 是否进行了处理)
    """
    docx_path = Path(docx_path)

    # 获取版本信息
    version_info = get_docx_version_info(docx_path)

    if verbose:
        print(f"[DOCX版本检测] {version_info['word_version']} (v{version_info['app_version']})")

    if not version_info["needs_para_id"]:
        return docx_path, False

    if verbose:
        print(f"[DOCX预处理] Word 2007 文件，需要添加 paraId...")

    # 创建备份并处理
    backup_path = docx_path.parent / f"{docx_path.stem}_original{docx_path.suffix}"

    # 备份原文件
    shutil.copy2(docx_path, backup_path)

    try:
        # 添加 paraId
        add_para_ids_to_docx(docx_path, docx_path)

        if verbose:
            print(f"[DOCX预处理] 完成，原文件已备份到: {backup_path.name}")

        return docx_path, True

    except Exception as e:
        # 恢复原文件
        shutil.copy2(backup_path, docx_path)
        logging.error(f"[DOCX预处理] 添加 paraId 失败: {e}")
        return docx_path, False


# ============== 命令行入口 ==============

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python docx_preprocessor.py <docx_file>")
        print("示例: python docx_preprocessor.py input.docx")
        sys.exit(1)

    docx_file = sys.argv[1]

    print(f"检测文件: {docx_file}")
    info = get_docx_version_info(docx_file)
    print(f"  应用程序: {info['application']}")
    print(f"  版本: {info['app_version']}")
    print(f"  Word版本: {info['word_version']}")
    print(f"  需要添加paraId: {info['needs_para_id']}")

    if info['needs_para_id']:
        print("\n开始预处理...")
        result_path, processed = preprocess_docx_if_needed(docx_file)
        if processed:
            print(f"处理完成: {result_path}")
        else:
            print("处理失败")