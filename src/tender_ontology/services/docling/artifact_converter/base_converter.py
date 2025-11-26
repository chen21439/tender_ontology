"""
BaseConverter - 所有转换器的公共基类

提供共享的工具方法：
1. 表格内容过滤（_build_parent_map, _is_in_table）
2. 阅读顺序构建（_build_reading_order）
3. 通用工具方法（normalize_id, remove_zero_width_chars, get_element_position）
"""

import re
from typing import Dict, Any, Tuple


class BaseConverter:
    """所有 Docling JSON 转换器的基类"""

    # 零宽字符正则表达式（共享）
    ZERO_WIDTH_CHARS = re.compile(
        r'[\u200B\u200C\u200D\uFEFF\u00AD]'
    )

    def __init__(self, debug: bool = False):
        """
        初始化基础转换器

        Args:
            debug: 是否启用调试输出
        """
        self.debug = debug

    @staticmethod
    def normalize_id(self_ref: str) -> str:
        """
        将 self_ref 转换为统一的 ID

        Args:
            self_ref: Docling 原生引用，如 '#/texts/5'

        Returns:
            标准化的 ID，如 'texts-5'
        """
        return self_ref.lstrip("#/").replace("/", "-")

    @classmethod
    def remove_zero_width_chars(cls, text: str) -> str:
        """移除字符串中的零宽字符"""
        return cls.ZERO_WIDTH_CHARS.sub('', text)

    @staticmethod
    def get_element_position(item: Dict[str, Any]) -> Tuple[int, float]:
        """
        获取元素的页面位置信息

        Args:
            item: 元素数据（text 或 table）

        Returns:
            (page_no, top) 元组，用于排序
        """
        prov = item.get("prov", [])
        if prov and len(prov) > 0:
            first_prov = prov[0]
            page_no = first_prov.get("page_no", 0)
            bbox = first_prov.get("bbox", {})
            top = bbox.get("t", 0)
            return (page_no, top)
        return (0, 0)

    def _build_parent_map(self, docling_json: Dict[str, Any]) -> Dict[str, str]:
        """
        构建子元素到父元素的映射

        用途：判断元素是否在表格内（通过追踪父节点链）

        Args:
            docling_json: Docling 完整 JSON 数据

        Returns:
            子元素 cref -> 父元素 cref 的映射字典
        """
        parent_map = {}

        # body.children 的父节点是 body
        for child in docling_json.get("body", {}).get("children", []):
            cref = child.get("cref", "")
            if cref:
                parent_map[cref] = "#/body"

        # groups 的父子关系
        for group in docling_json.get("groups", []):
            self_ref = group.get("self_ref", "")
            parent = group.get("parent", {})
            parent_cref = parent.get("cref", "") if parent else ""

            if self_ref and parent_cref:
                parent_map[self_ref] = parent_cref

            # group 的 children
            for child in group.get("children", []):
                child_cref = child.get("cref", "")
                if child_cref and self_ref:
                    parent_map[child_cref] = self_ref

        # tables 的父子关系
        for table in docling_json.get("tables", []):
            self_ref = table.get("self_ref", "")
            parent = table.get("parent", {})
            parent_cref = parent.get("cref", "") if parent else ""

            if self_ref and parent_cref:
                parent_map[self_ref] = parent_cref

            # table 的 children
            for child in table.get("children", []):
                child_cref = child.get("cref", "")
                if child_cref and self_ref:
                    parent_map[child_cref] = self_ref

        # texts 的父子关系（非常重要！用于判断 text 是否在表格内）
        for text in docling_json.get("texts", []):
            self_ref = text.get("self_ref", "")
            parent = text.get("parent", {})
            parent_cref = parent.get("cref", "") if parent else ""

            if self_ref and parent_cref:
                parent_map[self_ref] = parent_cref

            # text 的 children（如果有）
            for child in text.get("children", []):
                child_cref = child.get("cref", "")
                if child_cref and self_ref:
                    parent_map[child_cref] = self_ref

        return parent_map

    def _is_in_table(self, cref: str, parent_map: Dict[str, str]) -> bool:
        """
        判断一个元素是否在表格内（通过祖先链判断）

        工作原理：
        沿着 parent_map 向上追踪，直到找到 #/tables/X 或到达根节点

        示例：
            #/texts/290 → #/groups/7 → #/tables/3  ✅ 在表格内
            #/texts/100 → #/groups/2 → #/body      ❌ 不在表格内

        Args:
            cref: 元素的 cref
            parent_map: 父子关系映射

        Returns:
            True 如果元素在表格内，False 否则
        """
        current = cref
        visited = set()

        # 沿着父节点链向上查找
        while current in parent_map:
            parent = parent_map[current]

            # 防止循环引用
            if parent in visited:
                break

            # 如果祖先是 table，说明当前元素在表格内
            if parent.startswith("#/tables/"):
                return True

            visited.add(parent)
            current = parent

        return False

    def _build_reading_order(self, docling_json: Dict[str, Any], element_order: Dict[str, int]) -> None:
        """
        递归构建阅读顺序映射（按 Docling 规范：body 树的 children 顺序）

        策略：
        1. 优先使用 body 树的结构顺序（DFS 遍历）
        2. 对于不在 body 树中的 texts，使用 texts 数组索引作为 fallback

        Args:
            docling_json: Docling 完整 JSON 数据
            element_order: 输出的顺序映射字典 (cref -> order_index)
        """
        # 构建 cref -> item 的映射
        groups_map = {}
        for group in docling_json.get("groups", []):
            self_ref = group.get("self_ref", "")
            if self_ref:
                groups_map[self_ref] = group

        tables_map = {}
        for table in docling_json.get("tables", []):
            self_ref = table.get("self_ref", "")
            if self_ref:
                tables_map[self_ref] = table

        texts_map = {}
        for text in docling_json.get("texts", []):
            self_ref = text.get("self_ref", "")
            if self_ref:
                texts_map[self_ref] = text

        # 第一步：DFS 遍历 body 树
        counter = [0]

        def traverse(children_list):
            """递归遍历 children，按顺序分配序号"""
            for child in children_list:
                cref = child.get("cref", "")
                if not cref:
                    continue

                # 给当前元素分配序号（如果还没分配）
                if cref not in element_order:
                    element_order[cref] = counter[0]
                    counter[0] += 1

                # 根据 cref 类型，递归处理其 children
                if cref.startswith("#/groups/"):
                    if cref in groups_map:
                        group = groups_map[cref]
                        group_children = group.get("children", [])
                        if group_children:
                            traverse(group_children)
                elif cref.startswith("#/tables/"):
                    if cref in tables_map:
                        table = tables_map[cref]
                        table_children = table.get("children", [])
                        if table_children:
                            traverse(table_children)
                elif cref.startswith("#/texts/"):
                    # texts 也可能有 children！
                    if cref in texts_map:
                        text_item = texts_map[cref]
                        text_children = text_item.get("children", [])
                        if text_children:
                            traverse(text_children)

        # 从 body.children 开始遍历
        body_children = docling_json.get("body", {}).get("children", [])
        traverse(body_children)

        body_count = len(element_order)

        # 第二步：处理所有 texts，给不在 body 树中的分配 fallback 顺序
        # 使用一个大偏移量（10000），确保 fallback 元素排在正文之后
        FALLBACK_OFFSET = 10000
        texts = docling_json.get("texts", [])

        for idx, text_item in enumerate(texts):
            self_ref = text_item.get("self_ref", "")
            if self_ref and self_ref not in element_order:
                # 使用 texts 数组索引作为 fallback
                element_order[self_ref] = FALLBACK_OFFSET + idx

        fallback_count = len(element_order) - body_count

        # 同样处理 tables（如果有不在 body 树中的表格）
        tables = docling_json.get("tables", [])
        for idx, table_item in enumerate(tables):
            self_ref = table_item.get("self_ref", "")
            if self_ref and self_ref not in element_order:
                # 表格的 fallback 排在 texts 之后
                element_order[self_ref] = FALLBACK_OFFSET + len(texts) + idx

        if self.debug:
            print(f"  [DEBUG] 构建阅读顺序映射:")
            print(f"    - Body 树中: {body_count} 个元素")
            print(f"    - Fallback: {fallback_count} 个元素")
            print(f"    - 总共: {len(element_order)} 个元素")