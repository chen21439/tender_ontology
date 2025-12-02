# 模型选择指南

## 🎯 快速选择

根据任务类型自动选择最优模型：

```python
from tender_ontology.config.model_config import TaskType

# 文档层级分析 -> ERNIE-Speed-8K（快速）
model = TaskType.HIERARCHY_PREDICTION.get_recommended_model()

# 文本生成 -> ERNIE-4.0-Turbo（平衡）
model = TaskType.TEXT_GENERATION.get_recommended_model()

# 简单分类 -> ERNIE-Lite-8K（轻量）
model = TaskType.BINARY_CLASSIFICATION.get_recommended_model()
```

## 📋 任务类型与推荐模型

| 任务类型 | 推荐模型 | 速度 | 适用场景 |
|---------|---------|------|---------|
| **文档结构分析** | | | |
| `HIERARCHY_PREDICTION` | ERNIE-Speed-8K | ⚡⚡⚡ 快 | 标题层级关系预测（parent_id, left_sibling_id） |
| `SECTION_CLASSIFICATION` | ERNIE-Speed-8K | ⚡⚡⚡ 快 | 段落分类（标题/正文/表格） |
| **文本生成** | | | |
| `TEXT_GENERATION` | ERNIE-4.0-Turbo | ⚡⚡ 中等 | 通用文本生成 |
| `SUMMARIZATION` | ERNIE-4.0-Turbo | ⚡⚡ 中等 | 文本摘要 |
| **分类判断** | | | |
| `BINARY_CLASSIFICATION` | ERNIE-Lite-8K | ⚡⚡⚡ 快 | 二分类（是/否） |
| `MULTI_CLASSIFICATION` | ERNIE-Lite-8K | ⚡⚡⚡ 快 | 多分类 |
| **推理任务** | | | |
| `SIMPLE_REASONING` | ERNIE-4.0-Turbo | ⚡⚡ 中等 | 简单推理 |
| `COMPLEX_REASONING` | ERNIE-4.0-Turbo | ⚡⚡ 中等 | 复杂推理 |

## ⚠️ 性能对比：Thinking vs Speed

**真实案例**（244 个候选项的层级分析）：

| 模型 | 耗时 | 备注 |
|-----|------|------|
| ERNIE-5.0-Thinking | **115.72 秒** | ❌ 太慢！输出还被截断 |
| ERNIE-Speed-8K | **预计 10-20 秒** | ✅ 推荐使用 |
| ERNIE-Lite-8K | **预计 5-10 秒** | ✅ 更快，但质量可能略低 |

**结论**：
- ❌ **不要用 Thinking 模型做结构化输出任务！**
- ✅ **层级分析用 Speed 模型，速度提升 5-10 倍**

## 🔧 使用方法

### 方法 1：使用 DefaultModels（推荐）

```python
from tender_ontology.config.model_config import DefaultModels
from tender_ontology.utils.document_struct import BaiduTextClient

# 自动使用最优模型
client = BaiduTextClient(model=DefaultModels.DOCUMENT_HIERARCHY)
```

### 方法 2：直接指定模型

```python
from tender_ontology.config.model_config import BaiduModel
from tender_ontology.utils.document_struct import BaiduTextClient

# 手动选择
client = BaiduTextClient(model=BaiduModel.ERNIE_SPEED_8K)
```

### 方法 3：通过任务类型选择

```python
from tender_ontology.config.model_config import TaskType
from tender_ontology.utils.document_struct import BaiduTextClient

# 根据任务自动选择
task = TaskType.HIERARCHY_PREDICTION
client = BaiduTextClient(model=task.get_recommended_model())
```

## 📊 模型详细信息

### ERNIE-Speed 系列

- **ERNIE-Speed-8K**: 快速模型，适合结构化输出
  - 上下文: 8K tokens
  - 速度: 非常快
  - 成本: 低
  - 适用: 分类、标注、结构化生成

- **ERNIE-Speed-128K**: 长文本版本
  - 上下文: 128K tokens
  - 适用: 长文档分析

### ERNIE-Lite 系列

- **ERNIE-Lite-8K**: 轻量级模型
  - 上下文: 8K tokens
  - 速度: 极快
  - 成本: 很低
  - 适用: 简单分类、是非判断

### ERNIE-4.0 系列

- **ERNIE-4.0-Turbo-8K**: 平衡性能和质量
  - 上下文: 8K tokens
  - 速度: 中等
  - 质量: 高
  - 适用: 通用场景、文本生成、摘要

### ERNIE-Thinking 系列

- **ERNIE-5.0-Thinking-Latest**: 复杂推理模型
  - 上下文: 128K tokens
  - 速度: **很慢**（不推荐用于生产）
  - 质量: 非常高
  - 适用: **仅限需要多步推理的复杂任务**

## 💡 最佳实践

### ✅ 推荐做法

1. **文档层级分析**：使用 `ERNIE-Speed-8K`
   ```python
   # 速度快 5-10 倍，质量足够
   model = TaskType.HIERARCHY_PREDICTION.get_recommended_model()
   ```

2. **批量处理**：使用 `ERNIE-Lite-8K`
   ```python
   # 大量简单任务，追求速度和成本
   model = BaiduModel.ERNIE_LITE_8K
   ```

3. **通用场景**：使用 `ERNIE-4.0-Turbo`
   ```python
   # 平衡质量和速度
   model = BaiduModel.ERNIE_4_0_TURBO_8K
   ```

### ❌ 避免的做法

1. ❌ **用 Thinking 模型做结构化输出**
   ```python
   # 错误：太慢了！
   model = BaiduModel.ERNIE_5_0_THINKING_LATEST  # 115 秒
   ```

2. ❌ **用轻量模型做复杂推理**
   ```python
   # 错误：质量不够
   model = BaiduModel.ERNIE_LITE_8K  # 对于复杂推理
   ```

## 🚀 性能优化建议

### 问题：响应时间太长

**症状**: API 调用超过 30 秒

**解决方案**:
1. 检查是否误用了 Thinking 模型
2. 改用 Speed 或 Lite 模型
3. 减少输入 tokens（分批处理）

### 问题：输出被截断

**症状**: JSON 解析失败，`Unterminated string`

**解决方案**:
1. 增加 `max_tokens` 参数（默认 8192）
2. 分批处理候选项（每批 50-80 个）
3. 简化输出格式

### 问题：质量不够

**症状**: 预测准确率低

**解决方案**:
1. 从 Lite 升级到 Speed
2. 从 Speed 升级到 4.0-Turbo
3. 优化提示词

## 📈 成本与速度权衡

| 场景 | 候选模型 | 预计耗时 | 相对成本 |
|-----|---------|---------|---------|
| 244 个标题分析 | ERNIE-Lite-8K | 5-10 秒 | 💰 低 |
| 244 个标题分析 | ERNIE-Speed-8K | 10-20 秒 | 💰💰 中 |
| 244 个标题分析 | ERNIE-4.0-Turbo | 20-40 秒 | 💰💰💰 高 |
| 244 个标题分析 | ERNIE-Thinking | **115+ 秒** | 💰💰💰💰 很高 |

**建议**:
- 开发/测试：使用 `ERNIE-Speed-8K`
- 生产环境：根据质量要求在 `Speed` 和 `4.0-Turbo` 之间选择
- **永远不要用 Thinking 做结构化输出！**

## 🔗 相关资源

- [百度千帆模型文档](https://cloud.baidu.com/doc/WENXINWORKSHOP/index.html)
- 项目配置: `src/tender_ontology/config/model_config.py`
- 使用示例: `src/tender_ontology/utils/document_struct/hierarchy_relation.py`