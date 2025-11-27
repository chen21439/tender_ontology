# Docling 层级修正处理器

基于 `docling-hierarchical-pdf` 的层级修正工具，用于优化 Docling 的文档层级结构。

## 功能

- ✅ 从 PDF 元数据（TOC）提取层级
- ✅ 基于标题编号推断层级（支持数字、字母、罗马数字）
- ✅ 基于样式聚类推断层级（字体大小、粗体、斜体）
- ✅ 自动修正 Docling 文档树结构

## 快速使用

### 方式1：自动集成（推荐）

使用 `DoclingInferenceService`，已自动集成层级修正：

```python
from tender_ontology.services.docling.inference import DoclingInferenceService

service = DoclingInferenceService(hierarchy_refinement=True)
result = service.infer("document.pdf")
```

### 方式2：手动使用

```python
from docling.document_converter import DocumentConverter
from tender_ontology.utils.document_struct.docling_post_process import HierarchyProcessor

# 转换文档
converter = DocumentConverter()
result = converter.convert("document.pdf")

# 层级修正
processor = HierarchyProcessor(debug=True)
processor.process(result, source="document.pdf")

# result.document 现在包含修正后的层级
```

## API

### HierarchyProcessor

```python
processor = HierarchyProcessor(
    raise_on_error=False,  # 出错时是否抛异常
    debug=False            # 是否打印调试信息
)
```

#### 主要方法

**1. process(result, source=None)**

修正 Docling 结果的层级结构（主要入口）

```python
processor.process(result, source="document.pdf")
```

**2. extract_toc(result, source=None)**

提取 PDF 目录

```python
toc = processor.extract_toc(result, source="document.pdf")
# [(level, title, page, info), ...]
```

**3. build_hierarchy_from_metadata(result, source=None)**

从 PDF 元数据构建层级树

```python
root = processor.build_hierarchy_from_metadata(result, source="document.pdf")
print(root)  # 打印树结构
```

**4. build_hierarchy_from_style(headings)**

从样式构建层级树

```python
headers = processor.extract_headers(result)
root = processor.build_hierarchy_from_style(headers)
```

**5. extract_headers(result)**

提取标题信息

```python
headers = processor.extract_headers(result)
# [{"text": "...", "font_size": 14.0, "is_bold": True, ...}, ...]
```

## 工作原理

### 层级推断策略（优先级递减）

1. **PDF 元数据**：从 PDF TOC 提取（最准确）
2. **标题编号**：识别数字、字母、罗马数字编号
3. **样式聚类**：DBSCAN 聚类字体大小（回退方案）

### 修正流程

```
PDF 文档
    ↓
Docling 转换
    ↓
HierarchyProcessor.process()
    ├─ 提取/推断层级树
    ├─ 转换项类型 (TextItem ↔ SectionHeaderItem)
    ├─ 分配层级编号 (level 1-6)
    └─ 重组文档树结构
    ↓
修正后的文档
```

## 配置

在 `.env` 或 `docling_settings.py` 中配置：

```python
# 是否启用层级修正
hierarchy_refinement: bool = True

# 出错时是否抛异常
hierarchy_raise_on_error: bool = False
```

## 依赖

需要将 `docling-hierarchical-pdf-main` 放在项目根目录。

结构：
```
tender_ontology/
├── docling-hierarchical-pdf-main/
│   └── hierarchical/
│       ├── enums.py
│       ├── parsers.py
│       ├── hierarchy_builder.py
│       ├── hierarchy_builder_metadata.py
│       ├── postprocessor.py
│       └── types/
└── src/tender_ontology/
    └── utils/document_struct/
        └── docling_post_process/
            ├── __init__.py
            ├── hierarchy_processor.py
            └── README.md (本文件)
```

## 故障排查

### 模块不可用

如果看到 "hierarchical 模块不可用"：

1. 检查 `docling-hierarchical-pdf-main` 目录位置
2. 确保目录结构正确
3. 查看 `hierarchy_processor.py` 中的 `HIERARCHICAL_PDF_DIR` 路径

### 层级修正无效

1. 启用调试模式：`HierarchyProcessor(debug=True)`
2. 检查提取的标题：`processor.extract_headers(result)`
3. 尝试手动指定 source 参数

## 示例

查看 `docling-hierarchical-pdf-main/hierarchical/CLASSES_OVERVIEW.md` 了解更多技术细节。
