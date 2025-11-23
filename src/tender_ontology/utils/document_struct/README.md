# 百度文心一言图像理解工具

简化版的百度图像理解客户端，核心流程：**拿 token → 拼 URL → 组 messages（图 + 文）→ 用 `requests` 发 POST 拿结果**

---

## 快速开始

### 1. 基础调用

```python
from app.utils.AIDocument import BaiduImageClient

# 初始化客户端（access_token 由外部提供）
client = BaiduImageClient(
    access_token="your_access_token_here",
    api_name="ernie-4.0-turbo-128k-preview"  # 可选，默认值
)

# 发送请求
response = client.send_request(
    prompt="请描述这张图片的内容",
    image_path="path/to/image.jpg"
)

print(response)
```

### 2. 带 JSON 数据的调用

```python
from app.utils.AIDocument import BaiduImageClient
from app.prompts.AIDocument.image_understanding_prompt import (
    DOCUMENT_IMAGE_WITH_JSON_PROMPT
)

client = BaiduImageClient(access_token="your_token")

# 准备 JSON 数据（如从 PDF 提取的 lines）
lines_data = {
    "lines": [
        {"id": 1, "text": "第一章", "bbox": [100, 50, 200, 80]},
        {"id": 2, "text": "内容...", "bbox": [100, 100, 500, 120]}
    ]
}

# 调用（JSON 数据会被插入到 prompt 中）
response = client.send_request_with_json(
    prompt_template=DOCUMENT_IMAGE_WITH_JSON_PROMPT,
    image_path="path/to/page.jpg",
    json_data=lines_data
)

print(response)
```

---

## 核心组件

### BaiduImageClient

**初始化参数：**
- `access_token`: 百度API的access_token（必需，由外部提供）
- `api_name`: API服务名称（可选，默认 `"ernie-4.0-turbo-128k-preview"`）

**主要方法：**

#### `send_request()`
发送基础图像理解请求

```python
client.send_request(
    prompt="你的提示词",
    image_path="图片路径",
    temperature=0.01,  # 温度参数，越小越确定
    top_p=0.8,         # top_p参数
    verbose=True       # 是否打印详细日志
)
```

#### `send_request_with_json()`
发送带 JSON 数据的请求

```python
client.send_request_with_json(
    prompt_template="包含 {json_data} 占位符的提示词模板",
    image_path="图片路径",
    json_data={"key": "value"},  # 会被序列化后插入到 prompt
    temperature=0.01,
    top_p=0.8,
    verbose=True
)
```

---

## 提示词模板

位置：`app/prompts/AIDocument/image_understanding_prompt.py`

### 可用模板

1. **`BASIC_IMAGE_PROMPT`** - 基础图像理解
   - 用途：描述图片的主要内容、布局、关键元素

2. **`DOCUMENT_IMAGE_WITH_JSON_PROMPT`** - 文档图像+JSON数据
   - 用途：结合图片和文本行数据分析文档结构
   - 需要配合 `send_request_with_json()` 使用

3. **`TABLE_RECOGNITION_PROMPT`** - 表格识别
   - 用途：识别表格的行列、表头、单元格内容
   - 输出：JSON 格式的表格数据

4. **`HEADING_RECOGNITION_PROMPT`** - 标题层级识别
   - 用途：识别文档中的标题及其层级
   - 输出：JSON 格式的标题列表

### 自定义提示词

```python
from app.prompts.AIDocument.image_understanding_prompt import build_custom_prompt

prompt = build_custom_prompt(
    task_description="识别图片中的所有文字并按位置排序",
    context="这是一张扫描的合同文档",
    output_format="JSON格式，包含文字内容和坐标"
)
```

---

## 核心流程说明

### 1. 拼 URL

```python
url = f"https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chatv/{api_name}?access_token={access_token}"
```

### 2. 组 messages

按照百度官方文档的格式：

```python
messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "你的提示词"
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/jpeg;base64,xxx"  # base64 编码的图片
                }
            }
        ]
    }
]
```

### 3. 发 POST 请求

```python
payload = {
    "messages": messages,
    "temperature": 0.01,
    "top_p": 0.8,
    "stream": False
}

response = requests.post(url, headers=headers, json=payload, timeout=120)
result = response.json()
answer = result.get("result", "")
```

---

## 完整示例

参考 `app/utils/AIDocument/example.py`，包含：

1. **example_1_basic()** - 基础图像理解
2. **example_2_with_json()** - 带JSON数据的文档分析
3. **example_3_table_recognition()** - 表格识别
4. **example_4_batch_processing()** - 批量处理多张图片

运行示例：

```bash
python app/utils/document_struct/example.py
```

---

## 使用注意事项

### 1. access_token 获取

本工具不包含 token 获取功能，需要你自己提供。百度官方获取流程：

```
POST https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={API_KEY}&client_secret={SECRET_KEY}
```

返回的 JSON 中包含 `access_token` 字段。

### 2. API 名称

不同的 API 服务名称对应不同的模型能力：
- `ernie-4.0-turbo-128k-preview` - 默认，支持图像理解
- 其他名称参考百度官方文档

### 3. 图片格式

- 支持的格式：JPG、JPEG、PNG
- 图片会被自动编码为 `data:image/jpeg;base64,xxx` 格式
- 建议图片大小不超过 4MB

### 4. 响应解析

百度返回的 JSON 格式：

```json
{
  "id": "as-xxxxx",
  "object": "chat.completion",
  "created": 1234567890,
  "result": "AI的回复内容",
  "usage": {
    "prompt_tokens": 100,
    "completion_tokens": 50,
    "total_tokens": 150
  }
}
```

本工具自动提取 `result` 字段返回。

---

## 常见问题

### Q1: 如何批量处理多张图片？

参考 `example_4_batch_processing()`，使用循环依次调用 `send_request()`。

### Q2: 如何解析 AI 返回的 JSON？

```python
response = client.send_request(...)

# 如果AI返回的是 ```json ... ``` 格式
if "```json" in response:
    json_str = response.split("```json")[1].split("```")[0].strip()
    result = json.loads(json_str)
else:
    result = json.loads(response)
```

### Q3: 请求失败怎么办？

- 检查 access_token 是否有效
- 检查图片路径是否正确
- 检查网络连接
- 查看错误信息（会自动提取 `error_code` 和 `error_msg`）

### Q4: 如何调整 AI 的创造性？

- `temperature`: 0.01（更确定）~ 1.0（更随机）
- `top_p`: 0（更确定）~ 1.0（更多样）

建议文档分析类任务使用较低的值（如 `temperature=0.01`）。

---

## 项目结构

```
app/utils/AIDocument/
├── __init__.py              # 模块导出
├── baidu_client.py          # 百度图像理解客户端
├── example.py               # 使用示例
└── README.md                # 本文档

app/prompts/AIDocument/
└── image_understanding_prompt.py  # 提示词模板
```

---

## 后续扩展

可以在 `baidu_client.py` 中添加：
- 流式响应支持（`stream=True`）
- 多轮对话支持（在 `messages` 中添加历史消息）
- 自动重试机制
- 批量并发处理

---

**更新日期**: 2025-11-22
