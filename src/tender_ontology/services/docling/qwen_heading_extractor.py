"""
千问标题提取服务

提供：
1. QwenHeadingExtractor: 上传文件模式 (fileid://)
2. QwenDirectExtractor: 直接传入内容模式（推荐，效果更好）
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional


class QwenHeadingExtractor:
    """千问标题提取器"""

    def __init__(self, api_key: str = None, model: str = "qwen-long-latest"):
        """
        初始化提取器

        Args:
            api_key: 千问 API Key
            model: 模型名称，默认 qwen-long
        """
        self.api_key = api_key or "sk-f67e1a1d436c4df19ac575d8483e247d"
        self.model = model

    def upload_file(self, file_path: str, verbose: bool = True) -> str:
        """
        上传文件到千问获取 file_id

        Args:
            file_path: 文件路径
            verbose: 是否打印详细信息

        Returns:
            file_id
        """
        from tender_ontology.utils.document_struct.qwen_client import QwenClient

        client = QwenClient(api_key=self.api_key, model=self.model)

        if verbose:
            print(f"[Qwen] 上传文件中: {file_path}")

        file_id = client.upload_file(file_path, purpose="file-extract", verbose=verbose)

        if verbose:
            print(f"[Qwen] 文件上传成功，file_id: {file_id}")

        return file_id

    def extract_headings(
        self,
        file_path: str,
        header_count: int = 0,
        verbose: bool = True
    ) -> List[Dict[str, Any]]:
        """
        完整流程：上传文件 + 提取标题

        Args:
            file_path: Markdown 文件路径
            header_count: 原文档中的标题数量（用于约束输出）
            verbose: 是否打印详细信息

        Returns:
            标题列表，每个标题包含 id, text, level, page, bboxes 字段
        """
        # 第一步：上传文件
        file_id = self.upload_file(file_path, verbose=verbose)

        # 第二步：提取标题
        return self.extract_headings_by_file_id(file_id, header_count, verbose=verbose)

    def extract_headings_by_file_id(
        self,
        file_id: str,
        header_count: int = 0,
        verbose: bool = True
    ) -> List[Dict[str, Any]]:
        """
        根据 file_id 提取标题

        Args:
            file_id: 千问文件 ID
            header_count: 原文档中的标题数量
            verbose: 是否打印详细信息

        Returns:
            标题列表
        """
        from tender_ontology.utils.document_struct.qwen_client import QwenClient

        # 构建提示词
        prompt = self._build_prompt(header_count)

        # 创建客户端
        client = QwenClient(api_key=self.api_key, model="qwen-long-latest")

        # 系统提示词（fileid 必须单独存在）
        system_prompt = f"fileid://{file_id}"

        if verbose:
            print(f"[Qwen] 使用 file_id: {file_id} 提取标题，预期标题数量: {header_count}...")

        # 发送请求
        response = client.send_request(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.0,
            verbose=verbose
        )

        # 解析响应
        headings = self._parse_response(response)

        if verbose:
            print(f"[Qwen] 提取完成，共 {len(headings)} 个标题")

        return headings

    def _build_prompt(self, header_count: int = 0) -> str:
        """
        构建提示词

        Args:
            header_count: 原文档中的标题数量

        Returns:
            提示词字符串
        """
        prompt = """你是一个专业的文档结构分析引擎，**仅**专注于修复原markdown中所有不规范的标题标记（如误用 | 或 --- 的地方）。

## 说明
markdown中所有带"#"的内容都需要进行修复
1. 若存在"第X册"或"第X部分"类标题，则其为一级标题 `#`，其下"第X章"为二级 `##`。
2. 若不存在"册/部分"，但存在"第X章"，则"第X章"自动升为一级标题 `#`。
3. 所有具备分节功能的独立标题（如"特别警示条款""资格性审查表""符合性审查表""评标方法""用户需求书"等）无论位置，均视为有效标题。
4. 独立标题若与"第X章"同级出现，则统一作为 `#`；若出现在某章之下，则作为其子级。
5. 标题层级应连续递进，不得跳跃（禁止从 `#` 直接到 `###`）。

## 输出要求
- 仅在```markdown```中返回修正并层级化后的标题结构，不包含任何段落、表格或说明。
- **必须保留每个标题后跟随的 {id=...} 标识符**，原样附在标题行末尾。
- 标题层级使用# ## ### 在markdown中显示。

示例输出格式：
```markdown
# 一级标题 {id=texts-0}
## 二级标题 {id=texts-5}
### 三级标题 {id=texts-10}
#### 四级标题 {id=texts-15}
```

现在，请提取文档中的所有标题。"""

        # 添加标题数量约束
        if header_count > 0:
            prompt = prompt + f"\n\n**重要提示：原文档中共有 {header_count} 个标题，你的输出必须包含完全相同数量的标题，不得遗漏或新增。**"

        return prompt

    def _parse_response(self, response: str) -> List[Dict[str, Any]]:
        """
        解析千问返回的 Markdown 响应

        Args:
            response: 千问返回的原始响应

        Returns:
            标题列表
        """
        # 提取 markdown 代码块
        markdown_match = re.search(r'```markdown\s*(.*?)\s*```', response, re.DOTALL)
        if markdown_match:
            markdown_content = markdown_match.group(1).strip()
        else:
            markdown_content = response.strip()

        # 正则匹配 {id=xxx} 格式
        id_pattern = re.compile(r'\{id=([^}]+)\}')

        # 解析标题
        headings = []
        for line in markdown_content.split('\n'):
            line = line.strip()
            if line.startswith('#'):
                level = len(line) - len(line.lstrip('#'))
                text_with_id = line.lstrip('#').strip()

                # 提取 id
                id_match = id_pattern.search(text_with_id)
                node_id = id_match.group(1) if id_match else None

                # 移除 {id=xxx} 部分，得到纯文本
                text = id_pattern.sub('', text_with_id).strip()

                if text:
                    headings.append({
                        "id": node_id,
                        "text": text,
                        "level": level,
                        "page": None,
                        "bboxes": []
                    })

        return headings

    def enrich_headings_with_location(
        self,
        headings: List[Dict[str, Any]],
        fulltext_data: List[Dict[str, Any]],
        verbose: bool = True
    ) -> int:
        """
        从 fulltext 数据中填充标题的位置信息

        Args:
            headings: 标题列表（会被原地修改）
            fulltext_data: fulltext.json 的数据
            verbose: 是否打印详细信息

        Returns:
            成功匹配的数量
        """
        # 构建 id -> element 映射
        id_to_element = {item["id"]: item for item in fulltext_data if "id" in item}

        if verbose:
            print(f"[Qwen] 从 fulltext 构建了 {len(id_to_element)} 个 ID 映射")

        # 填充位置信息
        matched_count = 0
        for heading in headings:
            node_id = heading.get("id")
            if node_id and node_id in id_to_element:
                element = id_to_element[node_id]
                heading["page"] = element.get("page")
                heading["bboxes"] = element.get("bboxes", [])
                matched_count += 1

        if verbose:
            print(f"[Qwen] 成功匹配 {matched_count}/{len(headings)} 个标题的位置信息")

        return matched_count


class QwenDirectExtractor:
    """
    千问直接内容提取器（推荐使用）

    直接将完整 Markdown 内容作为 prompt 输入，避免 fileid:// 模式的采样问题。
    qwen-long-latest 支持 327,680 token 上下文，完全可以承载整篇文档。

    优势：
    - 模型能看到完整文档内容
    - ID 标识符不会丢失
    - 层级结构更准确
    - 输出更稳定
    """

    def __init__(self, api_key: str = None, model: str = "qwen-long-latest"):
        """
        初始化提取器

        Args:
            api_key: 千问 API Key
            model: 模型名称，默认 qwen-long-latest
        """
        self.api_key = api_key or "sk-f67e1a1d436c4df19ac575d8483e247d"
        self.model = model

    def extract_headings(
        self,
        file_path: str,
        header_count: int = 0,
        verbose: bool = True
    ) -> List[Dict[str, Any]]:
        """
        提取标题（直接读取文件内容并发送）

        Args:
            file_path: Markdown 文件路径
            header_count: 原文档中的标题数量（用于约束输出）
            verbose: 是否打印详细信息

        Returns:
            标题列表，每个标题包含 id, text, level, page, bboxes 字段
        """
        # 读取文件内容
        if verbose:
            print(f"[Qwen Direct] 读取文件: {file_path}")

        try:
            content = Path(file_path).read_text(encoding='utf-8')
        except Exception as e:
            raise RuntimeError(f"无法读取文件 {file_path}: {e}")

        if verbose:
            print(f"[Qwen Direct] 文件大小: {len(content)} 字符")

        # 使用内容提取
        return self.extract_headings_from_content(content, header_count, verbose)

    def extract_headings_from_content(
        self,
        content: str,
        header_count: int = 0,
        verbose: bool = True
    ) -> List[Dict[str, Any]]:
        """
        从 Markdown 内容直接提取标题

        Args:
            content: Markdown 文件内容
            header_count: 原文档中的标题数量
            verbose: 是否打印详细信息

        Returns:
            标题列表
        """
        from tender_ontology.utils.document_struct.qwen_client import QwenClient

        # 构建系统提示词（任务说明）和用户提示词（文档内容）
        system_prompt = self._build_system_prompt(header_count)
        user_prompt = self._build_user_prompt(content)

        # 创建客户端
        client = QwenClient(api_key=self.api_key, model=self.model)

        if verbose:
            print(f"[Qwen Direct] 使用模型: {self.model}")
            print(f"[Qwen Direct] 预期标题数量: {header_count}")
            print(f"[Qwen Direct] 发送请求中...")

        # 发送请求（系统提示词放任务说明，用户提示词放文档内容）
        response = client.send_request(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.0,
            max_tokens=8192,  # 给足输出空间
            verbose=verbose
        )

        # 解析响应
        headings = self._parse_response(response)

        if verbose:
            print(f"[Qwen Direct] 提取完成，共 {len(headings)} 个标题")

        return headings

    def _build_system_prompt(self, header_count: int = 0) -> str:
        """
        构建系统提示词（任务说明）

        Args:
            header_count: 原文档中的标题数量

        Returns:
            系统提示词字符串
        """
        system_prompt = """你是一个专业的文档结构分析引擎，专门负责修复招标文件中标题的层级结构。

## 任务背景
用户会提供一份招标文件的 Markdown 内容，是通过版面信息确定的标题 `#`。你需要根据标题内容判断其是否属于标题并确定标题正确的层级，并输出修正后的标题结构。

# 说明
有些被版面识别**误判**为标题，需要通过语义理解去除

## 层级判断规则

1. **"第X册"或"第X部分"** → 一级标题 `#`
2. **"第X章"** → 如果存在"册/部分"则为二级 `##`，否则为一级 `#`
3. **"一、""二、""三、"等中文数字序号** → 比其所属章节低一级
4. **"（一）""（二）""（三）"等带括号序号** → 比中文数字序号低一级
5. **"1、""2、""3、"或"1.""2.""3."等阿拉伯数字序号** → 根据上下文判断层级
6. **独立功能标题**（如"特别警示条款""资格性审查表""符合性审查表""评标方法""用户需求书""目录"等）→ 与"第X章"同级
7. **层级必须连续递进**，禁止从 `#` 直接跳到 `###`

## 输出要求

1. 仅输出 ```markdown``` 代码块，包含修正后的标题层级结构
2. **必须保留每个标题后的 {id=...} 标识符**，原样附在标题行末尾
3. 只输出标题行，不要输出段落、表格或其他内容
4. 使用 `#` `##` `###` `####` 等表示层级

## 输出示例

```markdown
# 第一册 专用条款 {id=texts-61}
## 第一章 招标公告 {id=texts-100}
## 第二章 对通用条款的补充内容 {id=texts-107}
### 一、对通用条款的补充内容 {id=texts-108}
### 二、其他关键信息 {id=texts-110}
#### （一）与"对通用条款的补充内容"章节相关的事项 {id=texts-111}
#### （二）其他事项 {id=texts-114}
# 第二册 通用条款 {id=texts-68}
## 第一章 总则 {id=texts-987}
```"""

        # 添加标题数量约束
        if header_count > 0:
            system_prompt += f"\n\n**重要约束**：原文档中共有 **{header_count}** 个标题，你的输出必须包含完全相同数量的标题，不得遗漏或新增。"

        return system_prompt

    def _build_user_prompt(self, content: str) -> str:
        """
        构建用户提示词（文档内容）

        Args:
            content: Markdown 文件内容

        Returns:
            用户提示词字符串
        """
        return f"""请修复以下招标文件中的标题层级结构：

{content}

请输出修正后的完整标题层级结构（仅输出标题行，保留 {{id=...}} 标识符）："""

    def _parse_response(self, response: str) -> List[Dict[str, Any]]:
        """
        解析千问返回的 Markdown 响应

        Args:
            response: 千问返回的原始响应

        Returns:
            标题列表
        """
        # 提取 markdown 代码块（增强鲁棒性）
        markdown_match = re.search(r'```markdown\s*(.*?)\s*```', response, re.DOTALL | re.IGNORECASE)
        if markdown_match:
            markdown_content = markdown_match.group(1).strip()
        else:
            markdown_content = response.strip()

        # 正则匹配 {id=xxx} 格式
        id_pattern = re.compile(r'\{id=([^}]+)\}')

        # 解析标题
        headings = []
        for line in markdown_content.split('\n'):
            line = line.strip()
            if not line.startswith('#'):
                continue

            level = len(line) - len(line.lstrip('#'))
            text_with_id = line.lstrip('#').strip()

            # 提取 id
            id_match = id_pattern.search(text_with_id)
            node_id = id_match.group(1) if id_match else None

            # 移除 {id=xxx} 部分，得到纯文本
            text = id_pattern.sub('', text_with_id).strip()

            if text:
                headings.append({
                    "id": node_id,
                    "text": text,
                    "level": level,
                    "page": None,
                    "bboxes": []
                })

        return headings

    def enrich_headings_with_location(
        self,
        headings: List[Dict[str, Any]],
        fulltext_data: List[Dict[str, Any]],
        verbose: bool = True
    ) -> int:
        """
        从 fulltext 数据中填充标题的位置信息

        Args:
            headings: 标题列表（会被原地修改）
            fulltext_data: fulltext.json 的数据
            verbose: 是否打印详细信息

        Returns:
            成功匹配的数量
        """
        # 构建 id -> element 映射
        id_to_element = {item["id"]: item for item in fulltext_data if "id" in item}

        if verbose:
            print(f"[Qwen Direct] 从 fulltext 构建了 {len(id_to_element)} 个 ID 映射")

        # 填充位置信息
        matched_count = 0
        for heading in headings:
            node_id = heading.get("id")
            if node_id and node_id in id_to_element:
                element = id_to_element[node_id]
                heading["page"] = element.get("page")
                heading["bboxes"] = element.get("bboxes", [])
                matched_count += 1

        if verbose:
            print(f"[Qwen Direct] 成功匹配 {matched_count}/{len(headings)} 个标题的位置信息")

        return matched_count
