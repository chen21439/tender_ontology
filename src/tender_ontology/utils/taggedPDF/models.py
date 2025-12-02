"""
Tagged PDF 数据模型

定义结构树元素、MCID 映射等数据结构
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class MCIDTextMapping:
    """
    MCID 到文本的映射

    Attributes:
        page_number: 页码 (1-indexed)
        mcid: Marked Content ID
        text: 该 MCID 对应的文本内容
        chars: 组成该文本的字符对象列表（可选）
    """
    page_number: int
    mcid: int
    text: str
    chars: List[Dict[str, Any]] = field(default_factory=list)

    def __repr__(self):
        text_preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return f"MCIDTextMapping(page={self.page_number}, mcid={self.mcid}, text='{text_preview}')"


@dataclass
class StructureElement:
    """
    PDF 结构树元素

    对应 pdfplumber 的 structure_tree 中的节点

    Attributes:
        type: 结构元素类型 (如 Document, Part, Sect, H1, P, Table 等)
        page_number: 所在页码 (1-indexed, 可能为 None)
        mcids: 关联的 MCID 列表
        text: 该元素对应的文本内容列表
        attributes: 元素属性 (如 alt, lang 等)
        children: 子元素列表
    """
    type: str
    page_number: Optional[int] = None
    mcids: List[int] = field(default_factory=list)
    text: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    children: List["StructureElement"] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """获取完整文本内容（合并所有 text）"""
        return "".join(self.text)

    @property
    def has_content(self) -> bool:
        """是否有文本内容"""
        return bool(self.text and any(t.strip() for t in self.text))

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            "type": self.type,
            "page_number": self.page_number,
            "mcids": self.mcids,
            "text": self.text,
        }
        if self.attributes:
            result["attributes"] = self.attributes
        if self.children:
            result["children"] = [child.to_dict() for child in self.children]
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StructureElement":
        """从字典创建实例"""
        children = [cls.from_dict(child) for child in data.get("children", [])]
        return cls(
            type=data.get("type", "Unknown"),
            page_number=data.get("page_number"),
            mcids=data.get("mcids", []),
            text=data.get("text", []),
            attributes=data.get("attributes", {}),
            children=children,
        )

    def __repr__(self):
        text_preview = self.full_text[:30] + "..." if len(self.full_text) > 30 else self.full_text
        return f"StructureElement(type='{self.type}', page={self.page_number}, text='{text_preview}')"


@dataclass
class TaggedDocument:
    """
    Tagged PDF 文档

    Attributes:
        file_path: PDF 文件路径
        page_count: 总页数
        is_tagged: 是否为 Tagged PDF
        structure_tree: 结构树根元素列表
        mcid_mappings: 所有 MCID 到文本的映射
        metadata: PDF 元数据
    """
    file_path: str
    page_count: int
    is_tagged: bool
    structure_tree: List[StructureElement] = field(default_factory=list)
    mcid_mappings: Dict[int, Dict[int, MCIDTextMapping]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_mcid_text(self, page_number: int, mcid: int) -> Optional[str]:
        """
        获取指定页面指定 MCID 的文本

        Args:
            page_number: 页码 (1-indexed)
            mcid: MCID

        Returns:
            文本内容，如果不存在返回 None
        """
        page_mappings = self.mcid_mappings.get(page_number)
        if page_mappings:
            mapping = page_mappings.get(mcid)
            if mapping:
                return mapping.text
        return None

    def get_all_text_by_type(self, element_type: str) -> List[str]:
        """
        获取指定类型的所有文本

        Args:
            element_type: 结构元素类型 (如 H1, P, Table 等)

        Returns:
            匹配类型的文本列表
        """
        results = []
        self._collect_text_by_type(self.structure_tree, element_type, results)
        return results

    def _collect_text_by_type(
        self,
        elements: List[StructureElement],
        element_type: str,
        results: List[str]
    ):
        """递归收集指定类型的文本"""
        for element in elements:
            if element.type == element_type and element.has_content:
                results.append(element.full_text)
            self._collect_text_by_type(element.children, element_type, results)

    def get_headings(self) -> List[Dict[str, Any]]:
        """
        获取所有标题

        Returns:
            标题列表，每项包含 level, text, page_number
        """
        headings = []
        heading_types = ["H", "H1", "H2", "H3", "H4", "H5", "H6"]
        self._collect_headings(self.structure_tree, heading_types, headings)
        return headings

    def _collect_headings(
        self,
        elements: List[StructureElement],
        heading_types: List[str],
        results: List[Dict[str, Any]]
    ):
        """递归收集标题"""
        for element in elements:
            if element.type in heading_types and element.has_content:
                # 提取标题级别
                level = 0
                if element.type == "H":
                    level = 1
                elif element.type.startswith("H") and len(element.type) == 2:
                    try:
                        level = int(element.type[1])
                    except ValueError:
                        level = 1

                results.append({
                    "level": level,
                    "type": element.type,
                    "text": element.full_text,
                    "page_number": element.page_number,
                })
            self._collect_headings(element.children, heading_types, results)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "file_path": self.file_path,
            "page_count": self.page_count,
            "is_tagged": self.is_tagged,
            "structure_tree": [elem.to_dict() for elem in self.structure_tree],
            "metadata": self.metadata,
        }

    def __repr__(self):
        return (
            f"TaggedDocument(file='{self.file_path}', "
            f"pages={self.page_count}, "
            f"is_tagged={self.is_tagged}, "
            f"elements={len(self.structure_tree)})"
        )
