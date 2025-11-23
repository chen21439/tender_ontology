# Docling 文档处理使用指南

## 概述

Docling 文档处理模块提供了以下功能：

1. **文档解析**: 将 PDF/DOCX 文档转换为 Markdown、JSON、Labeled JSON 等格式
2. **层级分析**: 使用大模型 API 对文档标题进行语义分析，构建层级目录树
3. **完整流程**: 一键执行解析 + 层级分析

## 环境配置

### 1. 安装依赖

```bash
cd E:\programFile\AIProgram\tender_ontology
poetry install
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```env
# Docling 配置
DOCLING_OFFLINE_MODE=true                    # 是否离线模式
DOCLING_DISABLE_TABLE_RECOGNITION=false      # 是否禁用表格识别
DOCLING_HIERARCHY_REFINEMENT=false           # 是否启用层级修正

# 输出目录
DOCLING_OUTPUT_BASE_DIR=./outputs/docling
DOCLING_HIERARCHY_OUTPUT_DIR=./outputs/hierarchy

# LLM API 配置（用于层级分析）
DOCLING_LLM_API_KEY=sk-your-api-key-here
DOCLING_LLM_API_BASE=https://api.openai.com/v1
DOCLING_LLM_MODEL=gpt-4o
```

**重要说明**:
- `DOCLING_DISABLE_TABLE_RECOGNITION=false`: 必须启用表格识别才能正确解析表格内容
- 层级分析需要 LLM API，使用 OpenAI API 格式（不需要本地 PyTorch）

## 使用方法

### 方式一：文档解析（单独）

只进行文档解析，生成 Markdown、JSON、Labeled JSON 等格式。

```bash
# 基本用法
poetry run python -m tender_ontology.scripts.run_docling_inference --file document.pdf

# 指定输出目录
poetry run python -m tender_ontology.scripts.run_docling_inference \
    --file document.pdf \
    --output-dir ./my_outputs

# 只生成 Markdown 和 Labeled JSON
poetry run python -m tender_ontology.scripts.run_docling_inference \
    --file document.docx \
    --no-json

# 生成所有格式（包括 doctags）
poetry run python -m tender_ontology.scripts.run_docling_inference \
    --file document.pdf \
    --doctags

# 离线模式 + 禁用表格识别（快速模式）
poetry run python -m tender_ontology.scripts.run_docling_inference \
    --file document.pdf \
    --offline \
    --no-table-recognition
```

**输出文件**:
- `document_20250101_120000.md` - Markdown 格式
- `document_20250101_120000.json` - 完整 JSON
- `document_20250101_120000_labeled.json` - 精简的 Labeled JSON
- `document_20250101_120000.doctags` - Doctags 格式（可选）

### 方式二：层级分析（单独）

对已有的 Labeled JSON 进行层级分析。

```bash
# 基本用法
poetry run python -m tender_ontology.scripts.run_hierarchy_analysis \
    --file artifact/docling/document_20250101_120000_labeled.json

# 指定输出路径
poetry run python -m tender_ontology.scripts.run_hierarchy_analysis \
    --file document_labeled.json \
    --output result_hierarchy.json

# 使用自定义 API 配置
poetry run python -m tender_ontology.scripts.run_hierarchy_analysis \
    --file document_labeled.json \
    --api-key sk-xxx \
    --api-base https://api.openai.com/v1 \
    --model gpt-4o
```

**输出文件**:
- `document_20250101_120000_labeled_hierarchy.json` - 包含层级标注和目录树

**输出格式**:
```json
{
  "annotated_items": [
    {
      "id": 0,
      "text": "第一章 招标公告",
      "level": 1,
      "reasoning": "主章节，使用'第一章'格式"
    }
  ],
  "toc": {
    "children": [
      {
        "id": 0,
        "level": 1,
        "text": "第一章 招标公告",
        "page": 1,
        "children": []
      }
    ]
  },
  "summary": {
    "total": 34,
    "distribution": {"H1": 3, "H2": 12, "H3": 15, "H4": 4},
    "confidence": "high",
    "notes": ["结构清晰，编号规范"]
  }
}
```

### 方式三：完整流程（推荐）

一键执行文档解析 + 层级分析。

```bash
# 基本用法（解析 + 层级分析）
poetry run python -m tender_ontology.scripts.run_full_pipeline --file document.pdf

# 只进行解析，不做层级分析
poetry run python -m tender_ontology.scripts.run_full_pipeline \
    --file document.pdf \
    --no-hierarchy

# 离线模式（仅解析部分）
poetry run python -m tender_ontology.scripts.run_full_pipeline \
    --file document.pdf \
    --offline

# 使用自定义 LLM API
poetry run python -m tender_ontology.scripts.run_full_pipeline \
    --file document.pdf \
    --api-key sk-xxx \
    --model gpt-4o
```

## 在 Python 代码中使用

除了命令行脚本，也可以直接在代码中导入使用：

```python
from pathlib import Path
from tender_ontology.services.docling import DoclingInferenceService, HierarchyAnalyzer

# 1. 文档解析
service = DoclingInferenceService(
    offline_mode=True,
    disable_table_recognition=False
)

results = service.infer(
    file_path=Path("document.pdf"),
    save_markdown=True,
    save_json=True,
    save_labeled=True
)

print(f"Markdown: {results['markdown_path']}")
print(f"Labeled JSON: {results['labeled_path']}")

# 2. 层级分析
import json

with open(results['labeled_path'], encoding='utf-8') as f:
    labeled_data = json.load(f)

analyzer = HierarchyAnalyzer(
    api_key="sk-xxx",
    api_base="https://api.openai.com/v1",
    model="gpt-4o"
)

hierarchy_result = analyzer.analyze(labeled_data)
print(f"总标题数: {hierarchy_result['summary']['total']}")
print(f"层级分布: {hierarchy_result['summary']['distribution']}")
```

## Labeled JSON 格式说明

Labeled JSON 是简化后的格式，包含以下字段：

```json
{
  "document_name": "document",
  "total_items": 150,
  "items": [
    {
      "id": 0,
      "label": "section_header",
      "text": "第一章 总则",
      "page_no": 1,
      "bbox": {"l": 100, "t": 200, "r": 500, "b": 250}
    },
    {
      "id": 1,
      "label": "text",
      "text": "本招标文件依据...",
      "page_no": 1,
      "bbox": {"l": 100, "t": 300, "r": 500, "b": 400}
    },
    {
      "id": 2,
      "label": "table",
      "text": "<table><tr><th>项目</th><th>金额</th></tr><tr><td>总价</td><td>1000万元</td></tr></table>",
      "page_no": 2,
      "bbox": {"l": 100, "t": 100, "r": 500, "b": 500}
    }
  ]
}
```

**字段说明**:
- `label`: 元素类型（section_header/text/list_item/table）
- `text`: 文本内容（表格为 HTML 格式）
- `bbox`: 边界框坐标 {left, top, right, bottom}
- `page_no`: 页码

**表格 HTML 格式**:
```html
<table>
  <tr>
    <th rowspan="2">表头</th>
    <td colspan="2">数据</td>
  </tr>
  <tr>
    <td>单元格1</td>
    <td>单元格2</td>
  </tr>
</table>
```

## 层级分析规则

大模型使用以下规则进行层级判断（优先级递减）：

### 1. 编号规则
- **H1**: 第X章、第X部分、第X册
- **H2**: 第X节、X.、（X）、X、
- **H3**: X.X、X)、①②③
- **H4**: X.X.X、(X)、a)b)c)

### 2. 语义重要性
- 全局概念 → 高层级
- 具体细节 → 低层级

### 3. 位置规律
- 章节开头通常是高层级
- 相似格式的标题通常同级

## 常见问题

### Q: 表格单元格为空？

**A**: 确保 `DOCLING_DISABLE_TABLE_RECOGNITION=false`。表格识别必须启用才能正确解析表格内容。

### Q: 层级分析失败？

**A**: 检查以下几点：
1. 是否设置了 `DOCLING_LLM_API_KEY`
2. API 是否可访问（网络连接）
3. 是否有足够的 API 配额

### Q: 离线模式下缺少模型？

**A**: 首次运行需要联网下载模型到本地缓存。之后可以离线使用：
```bash
# 首次运行（联网）
poetry run python -m tender_ontology.scripts.run_docling_inference --file document.pdf

# 之后离线运行
poetry run python -m tender_ontology.scripts.run_docling_inference --file document.pdf --offline
```

### Q: 想要加速推理？

**A**: 可以禁用表格识别和层级修正：
```bash
poetry run python -m tender_ontology.scripts.run_docling_inference \
    --file document.pdf \
    --offline \
    --no-table-recognition
```

**注意**: 禁用表格识别后，表格只会被识别为整体区域，不会解析单元格内容。

## 技术架构

```
tender_ontology/
├── src/tender_ontology/
│   ├── config/
│   │   └── docling_settings.py          # 配置管理
│   ├── services/docling/
│   │   ├── __init__.py                   # 导出服务类
│   │   ├── converter.py                  # LabeledJsonConverter
│   │   ├── inference.py                  # DoclingInferenceService
│   │   └── hierarchy.py                  # HierarchyAnalyzer
│   ├── prompts/
│   │   └── hierarchy_construction.txt    # 层级分析提示词
│   └── scripts/
│       ├── run_docling_inference.py      # 文档解析脚本
│       ├── run_hierarchy_analysis.py     # 层级分析脚本
│       └── run_full_pipeline.py          # 完整流程脚本
├── .env                                   # 环境配置
└── pyproject.toml                         # 依赖管理
```

## 依赖说明

- **docling** (>=2.61.1): 文档解析核心库
- **pypdfium2** (>=4.30.1): PDF 处理后端
- **requests** (>=2.32.5): HTTP 请求（LLM API）
- **pydantic-settings** (>=2.12.0): 配置管理

**不需要**:
- PyTorch: 层级分析使用 API，不需要本地推理
- transformers: 不使用本地模型