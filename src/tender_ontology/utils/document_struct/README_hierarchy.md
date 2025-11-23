# 文档层级目录构建工具 (hierarchy_builder)

基于已标注的文档数据，使用 AI 构建文档的层级目录结构。

## 功能特点

- 从已标注的 JSON 文件中提取纯文本内容
- 支持只分析章节标题或分析完整文档
- 使用百度千帆 ERNIE 文本模型进行智能分析
- 自动识别章节层级（H1, H2, H3...）
- 构建完整的目录树结构
- 保存分析结果到 JSON 文件

## 使用前提

1. **已标注的文档数据**
   - JSON 格式
   - 包含 `class` 字段标注（如 `Section`, `First-Line`, `Para-Line` 等）
   - 通过 `line_tagger.py` 工具生成

2. **API 配置**
   - 百度千帆 API Key（已内置默认 Key）
   - 可选：自定义 API Key

## 快速开始

### 基础用法

```python
from tender_ontology.utils.document_struct import process_document_hierarchy

# 处理文档，构建层级目录
result = process_document_hierarchy(
    json_path="path/to/tagged.json",
    include_sections_only=True,  # 只分析章节标题
    verbose=True,                # 显示详细信息
    save_results=True            # 保存结果
)
```

### 自定义客户端

```python
from tender_ontology.utils.document_struct import (
    BaiduTextClient,
    process_document_hierarchy
)

# 创建自定义文本客户端
client = BaiduTextClient(
    model="ernie-4.0-turbo-8k",
    api_key="your_api_key"  # 可选
)

# 使用自定义客户端
result = process_document_hierarchy(
    json_path="path/to/tagged.json",
    client=client,
    temperature=0.1
)
```

### 只提取章节标题（不调用 API）

```python
from tender_ontology.utils.document_struct import (
    load_tagged_document,
    extract_text_content
)

# 加载文档
lines_data = load_tagged_document("path/to/tagged.json")

# 提取章节标题
sections_text = extract_text_content(
    lines_data,
    include_sections_only=True
)

print(sections_text)
```

## API 参数说明

### `process_document_hierarchy()`

主要处理函数，完整的层级构建 Pipeline。

**参数:**

- `json_path` (str): 已标注的 JSON 文件路径
- `client` (optional): AI 客户端实例，默认自动创建
- `prompt_template` (str, optional): 提示词模板，默认使用 `DOCUMENT_HIERARCHY_PROMPT`
- `include_sections_only` (bool): 是否只分析章节标题，默认 `True`
- `temperature` (float): 温度参数，默认 `0.000001`
- `verbose` (bool): 是否显示详细信息，默认 `True`
- `save_results` (bool): 是否保存结果，默认 `True`
- `output_dir` (str, optional): 输出目录，默认与输入文件同目录

**返回值:**

```python
{
    "source_file": "path/to/input.json",
    "timestamp": "20251123_180000",
    "created_at": "2025-11-23T18:00:00",
    "include_sections_only": True,
    "hierarchy": {
        "section_headers": [...],      # 识别的章节列表
        "table_of_contents": {...},    # 目录树结构
        "summary": {...}                # 分析总结
    }
}
```

## 输出格式

AI 分析结果包含三个部分：

### 1. 章节标题列表 (section_headers)

```json
{
  "section_headers": [
    {
      "text": "第一章 招标公告",
      "hierarchy_level": 1,
      "hierarchy_reasoning": "全文主要章节，使用'第一章'格式",
      "line_number": 5
    },
    {
      "text": "一、项目基本信息",
      "hierarchy_level": 2,
      "hierarchy_reasoning": "第一章下的一级子标题，使用'一、'格式",
      "line_number": 15
    }
  ]
}
```

### 2. 目录树结构 (table_of_contents)

```json
{
  "table_of_contents": {
    "title": "文档目录",
    "children": [
      {
        "level": 1,
        "text": "第一章 招标公告",
        "line_number": 5,
        "children": [
          {
            "level": 2,
            "text": "一、项目基本信息",
            "line_number": 15,
            "children": []
          }
        ]
      }
    ]
  }
}
```

### 3. 分析总结 (summary)

```json
{
  "summary": {
    "total_headers": 34,
    "level_distribution": {
      "H1": 3,
      "H2": 12,
      "H3": 15,
      "H4": 4
    },
    "confidence": "high",
    "notes": [
      "文档结构清晰，使用标准的章节编号"
    ]
  }
}
```

## 完整示例

查看 `examples/hierarchy_example.py` 文件获取完整的使用示例。

```bash
# 运行示例
poetry run python examples/hierarchy_direct.py
```

## 工作流程

```
┌─────────────────────┐
│  已标注的 JSON 文件  │
│  (包含 class 字段)  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  提取纯文本内容      │
│  (章节标题或全文)   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  构建 AI 提示词      │
│  (使用 hierarchy    │
│   prompt 模板)      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  调用百度文本 API    │
│  (ERNIE-4.0-Turbo)  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  解析 JSON 响应      │
│  (章节列表 + 目录树) │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  保存结果到文件      │
│  (带时间戳)         │
└─────────────────────┘
```

## 相关工具

- `line_tagger.py`: 文档行级标签分类工具
- `baidu_text_client.py`: 百度千帆纯文本 API 客户端
- `document_hierarchy_prompt.py`: 文档层级分析提示词模板

## 注意事项

1. **输入文件要求**
   - 必须是已标注的 JSON 文件
   - 包含 `text`, `class`, `line_id`, `page` 等字段

2. **API 调用**
   - 使用纯文本 API，不需要图片
   - 默认使用 `ernie-4.0-turbo-8k` 模型
   - 支持自定义温度参数

3. **性能优化**
   - `include_sections_only=True` 可大幅减少文本长度
   - 适用于只需要目录结构的场景

4. **错误处理**
   - 如果 JSON 解析失败，会抛出详细错误信息
   - 建议设置 `verbose=True` 查看详细日志