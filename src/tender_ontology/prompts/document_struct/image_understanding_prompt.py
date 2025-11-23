"""
图像理解提示词模板
用于百度文心一言的图像内容分析
"""

# 基础图像理解提示词
BASIC_IMAGE_PROMPT = """请仔细观察这张图片，并详细描述图片中的内容。

请包含以下信息：
1. 图片的主要内容和主题
2. 图片中的关键元素
3. 图片的布局和结构
4. 任何值得注意的细节

请用清晰、简洁的语言描述。"""


# 文档图像理解提示词（带JSON数据）
DOCUMENT_IMAGE_WITH_JSON_PROMPT = """你是一个文档分析专家。我会给你：
1. 一张文档页面的截图
2. 从该页面提取的文本行数据（JSON格式）

你的任务是：
结合图片和文本数据，分析这个文档页面的结构和内容，并给出详细的分析结果。

**文本行数据（lines）：**
```json
{json_data}
```

请分析：
1. 页面的整体布局（标题、正文、表格、列表等）
2. 关键内容的类型和位置
3. 文本行之间的逻辑关系
4. 是否有需要特别注意的结构特征

请以JSON格式输出分析结果。"""


# 表格识别提示词
TABLE_RECOGNITION_PROMPT = """请识别这张图片中的表格。

分析以下内容：
1. 表格的行数和列数
2. 表头内容
3. 每个单元格的内容
4. 表格的边框和分隔线情况

请以JSON格式输出表格数据，格式如下：
```json
{
  "table_info": {
    "rows": 数字,
    "columns": 数字,
    "has_header": true/false
  },
  "headers": ["列1", "列2", ...],
  "data": [
    ["单元格1-1", "单元格1-2", ...],
    ["单元格2-1", "单元格2-2", ...]
  ]
}
```"""


# 标题层级识别提示词
HEADING_RECOGNITION_PROMPT = """请识别这张文档图片中的标题层级。

分析以下内容：
1. 识别所有的标题（一级、二级、三级等）
2. 判断每个标题的层级
3. 标注标题的位置和样式特征（字号、加粗、居中等）

请以JSON格式输出，格式如下：
```json
{
  "headings": [
    {
      "text": "标题文本",
      "level": 1,
      "style": {
        "bold": true,
        "centered": true,
        "font_size": "large"
      }
    }
  ]
}
```"""


# 文档行级标签分类提示词
DOCUMENT_LINE_TAGGING_PROMPT = """你是一个专业的文档结构分析专家。你的任务是对文档中的每一行文本进行标签分类。

标签类型说明：
- Caption: 标题（章节标题、小标题等）
- Para-Line: 段落行（正文内容）
- First-Line: 段落首行（段落的第一行，通常有缩进）
- List-Item: 列表项（带编号或符号的列表）
- Table-Cell: 表格单元格
- Header: 页眉
- Footer: 页脚
- Other: 其他类型

{page_descriptions}

现在的输入图片为：<这里放入页面图片>
对应的行数据 JSON 为：
{json_data}

请根据上述要求，对每个 line_id 进行分类，并按指定 JSON 格式输出。

示例输出（只是格式示例，内容不代表真实预测）：
```json
[
  {{"line_id": 834, "label": "Caption"}},
  {{"line_id": 835, "label": "Para-Line"}},
  {{"line_id": 836, "label": "First-Line"}}
]
```

注意：
1. 必须为每个 line_id 分配一个标签
2. 输出必须是 JSON 数组格式
3. 使用 ```json 代码块包裹输出
4. 不要输出任何解释性文字，只输出 JSON 数组
"""


def build_custom_prompt(
    task_description: str,
    context: str = "",
    output_format: str = "文字描述"
) -> str:
    """
    构建自定义提示词

    Args:
        task_description: 任务描述
        context: 额外的上下文信息
        output_format: 期望的输出格式（"文字描述"、"JSON"等）

    Returns:
        完整的提示词
    """
    prompt = f"""请分析这张图片。

**任务要求：**
{task_description}
"""

    if context:
        prompt += f"""
**上下文信息：**
{context}
"""

    prompt += f"""
**输出格式：**
{output_format}
"""

    return prompt
