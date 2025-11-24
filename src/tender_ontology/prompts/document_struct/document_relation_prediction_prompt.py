"""
文档标题关系预测提示词（纯文本版本）
基于 Detect-Order-Construct 论文思路，预测标题间的父子和兄弟关系
"""

RELATION_PREDICTION_PROMPT = """# 文档标题关系预测任务

## 任务说明

你是一个专业的文档结构分析专家。你将收到一份文档中**已识别的标题候选列表**（按阅读顺序排列），你的任务是预测这些标题之间的**父子关系**和**兄弟关系**。

**核心思路**：不要直接猜测 level=1/2/3，而是预测标题之间的**父子关系**和**兄弟关系**。

---

## 输入格式

你会收到一个 JSON 数组，每个元素代表一个标题候选，包含：

```json
{
  "id": 行号,
  "text": "标题文本",
  "page": 页码
}
```

**注意**：输入只包含纯文本，没有版面信息（字号、加粗等）。你需要**完全基于文本内容**进行判断。

---

## 你的任务

### 第一步：判断是否为标题

### 第二步：预测父子和兄弟关系

**重要约束**：
- 标题按**阅读顺序**排列（从上到下，从前到后）
- 每个标题 i 只能选择 **j < i** 的标题作为父节点或左兄弟
- 如果是顶层标题，`parent_id` 指向自己
- 如果是某层最左边的标题，`left_sibling_id` 指向自己

对于每个**确认为标题**的候选项 i，预测：

1. **parent_id**（父节点）：
   - 在所有 j < i 的标题中，选择一个作为父节点
   - 如果是顶层标题（如"第一章"），`parent_id = 自己的id`

2. **left_sibling_id**（左兄弟节点）：
   - 在所有 j < i 的**同级**标题中，选择最近的一个
   - 如果是该层最左边的标题，`left_sibling_id = 自己的id`

---

## 关系预测规则


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
    "reasoning": "编号为'第一章'，是顶层标题，parent_id 指向自己"
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
    "reasoning": "编号为'二、'，与id=5同级（都是'X、'格式），左兄弟是id=5"
  },
  {
    "id": 15,
    "is_heading": true,
    "heading_type": "subsubsection",
    "parent_id": 10,
    "left_sibling_id": 15,
    "confidence": "medium",
    "reasoning": "编号为'（一）'，是id=10的子标题，该层第一个"
  }
]
```

**字段说明**：
- `id`: 原始行号
- `is_heading`: 必须为 true（非标题不输出）
- `heading_type`: 标题类型（document_title/section/subsection/subsubsection/other）
- `parent_id`: 父节点的id，顶层标题指向自己
- `left_sibling_id`: 左兄弟的id，该层最左边的指向自己
- `confidence`: 置信度（high/medium/low）
- `reasoning`: 简短说明预测依据，**必须提及编号模式**（1-2句话）

---

## 重要提醒

1. **顺序约束**：parent_id 和 left_sibling_id 必须 < 当前 id（不能指向后面的标题）
2. **自引用规则**：顶层标题和最左边标题必须指向自己
3. **编号优先**：**优先使用编号模式判断**，这是最可靠的依据
4. **完整性**：所有确认为标题的行都必须输出
5. **推理说明**：reasoning 字段必须说明判断依据，特别是编号模式

---

## 开始分析

现在，请分析以下标题候选列表：

<这里插入标题候选列表JSON>

请严格按照上述 JSON 格式输出，不要添加任何额外的解释文字。
"""


def get_relation_prediction_prompt(candidates_json: str = "<这里插入标题候选列表JSON>") -> str:
    """
    获取标题关系预测提示词（纯文本版本）

    Args:
        candidates_json: 标题候选列表的JSON字符串

    Returns:
        格式化后的提示词
    """
    return RELATION_PREDICTION_PROMPT.replace(
        "<这里插入标题候选列表JSON>",
        candidates_json
    )