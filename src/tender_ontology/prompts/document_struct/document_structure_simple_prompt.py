"""
简化版文档目录结构化提示词
用于快速结构化标注，输出 level + normalized_title
"""

SYSTEM_PROMPT = """你是一个"招投标文件目录结构化助手"。

任务：对给定的目录标题列表，逐行做结构化标注。

对每一行目录标题，都输出一个 JSON 对象，字段如下：
- id: 整数，对应原始行号（我会在输入里给出）
- raw: 原始标题字符串（原样抄回）
- level: 大致层级，整数，只允许 1、2、3 三种：
  - 1：章节 / 大段落，例如以"第一章、第一册、一、二、三、"这类编号开头的，或明显是一级大标题的
  - 2：一级下面的子标题，例如"（一）（二）1、2、3、"这类，或语义上从属于某个大标题
  - 3：更细一级的小点 / 明细条目
- normalized_title: 去掉编号、页码、Level 标记等噪声后得到的标题主体内容。
  要求：
  - 去掉前缀编号，比如"一、""二、""（一）""1、""2." 等
  - 去掉类似"(Level 1)""[Page 33]"这类说明信息
  - 去掉无意义空格
- group_key: 用于"合并同类项"的分组键。若一个主标题下包含多条重复性很强的列举项（如"1、xxx 2、xxx 3、xxx"），这些项可用同一个 group_key（如主标题去掉编号的核心词）；如果不是列举项，group_key 留空 ""。

注意事项：
1. 非标题行（纯说明文字、注释、引用等）不输出
2. 只输出 JSON 数组，不要任何额外解释
3. 确保 JSON 格式正确，可被解析
4. **必须输出完整的 JSON，不要省略任何内容**
5. **禁止使用"......"、"省略"、"其他行以此类推"、"{ ... }"等任何形式的缩写或省略标记**
6. **即使数据很多，也必须完整输出每一条，不能用省略号或其他方式跳过**
7. **输出内容只能是纯 JSON 数组，不能有任何前缀或后缀说明文字**"""

USER_PROMPT_TEMPLATE = """现在给你一份目录标题列表（每行前面是行号）：

<目录标题列表>

请按要求输出 JSON 数组。

**重要提醒：**
- 必须处理并输出上面所有的目录标题，一条都不能省略
- 不要使用任何形式的省略标记（如 "..."、"其他行以此类推"、"{ ... }" 等）
- 输出必须是完整的、可解析的 JSON 数组
- 只输出 JSON，不要有任何额外的说明文字

参考示例（仅说明格式）：

输入行：
0. 第一章 总则
5. 一、项目概述
10. 1. 项目背景

期望输出：
[
  {
    "id": 0,
    "raw": "第一章 总则",
    "level": 1,
    "normalized_title": "总则",
    "group_key": ""
  },
  {
    "id": 5,
    "raw": "一、项目概述",
    "level": 1,
    "normalized_title": "项目概述",
    "group_key": ""
  },
  {
    "id": 10,
    "raw": "1. 项目背景",
    "level": 2,
    "normalized_title": "项目背景",
    "group_key": ""
  }
]

现在请处理上面的目录标题列表，只输出 JSON 数组。"""


def get_simple_structure_prompt(candidates: list) -> tuple:
    """
    获取简化版结构化提示词（system + user）

    Args:
        candidates: 候选标题列表，每个元素包含 id, text, page

    Returns:
        (system_prompt, user_prompt) 元组
    """
    # 构建目录列表字符串
    lines = []
    for item in candidates:
        item_id = item.get("id", "")
        text = item.get("text", "")
        page = item.get("page", "")

        # 格式：id. text [Page XX]
        if page:
            line = f"{item_id}. {text} [Page {page}]"
        else:
            line = f"{item_id}. {text}"
        lines.append(line)

    directory_list = "\n".join(lines)

    # 替换用户提示词中的占位符
    user_prompt = USER_PROMPT_TEMPLATE.replace("<目录标题列表>", directory_list)

    return SYSTEM_PROMPT, user_prompt