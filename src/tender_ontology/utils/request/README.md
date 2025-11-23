# Request 工具类文档

本目录提供统一的 AI 请求工具类，包括基础客户端、批量管理和并发处理等功能。

---

## 📁 目录结构

```
app/utils/request/
├── __init__.py           # 模块导出
├── ai_client.py          # AI 请求客户端
├── batch_manager.py      # 批量请求管理器（基于 token 限制智能分批）
└── batch_processor.py    # 批量请求处理器（支持并发处理）
```

---

## 🔧 核心组件

### 1. AIClient (`ai_client.py`)

**功能**：提供统一的 AI 模型调用接口，支持 OpenAI 兼容的 API。

**主要特性**：
- 基于 OpenAI SDK 封装
- 支持自定义模型参数（temperature、max_tokens、top_p 等）
- 自动重试机制（默认最多重试 3 次）
- 详细的请求/响应日志

**默认配置**：
```python
{
    "model_name": "qwen3-14b",
    "base_url": "http://112.111.54.86:10011/v1",
    "temperature": 0.0,
    "max_tokens": 8192,
    "top_p": 1.0,
    "repetition_penalty": 1.0,
    "timeout": 60.0
}
```

**使用示例**：
```python
from app.utils.request import AIClient

# 创建客户端
client = AIClient()

# 发送请求
response = client.send_request(
    system_prompt="你是一个AI助手",
    user_prompt="1+1等于几？",
    temperature=0.1,
    max_tokens=100
)

# 安全发送请求（不会抛出异常）
response = client.send_request_safe(
    system_prompt="你是一个AI助手",
    user_prompt="1+1等于几？",
    default_response="抱歉，请求失败"
)

# 使用全局单例
from app.utils.request import get_global_client

client = get_global_client()
```

**主要方法**：
- `send_request()`: 发送 AI 请求（可能抛出异常）
- `send_request_safe()`: 安全发送请求（不会抛出异常，返回默认值）
- `create_request_body()`: 构建请求体（可单独使用）

---

### 2. BatchManager (`batch_manager.py`)

**功能**：基于 token 限制智能分批，避免超过模型上下文窗口。

**主要特性**：
- 使用 `tiktoken` 精确计算 token 数（如未安装，回退到字符估算）
- 自动计算固定开销（system_prompt、header、footer）
- 支持安全边际配置（默认预留 10%）

**默认配置**：
```python
{
    "max_context_tokens": 32768,    # 模型上下文窗口
    "max_output_tokens": 8192,      # 输出最大 token
    "safety_margin": 0.1,           # 安全边际 10%
    "encoding_name": "cl100k_base"  # tiktoken 编码
}
```

**使用示例**：
```python
from app.utils.request import BatchManager

# 创建管理器
manager = BatchManager(
    max_context_tokens=32768,
    max_output_tokens=8192
)

# 定义内容构建函数
def build_item_content(item):
    return f"## {item['title']}\n{item['content']}\n"

# 分批
batches = manager.split_items_by_tokens(
    items=items_list,
    system_prompt="你是一个助手",
    build_item_content_func=build_item_content,
    prompt_header="请处理以下内容:\n",
    prompt_footer="\n请输出 JSON 格式"
)

# 使用全局单例
from app.utils.request import get_default_batch_manager

manager = get_default_batch_manager()
```

**主要方法**：
- `split_items_by_tokens()`: 根据 token 限制智能分批
- `count_tokens()`: 计算文本的 token 数
- `estimate_tokens()`: 估算文本 token（别名方法）

---

### 3. BatchProcessor (`batch_processor.py`)

**功能**：处理分批发送和结果合并的通用逻辑，支持并发处理。

**主要特性**：
- 支持串行/并行处理（默认并行）
- 线程池并发（默认最多 10 个线程）
- 自动失败重试和错误处理
- 线程安全的日志输出

**使用示例**：
```python
from app.utils.request import BatchProcessor, AIClient, get_default_batch_manager

# 创建处理器
processor = BatchProcessor(
    ai_client=AIClient(),
    batch_manager=get_default_batch_manager(),
    verbose=True,
    max_workers=10  # 最大并发线程数
)

# 定义解析函数
def parse_response(response_text: str, context: dict) -> dict:
    import json
    # 解析 JSON 响应
    result = json.loads(response_text)
    return result

# 定义合并函数
def merge_results(all_results: list) -> dict:
    # 合并所有批次的结果
    merged = {
        "items": [],
        "total_count": 0
    }
    for result in all_results:
        merged["items"].extend(result.get("items", []))
    merged["total_count"] = len(merged["items"])
    return merged

# 准备批次数据
batches = [
    (system_prompt, user_prompt_1, context_1),
    (system_prompt, user_prompt_2, context_2),
    # ...
]

# 处理批次（并行）
final_result = processor.process_batches(
    batches=batches,
    parse_response_func=parse_response,
    merge_results_func=merge_results,
    parallel=True,  # 是否并行
    temperature=0.1  # 传递给 AIClient 的参数
)
```

**主要方法**：
- `process_batches()`: 处理多个批次（支持并行/串行）
- `_process_single_batch()`: 处理单个批次（内部方法）
- `_process_batches_serial()`: 串行处理（内部方法）

**内置工具函数**：
```python
from app.utils.request import merge_candidates_with_dedup

# 合并候选结果（带去重和排序）
merged = merge_candidates_with_dedup(
    all_results=all_results,
    candidates_key="candidates",
    id_key="id",
    score_key="score",
    verbose=True
)
```

---

## 🚀 完整工作流示例

以下是一个完整的批量处理流程示例：

```python
from app.utils.request import (
    AIClient,
    BatchManager,
    BatchProcessor,
    merge_candidates_with_dedup
)
import json

# 1. 准备数据
items = [
    {"id": 1, "text": "..."},
    {"id": 2, "text": "..."},
    # ... 数百个 items
]

# 2. 初始化组件
client = AIClient()
batch_manager = BatchManager(max_context_tokens=32768)
processor = BatchProcessor(
    ai_client=client,
    batch_manager=batch_manager,
    max_workers=10
)

# 3. 定义提示词
system_prompt = "你是一个文档分析专家"
prompt_header = "请分析以下文档块：\n"
prompt_footer = "\n请返回 JSON 格式的分析结果"

# 4. 定义内容构建函数
def build_item_content(item):
    return f"## Block {item['id']}\n{item['text']}\n"

# 5. 智能分批
batches_items = batch_manager.split_items_by_tokens(
    items=items,
    system_prompt=system_prompt,
    build_item_content_func=build_item_content,
    prompt_header=prompt_header,
    prompt_footer=prompt_footer
)

# 6. 构建批次请求
batches = []
for batch_items in batches_items:
    # 构建 user_prompt
    user_prompt = prompt_header
    for item in batch_items:
        user_prompt += build_item_content(item)
    user_prompt += prompt_footer

    # 添加批次
    context = {"batch_items": batch_items}
    batches.append((system_prompt, user_prompt, context))

# 7. 定义解析和合并函数
def parse_response(response_text: str, context: dict) -> dict:
    # 从代码块中提取 JSON
    if "```json" in response_text:
        json_str = response_text.split("```json")[1].split("```")[0].strip()
    else:
        json_str = response_text.strip()

    result = json.loads(json_str)
    return result

def merge_results(all_results: list) -> dict:
    return merge_candidates_with_dedup(
        all_results=all_results,
        candidates_key="candidates",
        id_key="id",
        score_key="score"
    )

# 8. 并行处理
final_result = processor.process_batches(
    batches=batches,
    parse_response_func=parse_response,
    merge_results_func=merge_results,
    parallel=True,
    temperature=0.0,
    max_tokens=8192
)

print(f"处理完成：{final_result['unique_candidates']} 个候选")
```

---

## 📝 实际使用案例

### 案例 1: H1 标题检测（参考 `app/prompts/docx/tag_prompt.py`）

```python
from app.utils.request import get_global_client, get_default_batch_processor

# 使用全局单例
client = get_global_client()
processor = get_default_batch_processor()

# ... 构建批次和处理逻辑
```

### 案例 2: 跨页单元格合并（参考 `app/prompts/cross_page_cell_prompts.py`）

批量判断跨页表格行是否应该合并，使用 `BatchProcessor` 并发处理提升效率。

---

## ⚙️ 配置建议

### Token 限制配置

不同模型的上下文窗口不同，需要相应调整：

| 模型 | max_context_tokens | max_output_tokens |
|------|-------------------|-------------------|
| qwen3-14b | 32768 | 8192 |
| gpt-3.5-turbo | 16384 | 4096 |
| gpt-4 | 8192 | 2048 |
| claude-2 | 100000 | 4096 |

### 并发配置

- **max_workers**: 根据 API 速率限制调整（默认 10）
- **并行 vs 串行**:
  - 并行：适合大量独立任务（如批量分类、检测）
  - 串行：适合有依赖关系或需要严格顺序的任务

### 重试配置

- **max_retries**: 最大重试次数（默认 3）
- **retry_delay**: 重试延迟秒数（默认 2.0）

---

## 🔍 常见问题

### 1. Token 超限怎么办？

增加 `safety_margin` 或减小 `max_output_tokens`：

```python
manager = BatchManager(
    max_context_tokens=32768,
    max_output_tokens=4096,  # 减小输出限制
    safety_margin=0.15        # 增加安全边际到 15%
)
```

### 2. 如何查看详细日志？

设置 `verbose=True`：

```python
client = AIClient()
response = client.send_request(
    system_prompt="...",
    user_prompt="...",
    verbose=True  # 打印详细日志
)
```

### 3. 如何自定义模型参数？

在 `send_request()` 中传递参数覆盖默认值：

```python
response = client.send_request(
    system_prompt="...",
    user_prompt="...",
    temperature=0.7,      # 覆盖默认值
    max_tokens=4096,      # 覆盖默认值
    top_p=0.9,            # 覆盖默认值
    model="gpt-4"         # 切换模型
)
```

### 4. 如何处理失败的批次？

`BatchProcessor` 会自动跳过失败的批次，继续处理其他批次。如果所有批次都失败，会抛出异常。

---

## 🎯 最佳实践

1. **使用全局单例**：避免重复创建客户端
   ```python
   from app.utils.request import get_global_client
   client = get_global_client()
   ```

2. **智能分批**：使用 `BatchManager` 避免手动计算 token
   ```python
   batches = batch_manager.split_items_by_tokens(...)
   ```

3. **并发处理**：对于独立任务，开启并行提升效率
   ```python
   processor.process_batches(..., parallel=True)
   ```

4. **异常处理**：使用 `send_request_safe()` 避免程序中断
   ```python
   response = client.send_request_safe(..., default_response="")
   ```

5. **日志控制**：生产环境关闭详细日志
   ```python
   processor = BatchProcessor(verbose=False)
   ```

---

## 📚 参考资料

- OpenAI API 文档: https://platform.openai.com/docs/api-reference
- tiktoken 文档: https://github.com/openai/tiktoken
- 项目内使用示例: `app/prompts/docx/tag_prompt.py`
