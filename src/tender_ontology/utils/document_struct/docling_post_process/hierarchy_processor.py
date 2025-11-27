"""
Docling 自定义后处理器

功能：
1. 识别数字编号标题（1. 1.1 1.1.1）
2. 根据编号设置 level
"""

import re
from typing import Optional, Union, List
from pathlib import Path
from io import BytesIO


def chinese_to_int(chinese_num: str) -> int:
    """
    中文数字转阿拉伯数字

    支持：一二三四五六七八九十
    示例：
        "一" -> 1
        "十" -> 10
        "十二" -> 12
        "二十三" -> 23
    """
    chinese_map = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10
    }

    if chinese_num == '十':
        return 10

    # 处理 "十X" 格式（如"十一"、"十二"）
    if chinese_num.startswith('十'):
        return 10 + chinese_map.get(chinese_num[1], 0)

    # 处理 "X十" 或 "X十Y" 格式（如"二十"、"二十三"）
    if '十' in chinese_num:
        parts = chinese_num.split('十')
        tens = chinese_map.get(parts[0], 1)  # 默认1（如"十"开头）
        ones = chinese_map.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        return tens * 10 + ones

    # 单个数字
    return chinese_map.get(chinese_num, 0)


def infer_header_level_chinese(header_text: str) -> tuple[str, int]:
    """
    识别中文编号（册、章）

    册 -> level 1
    章 -> level 2

    示例：
        "第一册 总则" -> ("册", 1)
        "第二章 招标公告" -> ("章", 2)
        "第十二章 附则" -> ("章", 12)

    Args:
        header_text: 标题文本

    Returns:
        (类型, 编号) 元组，如 ("册", 1) 或 ("章", 2)
        如果没有匹配返回 ("", 0)
    """
    text = header_text.strip()

    # 匹配：第X册 或 第X章
    match = re.match(r"^第([一二三四五六七八九十]+)([册章])", text)
    if match:
        chinese_num = match.group(1)
        unit = match.group(2)
        number = chinese_to_int(chinese_num)
        return (unit, number)

    return ("", 0)


def infer_header_level_numerical(header_text: str) -> List[int]:
    """
    识别数字编号（从 hierarchical-pdf 复制）

    示例：
        "1. 引言" -> [1]
        "1.1 背景" -> [1, 1]
        "1.1.1 目的" -> [1, 1, 1]

    Args:
        header_text: 标题文本

    Returns:
        数字列表，长度表示层级深度
    """
    # 1. 匹配多级编号：1.2.3 或 1 2 3 或 1-2-3
    match = re.match(r"^((?:\d+[.\s-])+)\d+", header_text.strip())
    if match:
        numbering = match.group(0)
        # 分割成数字列表
        try:
            groups = [int(g) for g in re.split(r"[.\s]", numbering) if g]
        except ValueError:
            return []
        return groups

    # 2. 匹配单个数字：1 标题
    match_single = re.match(r"^\d+", header_text.strip())
    if match_single:
        return [int(match_single.group(0))]

    # 3. 没有编号
    return []


class HierarchyProcessor:
    """
    Docling 自定义后处理器

    当前功能：给所有标题添加 [HIERARCHY] 前缀（用于验证集成）
    """

    def __init__(self, raise_on_error: bool = False, debug: bool = False):
        """
        初始化处理器

        Args:
            raise_on_error: 是否在错误时抛出异常
            debug: 是否启用调试输出
        """
        self.raise_on_error = raise_on_error
        self.debug = debug

    def find_left_sibling(self, headers: List[dict], current_idx: int) -> Optional[int]:
        """
        寻找左兄弟节点（同级的前一个节点）

        规则：
        - 编号类型相同（都是中文/都是数字）
        - 编号深度相同（都是1级/都是2级）
        - 在当前节点之前

        Args:
            headers: 标题列表
            current_idx: 当前标题索引

        Returns:
            左兄弟节点的索引，没有则返回 None
        """
        current = headers[current_idx]

        # 从当前节点往前找
        for i in range(current_idx - 1, -1, -1):
            candidate = headers[i]

            # 1. 中文编号：相同类型（册对册，章对章）
            if current.get("chinese_unit") and candidate.get("chinese_unit"):
                if current["chinese_unit"] == candidate["chinese_unit"]:
                    return i

            # 2. 数字编号：相同深度
            if current.get("numbering") and candidate.get("numbering"):
                if len(current["numbering"]) == len(candidate["numbering"]):
                    return i

        return None

    def numbering_to_level(self, headers: List[dict], header_idx: int) -> int:
        """
        根据父节点递归计算 level（参考 hierarchical-pdf 的逻辑）

        规则：
        - 根节点（无父节点）-> level = 1
        - 有父节点 -> level = parent.level + 1

        注意：这个函数返回基础 level，调用方可以根据需要加偏移量

        Args:
            headers: 标题列表
            header_idx: 当前标题索引

        Returns:
            基础 level 值（1, 2, 3...）
        """
        header = headers[header_idx]

        # 如果已经计算过，直接返回
        if header.get("_base_level") is not None:
            return header["_base_level"]

        # 根节点
        if header["parent"] is None:
            base_level = 1
        else:
            # 递归计算父节点的 level
            parent_idx = header["parent"]
            parent_level = self.numbering_to_level(headers, parent_idx)
            base_level = parent_level + 1

        # 缓存结果
        header["_base_level"] = base_level
        return base_level

    def find_parent(self, headers: List[dict], current_idx: int) -> Optional[int]:
        """
        寻找父节点（使用 hierarchical-pdf 的逻辑）

        规则：
        - 中文编号：章的父节点是册
        - 数字编号：使用 hierarchical-pdf 的前缀匹配逻辑

        Args:
            headers: 标题列表
            current_idx: 当前标题索引

        Returns:
            父节点的索引，没有则返回 None
        """
        current = headers[current_idx]

        # 从当前节点往前找
        for i in range(current_idx - 1, -1, -1):
            candidate = headers[i]

            # 1. 中文编号：章的父节点是册
            if current.get("chinese_unit") == "章":
                if candidate.get("chinese_unit") == "册":
                    return i

            # 2. 数字编号：使用 hierarchical-pdf 逻辑
            if current.get("numbering") and candidate.get("numbering"):
                current_numbering = current["numbering"]
                candidate_numbering = candidate["numbering"]

                current_depth = len(current_numbering)
                candidate_depth = len(candidate_numbering)

                # hierarchical-pdf 的父节点判断逻辑
                # 父节点深度应该是当前深度 - 1
                if candidate_depth == current_depth - 1:
                    # 检查前缀是否匹配
                    # 例如：[1,1] 的父节点应该是 [1]
                    #      [1,2,3] 的父节点应该是 [1,2]
                    if current_numbering[:candidate_depth] == candidate_numbering:
                        return i

        return None

    def process(
        self,
        result,  # docling.ConversionResult
        source: Optional[Union[str, Path, BytesIO]] = None
    ):
        """
        处理 Docling 转换结果

        流程：
        1. 提取所有标题并识别编号
        2. 为每个标题寻找左兄弟节点
        3. 为每个标题寻找父节点
        4. 根据父节点确定 level

        Args:
            result: Docling ConversionResult 对象
            source: PDF 源（暂未使用）
        """
        print("\n" + "="*80)
        print("🔧 [自定义插件] HierarchyProcessor - 层级关系分析")
        print("="*80)

        try:
            from docling_core.types.doc import SectionHeaderItem

            # 步骤1: 提取所有标题并识别编号
            headers = []
            items = []

            for item, _ in result.document.iterate_items():
                if isinstance(item, SectionHeaderItem):
                    # 识别中文编号
                    unit, number = infer_header_level_chinese(item.text)

                    # 识别数字编号
                    numbering = infer_header_level_numerical(item.text)

                    header_info = {
                        "item": item,
                        "text": item.text,
                        "chinese_unit": unit if unit else None,
                        "chinese_number": number if unit else None,
                        "numbering": numbering if numbering else None,
                        "left_sibling": None,
                        "parent": None,
                        "level": None
                    }

                    headers.append(header_info)
                    items.append(item)

            print(f"📋 提取到 {len(headers)} 个标题\n")

            # 步骤2: 寻找左兄弟节点
            print("🔍 步骤1: 寻找左兄弟节点")
            for i, header in enumerate(headers):
                left_sibling_idx = self.find_left_sibling(headers, i)
                header["left_sibling"] = left_sibling_idx

                if left_sibling_idx is not None:
                    sibling = headers[left_sibling_idx]
                    print(f"  [{i}] {header['text'][:40]}")
                    print(f"       左兄弟 -> [{left_sibling_idx}] {sibling['text'][:40]}")

            # 步骤3: 寻找父节点
            print(f"\n🔍 步骤2: 寻找父节点")
            for i, header in enumerate(headers):
                parent_idx = self.find_parent(headers, i)
                header["parent"] = parent_idx

                if parent_idx is not None:
                    parent = headers[parent_idx]
                    print(f"  [{i}] {header['text'][:40]}")
                    print(f"       父节点 -> [{parent_idx}] {parent['text'][:40]}")

            # 步骤4: 根据编号类型确定 level
            print(f"\n🔍 步骤3: 确定 level")
            for i, header in enumerate(headers):
                # 1. 数字编号：递归计算 + 100
                if header.get("numbering"):
                    base_level = self.numbering_to_level(headers, i)
                    header["level"] = base_level + 100  # +100 区分数字编号

                # 2. 中文编号：固定规则（不加100）
                elif header.get("chinese_unit"):
                    if header["chinese_unit"] == "册":
                        header["level"] = 1
                    elif header["chinese_unit"] == "章":
                        header["level"] = 2

                # 3. 无编号：递归计算（不加100）
                else:
                    header["level"] = self.numbering_to_level(headers, i)

                # 设置到 item
                header["item"].level = header["level"]

                # 打印信息
                if header.get("numbering"):
                    parent_info = ""
                    if header["parent"] is not None:
                        parent = headers[header["parent"]]
                        parent_info = f", 父节点: [{header['parent']}] {parent['numbering']}"

                    print(f"  [{i}] {header['text'][:40]}")
                    print(f"       数字编号: {header['numbering']} -> level: {header['level']}{parent_info}")

                elif header.get("chinese_unit"):
                    print(f"  [{i}] {header['text'][:40]}")
                    print(f"       中文编号: 第{header['chinese_number']}{header['chinese_unit']} -> level: {header['level']}")

                else:
                    print(f"  [{i}] {header['text'][:40]}")
                    print(f"       无编号 -> level: {header['level']}")

            print(f"\n✅ 处理完成")
            print("="*80 + "\n")

        except Exception as e:
            error_msg = f"处理失败: {e}"
            print(f"⚠️  {error_msg}")
            print("="*80 + "\n")

            if self.raise_on_error:
                raise
