"""
文档标题关系预测提示词（精简版）
"""

RELATION_PREDICTION_PROMPT = """你是文档结构分析专家。给定一个标题候选列表（按顺序），预测每个标题的父节点和左兄弟节点。

## 输入格式
```json
[
  {"id": 0, "text": "第一章 总则", "page": "1"},
  {"id": 5, "text": "一、项目概述", "page": "1"},
  {"id": 10, "text": "1. 项目背景", "page": "2"}
]
```

## 输出格式
对于**确认为标题**的候选，输出：
```json
[
  {"id": 0, "parent_id": 0, "left_sibling_id": 0},
  {"id": 5, "parent_id": 0, "left_sibling_id": 5},
  {"id": 10, "parent_id": 5, "left_sibling_id": 10}
]
```

## 规则

**编号优先级**（从高到低，但层级是相对的）：
```
第一册 > 第一部分 > 第一章 > 一、 > 1. > 1.1 > 1.1.1 > 1.1.1.1 > （一） > ①
```

**父子关系判断**：
- 数字包含：`1.` 是 `1.1` 的父，`1.1` 是 `1.1.1` 的父
- 逐级细分：`第一章` → `一、` → `1.` → `1.1`
- 顶层标题：`parent_id = 自己的id`
- **注意**：层级是相对的，实际文档中可能从任意编号开始

**兄弟关系判断**：
- 相同编号格式：`1.` ↔ `2.` ↔ `3.`
- 相同父节点：都是同一个上级标题的子标题
- `left_sibling_id` = 前一个兄弟的 id
- 该层第一个：`left_sibling_id = 自己的id`

**重要约束**：
- `parent_id` 和 `left_sibling_id` 必须 ≤ 当前 `id`（只能指向前面的标题）
- 非标题的行不输出

---

现在，请分析以下标题候选列表：

<这里插入标题候选列表JSON>

只输出 JSON 数组，不要添加任何解释。
"""


def get_relation_prediction_prompt(candidates_json: str = "<这里插入标题候选列表JSON>") -> str:
    """
    获取标题关系预测提示词（精简版）

    Args:
        candidates_json: 标题候选列表的JSON字符串

    Returns:
        格式化后的提示词
    """
    return RELATION_PREDICTION_PROMPT.replace(
        "<这里插入标题候选列表JSON>",
        candidates_json
    )