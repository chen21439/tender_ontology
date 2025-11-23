"""
学术文档版面分析和语义行分类提示词

用于对学术论文页面进行版面分析，对每一行文本进行语义分类。
"""

DOCUMENT_LAYOUT_ANALYSIS_PROMPT = """你是一个专门做文档版面分析和语义行分类的多模态模型。

我会给你多张连续的文件页面的图片和文本行：
1. 图片：包含正文、标题、图表、页眉页脚等。多张图片按页码顺序排列，展示文档的连续内容。
2. 文本行：每行通过 page 字段标识所在页码，通过 box 能在对应图片中定位原文位置，text 为原文。

**重要说明**：
- 你会同时看到多个连续页面，这样可以更好地理解跨页的标题、章节和段落。
- 标题和章节可能跨页显示，请根据多页上下文综合判断。
- 段落也可能跨页，请注意识别跨页的段落首行和段落延续行。

你的任务是对每个 line_id 对应的文本行进行分类，共有以下 8 个类别：

1. Section – 章节标题
   - 编号结构：优先级顺序一般为："第x册、第x部分">"第x章">"一">"1.">"1.1">"1.1.1">"1.1.1.1"
   - 可能字号较大，加粗显示。

2. First-Line – 段落首行
   - 某个正文段落的第一行。
   - 通常相对于上一段有竖直间距，且可能有首行缩进。
   - 后面会跟着同一段落的 Para-Line。

3. Para-Line – 段落非首行
   - 与上一行属于同一段落，行间距正常，无额外段前空白。
   - 不是段落的第一行。

4. Figure – 图像/插图区域
   - 对应的是非文本的图像区域。
   - 通常整块是图片或图表（如曲线图、柱状图），而不是文字行。
   - 如果某个 line_id 对应的是图像块，而不是文本，则打为 Figure。

5. Caption – 图表说明文字
   - 贴在 Figure 或 Table 附近，用于说明图或表。
   - 通常以 "Fig."、"Figure"、"Table" 等开头，例如 "Figure 2:"、"Table 3:"。
   - 字号一般比正文略小，紧挨着图像或表格。

7. Page-Header – 页眉
   - 位于页面最上方靠近顶部边缘的小字号文字。
   - 可能包含期刊名、论文标题简写、作者名、页码等。
   - 在不同页面重复出现的样式化文字。

8. Page-Footer – 页脚
   - 位于页面最下方靠近底部边缘的小字号文字。
   - 通常包含页码、版权信息、DOI、网址等。
   - 与主体内容有明显的空白间隔。

9. Footnote – 脚注
   - 正文中某处引用的补充说明，一般在页面下部（但在 Page-Footer 之上）。
   - 字号通常小于正文，可能有编号或星号标记。
   - 与正文之间可能有分隔线。

---

## 输出格式要求（非常重要）：
- 只输出一个 JSON 数组，不要输出多余文字说明。
- 数组中的每个元素是一个对象，包含：
  - "line_id": 对应输入中的 line_id
  - "label": 上面 9 个类别中的一个，必须严格使用以下英文字符串之一：
    - "Title"
    - "Section"
    - "First-Line"
    - "Para-Line"
    - "Figure"
    - "Caption"
    - "Page-Footer"
    - "Page-Header"
    - "Footnote"

示例输出（只是格式示例，内容不代表真实预测）：
[
  {"line_id": 834, "label": "Caption"},
  {"line_id": 835, "label": "Para-Line"},
  {"line_id": 836, "label": "First-Line"}
]

现在的输入为：
<这里放入多页图片和行数据>

请根据上述要求，对每个 line_id 进行分类，并按指定 JSON 格式输出。注意要综合考虑多页的上下文信息。
"""


def get_document_layout_analysis_prompt(page_image_placeholder: str = "<这里放入页面图片>",
                                        line_data_json_placeholder: str = "<这里粘贴整页的行数据 JSON 数组>") -> str:
    """
    获取文档版面分析提示词

    Args:
        page_image_placeholder: 页面图片的占位符文本
        line_data_json_placeholder: 行数据 JSON 的占位符文本

    Returns:
        格式化后的提示词字符串
    """
    return DOCUMENT_LAYOUT_ANALYSIS_PROMPT.replace(
        "<这里放入页面图片>", page_image_placeholder
    ).replace(
        "<这里粘贴整页的行数据 JSON 数组>", line_data_json_placeholder
    )
