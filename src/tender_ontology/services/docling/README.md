# Docling 文档处理服务

## 目录结构

```
docling/
├── __init__.py              # 服务导出
├── README.md               # 本文档
├── inference.py            # 文档推理服务（原 run_inference.py）
├── converter.py            # JSON 格式转换器
└── hierarchy.py            # 层级目录分析服务
```

## 服务说明

### 1. DoclingInferenceService (inference.py)

**功能：** 使用 Docling 进行 PDF/DOCX 文档推理

**输入：**
- PDF 或 DOCX 文件路径

**输出：**
- Markdown 格式
- 完整 JSON
- Section Headers JSON
- Labeled JSON
- Doctags

**使用示例：**

```python
from tender_ontology.services.docling import DoclingInferenceService

service = DoclingInferenceService()
results = service.infer("path/to/document.pdf")

# 结果包含：
# - results['markdown_path']
# - results['json_path']
# - results['labeled_path']
# - ...
```

### 2. LabeledJsonConverter (converter.py)

**功能：** 将 Docling 完整 JSON 转换为精简的 labeled 格式

**特点：**
- 合并 texts 和 tables
- 表格转换为 HTML 格式
- 保留核心字段：label, text, bbox, page_no

**使用示例：**

```python
from tender_ontology.services.docling import LabeledJsonConverter

converter = LabeledJsonConverter(debug=True)
labeled_data = converter.convert(docling_json)
```

### 3. HierarchyAnalyzer (hierarchy.py)

**功能：** 使用大模型进行文档层级分析

**输入：**
- Labeled JSON 数据

**输出：**
- 带层级标注的元素列表
- 层级目录树
- 分析摘要

**使用示例：**

```python
from tender_ontology.services.docling import HierarchyAnalyzer

analyzer = HierarchyAnalyzer(api_key="your-key")
hierarchy_result = analyzer.analyze(labeled_data)

# 结果包含：
# - hierarchy_result['annotated_items']
# - hierarchy_result['toc']
# - hierarchy_result['summary']
```

## 完整工作流

```python
from pathlib import Path
from tender_ontology.services.docling import (
    DoclingInferenceService,
    HierarchyAnalyzer
)

# 1. 文档推理
service = DoclingInferenceService()
results = service.infer("document.pdf")

# 2. 读取 labeled JSON
import json
with open(results['labeled_path']) as f:
    labeled_data = json.load(f)

# 3. 层级分析
analyzer = HierarchyAnalyzer(api_key="your-key")
hierarchy = analyzer.analyze(labeled_data)

# 4. 保存结果
output_path = Path("static/artifact/hierarchy/document_hierarchy.json")
output_path.write_text(json.dumps(hierarchy, ensure_ascii=False, indent=2))
```

## 配置

在 `.env` 文件中配置：

```env
# Docling 配置
DOCLING_OFFLINE_MODE=true
DOCLING_DISABLE_TABLE_RECOGNITION=false

# LLM API 配置
DOCLING_LLM_API_KEY=sk-xxx
DOCLING_LLM_MODEL=gpt-4o
```

## 依赖

需要在 `pyproject.toml` 中添加：

```toml
[tool.poetry.dependencies]
docling = "^2.61.0"
pypdfium2 = "^4.30.0"
requests = "^2.31.0"
```

## API 路由

参考 `routers/document.py` 中的 API 端点：

- `POST /documents/parse` - 解析文档
- `POST /documents/hierarchy` - 分析层级
- `GET /documents/{doc_id}/toc` - 获取目录树