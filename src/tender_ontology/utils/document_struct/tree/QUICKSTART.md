# 快速开始 - TreeConstructor

## 一分钟快速上手

```python
from tender_ontology.utils.document_struct import TreeConstructor

# 大模型预测的结果（包含 parent_id 和 left_sibling_id）
predictions = [
    {
        "id": 1,
        "heading_type": "section",
        "parent_id": 1,         # 指向自己 = 根节点
        "left_sibling_id": 1,
        "confidence": "high"
    },
    {
        "id": 5,
        "heading_type": "subsection",
        "parent_id": 1,         # 父节点是 id=1
        "left_sibling_id": 5,   # 指向自己 = 该层第一个
        "confidence": "high"
    }
]

# 创建树
constructor = TreeConstructor(verbose=True)
result = constructor.build_tree_from_predictions(predictions)

# 打印树结构
constructor.print_tree()

# 获取结果
print(result["summary"])
```

## 完整工作流程

### 方案 A：只使用树构建算法

如果你已经有了大模型的预测结果：

```python
from tender_ontology.utils.document_struct.tree import construct_tree_from_predictions

# 已有的预测结果
predictions = [...]  # 来自大模型

# 一行代码构建树
result = construct_tree_from_predictions(predictions, verbose=True)
```

### 方案 B：完整 Pipeline（关系预测 + 树构建）

从标注文件开始，完整构建层级树：

```python
from tender_ontology.utils.document_struct.hierarchy_relation import (
    process_document_hierarchy_relations
)
from tender_ontology.utils.document_struct.tree import TreeConstructor

# 步骤 1：调用大模型预测关系
hierarchy_result = process_document_hierarchy_relations(
    json_path="path/to/labeled.json",
    include_all_lines=False,
    verbose=True
)

predictions = hierarchy_result["result"]["predictions"]

# 步骤 2：使用树算法构建
constructor = TreeConstructor(verbose=True)
tree_result = constructor.build_tree_from_predictions(predictions)

# 步骤 3：可视化
constructor.print_tree(max_depth=3)
```

### 方案 C：使用集成示例脚本

直接运行提供的集成示例：

```bash
cd src/tender_ontology/utils/document_struct/tree
python example_integration.py
```

记得修改脚本中的 `json_path` 为你的文件路径。

## 输入数据格式

### predictions（必需）

大模型预测的标题列表：

```python
[
    {
        "id": 1,                    # 节点ID（行号）
        "heading_type": "section",  # 标题类型
        "parent_id": 1,             # 父节点ID（顶层节点指向自己）
        "left_sibling_id": 1,       # 左兄弟ID（最左节点指向自己）
        "confidence": "high",       # 置信度（high/medium/low）
        "reasoning": "..."          # 可选：预测理由
    }
]
```

**关键约束：**
- `parent_id` 和 `left_sibling_id` 必须 ≤ 当前 `id`（只能指向前面的标题）
- 顶层标题：`parent_id` 指向自己
- 每层最左标题：`left_sibling_id` 指向自己

### candidates_map（可选）

补充原始候选数据（文本、页码、特征等）：

```python
{
    "1": {
        "id": 1,
        "text": "第一章 项目概述",
        "page": 1,
        "features": {...}
    }
}
```

## 输出格式

```python
{
    "tree": [
        {
            "id": "1",
            "text": "第一章 项目概述",
            "level": 1,
            "heading_type": "section",
            "confidence": "high",
            "children": [
                {
                    "id": "5",
                    "text": "一、项目背景",
                    "level": 2,
                    "children": []
                }
            ]
        }
    ],
    "summary": {
        "total_headings": 20,
        "root_nodes": 3,
        "level_distribution": {
            "level_1": 3,
            "level_2": 10,
            "level_3": 7
        },
        "confidence_distribution": {
            "high": 15,
            "medium": 5
        }
    }
}
```

## 核心方法

### TreeConstructor.build_tree_from_predictions()

主要方法，构建层级树。

```python
result = constructor.build_tree_from_predictions(
    predictions,           # 必需：预测结果列表
    candidates_map=None    # 可选：候选项映射
)
```

### TreeConstructor.print_tree()

打印树结构（调试用）。

```python
constructor.print_tree(max_depth=3)  # 只打印前3层
```

## 常见问题

### Q: 如何获取 predictions？

A: 使用 `hierarchy_relation.py` 调用大模型：

```python
from tender_ontology.utils.document_struct.hierarchy_relation import (
    process_document_hierarchy_relations
)

result = process_document_hierarchy_relations(
    json_path="path/to/labeled.json"
)

predictions = result["result"]["predictions"]
```

### Q: 树算法和原始方法有什么区别？

A:
- **原始方法**（`construct_hierarchy_tree`）：直接根据 `parent_id` 构建父子关系
- **树算法**（`TreeConstructor`）：按论文的插入算法，逐个插入节点到最右支路

树算法更符合论文的原始设计，处理边界情况更稳健。

### Q: 如果预测结果不准确怎么办？

A: 可以：
1. 调整提示词（`document_relation_prediction_prompt.py`）
2. 使用更强大的模型
3. 手动修正预测结果后再构建树

### Q: 支持多个根节点吗？

A: 是的！算法自动处理多个根节点（多个 `parent_id` 指向自己的标题）。

## 下一步

- 查看 [README.md](README.md) 了解算法详情
- 查看 [example_integration.py](example_integration.py) 了解完整集成示例
- 查看论文：https://arxiv.org/pdf/2401.11874