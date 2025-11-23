"""
文档标题关系预测提示词
基于 Detect-Order-Construct 论文思路，预测标题间的父子和兄弟关系
"""

RELATION_PREDICTION_PROMPT = """# 文档标题关系预测任务

## 任务说明

你是一个专业的文档结构分析专家。你将收到一份文档中**已识别的标题候选列表**（按阅读顺序排列），你的任务是预测这些标题之间的**层级关系**。

**核心思路**：不要直接猜测 level=1/2/3，而是预测标题之间的**父子关系**和**兄弟关系**，然后通过这些关系构建层级树。

---

## 输入格式

你会收到一个 JSON 数组，每个元素代表一个标题候选，包含：

```json
{
  "id": 行号,
  "text": "标题文本",
  "page": 页码,
  "features": {
    "font_size_level": 0/1/2,        // 0=正文大小, 1=中等, 2=最大
    "is_bold": true/false,            // 是否加粗
    "is_centered": true/false,        // 是否居中
    "indent_level": 0/1/2,            // 缩进级别
    "spacing_before": "small/medium/large",  // 前置空白
    "has_numbering": true/false,      // 是否有编号
    "numbering_pattern": "1/1.1/一、/（一）/null"  // 编号模式
  }
}
```

---

## 你的任务

### 第一步：判断是否为标题

对于每个候选项，判断它**是否真的是标题**，以及**标题类型**。

**判断依据**：
1. **文本特征**：
   - 短句（通常 < 50 字）
   - 不包含完整句子（没有句号结尾，除非是问句标题）
   - 包含编号（如 1、1.1、一、（一））
   - 常见章节名称（如"引言"、"背景"、"方法"、"结论"等）

2. **版面特征**（从 features 中获取）：
   - 字号明显大于正文
   - 加粗、居中、全大写
   - 上下留白明显

3. **标题类型**：
   - `document_title`: 文档主标题（通常在首页，字号最大）
   - `section`: 章节标题（第一级标题，如"第一章"）
   - `subsection`: 小节标题（第二级标题，如"1.1"）
   - `subsubsection`: 小小节标题（第三级，如"1.1.1"）
   - `other`: 图表标题、附录标题等

### 第二步：预测父子和兄弟关系

**重要约束**：
- 标题按**阅读顺序**排列（从上到下，从前到后）
- 每个标题 i 只能选择 **j < i** 的标题作为父节点或左兄弟
- 如果是顶层标题，`parent_id` 指向自己
- 如果是某层最左边的标题，`left_sibling_id` 指向自己

对于每个**确认为标题**的候选项 i，预测：

1. **parent_id**（父节点）：
   - 在所有 j < i 的标题中，选择一个作为父节点
   - 判断依据：
     * 编号层级（如"1.1"的父节点是"1"）
     * 字号大小（父节点字号通常更大）
     * 缩进关系（子节点通常缩进更多）
     * 内容语义（子标题是父标题内容的细分）
   - 如果是顶层标题（如"第一章"），`parent_id = 自己的id`

2. **left_sibling_id**（左兄弟节点）：
   - 在所有 j < i 的**同级**标题中，选择最近的一个
   - 判断依据：
     * 相同的父节点
     * 相似的编号模式（如"1.1"和"1.2"是兄弟）
     * 相似的字号和格式
   - 如果是该层最左边的标题，`left_sibling_id = 自己的id`

---

## 关系预测规则

### 规则1：编号优先
- 如果标题有明确编号，优先按编号判断：
  * `1`, `2`, `3` → 同级兄弟
  * `1.1`, `1.2` → 同级兄弟，父节点是 `1`
  * `1.1.1` → 父节点是 `1.1`

### 规则2：字号层级
- 字号更大的标题，层级更高
- `font_size_level=2` 通常是顶层标题
- `font_size_level=1` 是中层标题
- `font_size_level=0` 可能不是标题

### 规则3：格式一致性
- 同级标题通常有相似的格式：
  * 相同的字号
  * 相同的加粗/居中属性
  * 相同的缩进级别

### 规则4：内容语义
- 子标题是父标题的细分：
  * "项目背景" 是 "项目概述" 的子标题
  * "技术路线" 是 "实施方案" 的子标题

### 规则5：特殊标题
- "目录"、"摘要"、"前言" 通常是独立的顶层标题
- "附录"、"参考文献" 通常是文档最后的顶层标题
- 图表标题（"图1"、"表1"）通常不参与层级树

---

## 输出格式

输出一个 JSON 数组，**只包含确认为标题的项**：

```json
[
  {
    "id": 1,
    "is_heading": true,
    "heading_type": "section",
    "parent_id": 1,
    "left_sibling_id": 1,
    "confidence": "high",
    "reasoning": "这是第一章标题，编号为'第一章'，字号最大，是顶层标题"
  },
  {
    "id": 5,
    "is_heading": true,
    "heading_type": "subsection",
    "parent_id": 1,
    "left_sibling_id": 5,
    "confidence": "high",
    "reasoning": "编号为'一、'，是第一章的第一个子标题，父节点是id=1"
  },
  {
    "id": 10,
    "is_heading": true,
    "heading_type": "subsection",
    "parent_id": 1,
    "left_sibling_id": 5,
    "confidence": "high",
    "reasoning": "编号为'二、'，与id=5同级，父节点是id=1，左兄弟是id=5"
  },
  {
    "id": 15,
    "is_heading": true,
    "heading_type": "subsubsection",
    "parent_id": 10,
    "left_sibling_id": 15,
    "confidence": "medium",
    "reasoning": "编号为'（一）'，是id=10的子标题"
  }
]
```

**字段说明**：
- `id`: 原始行号
- `is_heading`: 必须为 true（非标题不输出）
- `heading_type`: 标题类型（document_title/section/subsection/subsubsection/other）
- `parent_id`: 父节点的id，顶层标题指向自己
- `left_sibling_id`: 左兄弟的id，最左边的指向自己
- `confidence`: 置信度（high/medium/low）
- `reasoning`: 简短说明预测依据（1-2句话）

---

## 重要提醒

1. **顺序约束**：parent_id 和 left_sibling_id 必须 < 当前 id（不能指向后面的标题）
2. **自引用规则**：顶层标题和最左边标题必须指向自己
3. **一致性**：同一父节点下的子标题，应该有相似的格式
4. **合理性**：父节点的字号应该 ≥ 子节点
5. **完整性**：所有确认为标题的行都必须输出

---

## 开始分析

现在，请分析以下标题候选列表：

<这里插入标题候选列表JSON>

请严格按照上述 JSON 格式输出，不要添加任何额外的解释文字。
"""


def get_relation_prediction_prompt(candidates_json: str = "<这里插入标题候选列表JSON>") -> str:
    """
    获取标题关系预测提示词

    Args:
        candidates_json: 标题候选列表的JSON字符串

    Returns:
        格式化后的提示词
    """
    return RELATION_PREDICTION_PROMPT.replace(
        "<这里插入标题候选列表JSON>",
        candidates_json
    )