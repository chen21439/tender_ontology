# AIDocument 提示词目录

本目录包含用于 AI 文档分析的各种提示词模板。

## 文件说明

### 1. document_layout_analysis_prompt.py
**用途**: 学术文档版面分析和语义行分类

**功能**:
- 对学术论文页面进行版面分析
- 对每一行文本进行语义分类（共 9 个类别）
- 支持多模态输入（图片 + 文本行结构化信息）

**分类类别**:
1. `Title` - 论文主标题或子标题
2. `Section` - 章节标题
3. `First-Line` - 段落首行
4. `Para-Line` - 段落非首行
5. `Figure` - 图像/插图区域
6. `Caption` - 图表说明文字
7. `Page-Header` - 页眉
8. `Page-Footer` - 页脚
9. `Footnote` - 脚注

**使用示例**:
```python
from app.prompts.AIDocument.document_layout_analysis_prompt import (
    DOCUMENT_LAYOUT_ANALYSIS_PROMPT,
    get_document_layout_analysis_prompt
)

# 方式1：直接使用原始提示词
prompt = DOCUMENT_LAYOUT_ANALYSIS_PROMPT

# 方式2：使用辅助函数（可自定义占位符）
prompt = get_document_layout_analysis_prompt(
    page_image_placeholder="[图片已上传]",
    line_data_json_placeholder='[{"line_id": 1, "text": "示例文本"}]'
)
```

**输出格式**:
```json
[
  {"line_id": 834, "label": "Caption"},
  {"line_id": 835, "label": "Para-Line"},
  {"line_id": 836, "label": "First-Line"}
]
```

### 2. image_understanding_prompt.py
**用途**: （待补充说明）

### 3. 笔记.md
**用途**: 文档标题层级结构提取

**功能**:
- 从长文档中抽取完整的标题层级结构
- 支持多级标题（4级及以上）
- 输出 JSON 格式的树形结构

**核心原则**:
1. 标题必须在原文中真实存在且独立成行
2. 分解到最小的完整语义粒度
3. 严格按照层级关系组织

**输出格式**:
```json
[
  {
    "title": "一级标题1",
    "children": [
      {
        "title": "二级标题1.1",
        "children": [
          {"title": "三级标题1.1.1"}
        ]
      }
    ]
  }
]
```

## 注意事项

- 所有提示词都应当严格遵循输出格式要求
- 使用前请仔细阅读每个提示词的具体说明
- 建议根据实际需求选择合适的提示词模板
