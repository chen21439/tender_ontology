# Tree Constructor - 树构建算法

## 算法流程

### 输入

大模型预测的标题列表（按阅读顺序排列）：

```json
[
  {
    "id": 1,
    "is_heading": true,
    "heading_type": "section",
    "parent_id": 1,         // 谁是我的父节点
    "left_sibling_id": 1,   // 谁是我的左兄弟
    "confidence": "high",
    "reasoning": "第一章标题，顶层节点"
  },
  {
    "id": 5,
    "is_heading": true,
    "heading_type": "subsection",
    "parent_id": 1,         // 父节点是 id=1
    "left_sibling_id": 5,   // 指向自己 = 该层第一个
    "confidence": "high",
    "reasoning": "编号为'一、'，是第一章的第一个小节"
  },
  // ...
]
```

**关键约束：**
- `parent_id` 和 `left_sibling_id` 只能指向**前面**的标题（j < i）
- 如果是顶层标题，`parent_id` 指向自己
- 如果是该层最左边的标题，`left_sibling_id` 指向自己

### 核心算法：Tree Insertion Algorithm

```
初始化：空树 T = {}

对于每个标题 sec_i (按阅读顺序):
    1. 获取当前树的「最右支路」candidates
       - 从每个根节点开始，沿着最右子节点走到叶子
       - 这些节点是可能的插入位置

    2. 对每个候选节点 sec_r，计算匹配得分:
       - parent_match = (sec_r.id == sec_i.parent_id)
       - sibling_match = (sec_r 是 sec_i.left_sibling 的父节点)

    3. 选择得分最高的候选节点 sec_best

    4. 将 sec_i 插入为 sec_best 的最右子节点

    5. 更新树 T

处理完所有标题后，计算每个节点的 level
```

### 输出

层级树结构：

```json
{
  "tree": [
    {
      "id": 1,
      "text": "第一章 项目概述",
      "level": 1,
      "children": [
        {
          "id": 5,
          "text": "一、项目背景",
          "level": 2,
          "children": []
        },
        {
          "id": 10,
          "text": "二、项目目标",
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
    }
  }
}
```

---

## 使用方法

### 基础用法

```python
from tender_ontology.utils.document_struct.tree import TreeConstructor

# 创建树构建器
constructor = TreeConstructor(verbose=True)

# 从大模型预测结果构建树
predictions = [
    {
        "id": 1,
        "is_heading": True,
        "heading_type": "section",
        "parent_id": 1,
        "left_sibling_id": 1,
        "confidence": "high",
        "reasoning": "第一章标题"
    },
    # ... 更多预测
]

result = constructor.build_tree_from_predictions(predictions)
```

### 包含原始候选数据

如果你有原始的候选项数据（包含文本、页码、特征等），可以传入 `candidates_map`：

```python
candidates_map = {
    "1": {
        "id": 1,
        "text": "第一章 项目概述",
        "page": 1,
        "features": {
            "font_size_level": 2,
            "is_bold": True,
            "numbering_pattern": "第X章"
        }
    },
    # ... 更多候选项
}

result = constructor.build_tree_from_predictions(
    predictions,
    candidates_map=candidates_map
)
```

### 打印树结构（调试）

```python
# 打印完整树结构
constructor.print_tree()

# 只打印前3层
constructor.print_tree(max_depth=3)
```

输出示例：

```
================================================================================
树结构预览:
================================================================================

根节点 #1:
[L1] 1: 第一章 项目概述 (section)
  ├─ [L2] 5: 一、项目背景 (subsection)
  └─ [L2] 10: 二、项目目标 (subsection)
      └─ [L3] 15: （一）总体目标 (subsubsection)

根节点 #2:
[L1] 20: 第二章 技术方案 (section)
  └─ [L2] 25: 一、技术架构 (subsection)
================================================================================
```

### 便捷函数

```python
from tender_ontology.utils.document_struct.tree import construct_tree_from_predictions

# 一行代码构建树
result = construct_tree_from_predictions(
    predictions,
    candidates_map=candidates_map,
    verbose=True
)
```

---

## 完整示例：与 hierarchy_relation 集成

```python
from tender_ontology.utils.document_struct.hierarchy_relation import (
    process_document_hierarchy_relations
)
from tender_ontology.utils.document_struct.tree import TreeConstructor

# 第一步：使用 hierarchy_relation 获取预测结果
hierarchy_result = process_document_hierarchy_relations(
    json_path="path/to/tagged.json",
    include_all_lines=False,  # 只分析 Section
    verbose=True
)

# 第二步：提取预测数据
predictions = hierarchy_result["result"]["predictions"]

# 第三步：构建候选项映射（可选）
from tender_ontology.utils.document_struct.hierarchy_relation import (
    load_tagged_document,
    extract_heading_candidates
)

lines_data = load_tagged_document("path/to/tagged.json")
candidates = extract_heading_candidates(lines_data, include_all_lines=False)
candidates_map = {str(c["id"]): c for c in candidates}

# 第四步：构建树
constructor = TreeConstructor(verbose=True)
tree_result = constructor.build_tree_from_predictions(
    predictions,
    candidates_map=candidates_map
)

# 第五步：可视化
constructor.print_tree(max_depth=3)

# 第六步：获取结果
print(f"总标题数: {tree_result['summary']['total_headings']}")
print(f"根节点数: {tree_result['summary']['root_nodes']}")
print(f"层级分布: {tree_result['summary']['level_distribution']}")
```

---

## API 参考

### TreeConstructor

主要的树构建器类。

#### 构造函数

```python
TreeConstructor(verbose: bool = True)
```

#### 方法

##### `build_tree_from_predictions()`

从预测结果构建层级树。

```python
def build_tree_from_predictions(
    predictions: List[Dict[str, Any]],
    candidates_map: Optional[Dict[str, Dict[str, Any]]] = None
) -> Dict[str, Any]
```

**参数：**
- `predictions`: 大模型预测的标题列表
- `candidates_map`: 可选的候选项映射（id -> 原始数据）

**返回：**
```python
{
    "tree": [...],           # 树结构列表
    "summary": {
        "total_headings": 20,
        "root_nodes": 3,
        "level_distribution": {...},
        "confidence_distribution": {...}
    }
}
```

##### `print_tree()`

打印树结构（调试用）。

```python
def print_tree(max_depth: Optional[int] = None)
```

**参数：**
- `max_depth`: 最大打印深度，None 表示打印所有层级

---

### TreeNode

树节点类。

#### 属性

- `id`: 节点ID（字符串）
- `text`: 标题文本
- `heading_type`: 标题类型（section/subsection/...）
- `parent_id`: 父节点ID（预测值）
- `left_sibling_id`: 左兄弟ID（预测值）
- `confidence`: 置信度（high/medium/low）
- `reasoning`: 预测理由
- `page`: 页码
- `features`: 特征字典
- `parent`: 父节点（TreeNode）
- `children`: 子节点列表（List[TreeNode]）
- `level`: 树的层级（int）

#### 方法

```python
# 添加子节点
node.add_child(child_node)

# 获取最右子节点
rightmost = node.get_rightmost_child()

# 转换为字典
node_dict = node.to_dict(include_children=True)
```

---

## 与论文的对应关系

| 论文算法                           | 代码实现                                    |
|-----------------------------------|-------------------------------------------|
| Tree Insertion Algorithm          | `_insert_nodes_in_order()`                |
| 获取最右支路 (rightmost path)      | `_get_rightmost_path()`                   |
| 融合 parent + sibling 打分         | `_find_best_insertion_point()`            |
| 插入为最右子节点                    | `best_candidate.add_child(node)`          |
| 计算层级 level                     | `_calculate_levels()`                     |

---

## 注意事项

### 1. 输入约束

- `predictions` 必须按**阅读顺序**排列（从上到下）
- `parent_id` 和 `left_sibling_id` 必须指向前面的标题
- 顶层标题的 `parent_id` 必须指向自己

### 2. 简化版本

当前实现是论文算法的简化版本：

- **论文原版**：使用小模型输出的 `s^p` 和 `s^s` 打分矩阵
- **当前版本**：只使用大模型预测的 `parent_id` 和 `left_sibling_id`（布尔匹配）

这样做的好处：
- 不需要训练小模型
- 直接使用大模型的输出
- 实现简单，效果不错

### 3. 扩展方向

如果需要更精细的控制，可以：

1. **添加打分矩阵**：从小模型获取每个候选位置的得分
2. **融合多个信号**：结合编号模式、字号、语义等多种特征
3. **后处理优化**：对构建好的树进行微调（如合并孤立节点）

---

## 相关文件

- `tree_construct.py`: 主要实现文件
- `../hierarchy_relation.py`: 大模型关系预测模块
- `../../prompts/document_struct/document_relation_prediction_prompt.py`: 提示词模板

---

## 测试

运行内置测试：

```bash
cd src/tender_ontology/utils/document_struct/tree
python tree_construct.py
```

这会运行一个简单的 4 节点示例，并打印树结构。