"""
千问标题提取服务 - 上传文件模式 (fileid://)

支持两种模式并行调用：
1. 外部千问 long API (fileid://)
2. 内部千问 32b API (http://175.42.62.118:9102)
"""

import re
import asyncio
import aiohttp
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor


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
            header_count: 原文档中的标题数量（此参数在当前模式下不使用）

        Returns:
            提示词字符串
        """
        prompt = """你是一个专业的文档结构分析引擎，专门负责识别招标文件中的一级标题和二级标题。

## 任务说明
从文档中找到所有的**一级标题**和**二级标题**，忽略三级及以下的标题。

## 层级判断规则

### 第一步：判断文档是否存在"册/部分/节"结构
先扫描全文，判断是否存在"第X册"、"第X部分"或"第X节"这样的顶层结构标题。

### 第二步：根据文档结构确定层级

**情况一：文档存在"册/部分/节"结构**
- 一级标题 `#`：**"第X册"、"第X部分"、"第X节"** 格式的标题
- 二级标题 `##`：**"第X章"** 格式的标题（挂载在册/部分/节下）

**情况二：文档不存在"册/部分/节"结构**
- 一级标题 `#`：**"第X章"** 格式的标题
- 二级标题 `##`：章下的主要分节（如"一、""二、"等）

### 补充说明
- **独立功能标题**（如"目录"、"封面"、"特别警示条款"、"资格性审查表"、"符合性审查表"、"评标方法"、"用户需求书"等）→ 作为一级标题 `#`
- 层级必须连续，不能跳级

## 输出要求
1. 仅在 ```markdown``` 代码块中返回找到的一级和二级标题
2. **必须保留每个标题后的 {id=...} 标识符**，原样附在标题行末尾
3. 只输出一级 `#` 和二级 `##` 标题，忽略更深层级

## 输出示例

**示例一（存在册/部分结构）：**
```markdown
# 第一册 专用条款 {id=texts-61}
## 第一章 招标公告 {id=texts-100}
## 第二章 投标须知 {id=texts-150}
# 第二册 通用条款 {id=texts-200}
## 第一章 总则 {id=texts-210}
```

**示例二（无册/部分结构，章为顶层）：**
```markdown
# 第一章 招标公告 {id=texts-10}
## 一、项目概况 {id=texts-15}
## 二、投标人资格要求 {id=texts-20}
# 第二章 投标须知 {id=texts-50}
## 一、投标文件的编制 {id=texts-55}
```

现在，请找出文档中所有的一级标题和二级标题。"""

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

    # ========== 内部千问32b API 调用 ==========

    INTERNAL_API_URL = "http://175.42.62.118:9102/v1/chat/completions"
    INTERNAL_MODEL = "qwen3-32b"

    def _call_internal_qwen32b(
        self,
        content: str,
        header_count: int = 0,
        verbose: bool = True,
        save_response_path: Optional[Path] = None
    ) -> str:
        """
        调用内部千问32b API

        Args:
            content: Markdown 文件内容
            header_count: 原文档中的标题数量
            verbose: 是否打印详细信息
            save_response_path: 保存完整响应的路径（可选）

        Returns:
            API 响应文本
        """
        import json
        import requests

        prompt = self._build_prompt(header_count)
        user_content = f"请分析以下文档内容，找出一级和二级标题：\n\n{content}"

        payload = {
            "model": self.INTERNAL_MODEL,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.0,
            "top_p": 0.7,
            "repetition_penalty": 1.05,
            "max_tokens": 8192
        }

        if verbose:
            print(f"[Qwen32b] 调用内部API: {self.INTERNAL_API_URL}")

        try:
            response = requests.post(
                self.INTERNAL_API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=120
            )
            response.raise_for_status()
            result = response.json()

            # 保存完整响应
            if save_response_path:
                save_response_path = Path(save_response_path)
                save_response_path.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2),
                    encoding='utf-8'
                )
                if verbose:
                    print(f"[Qwen32b] 完整响应已保存: {save_response_path.name}")

            content_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            if verbose:
                print(f"[Qwen32b] 内部API调用成功")

            return content_text

        except Exception as e:
            if verbose:
                print(f"[Qwen32b] 内部API调用失败: {e}")
            return ""

    async def _call_internal_qwen32b_async(
        self,
        content: str,
        header_count: int = 0,
        verbose: bool = True
    ) -> str:
        """
        异步调用内部千问32b API

        Args:
            content: Markdown 文件内容
            header_count: 原文档中的标题数量
            verbose: 是否打印详细信息

        Returns:
            API 响应文本
        """
        prompt = self._build_prompt(header_count)
        user_content = f"请分析以下文档内容，找出一级和二级标题：\n\n{content}"

        payload = {
            "model": self.INTERNAL_MODEL,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.0,
            "top_p": 0.7,
            "repetition_penalty": 1.05,
            "max_tokens": 8192
        }

        if verbose:
            print(f"[Qwen32b] 异步调用内部API: {self.INTERNAL_API_URL}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.INTERNAL_API_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    result = await response.json()
                    content_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")

                    if verbose:
                        print(f"[Qwen32b] 内部API调用成功")

                    return content_text

        except Exception as e:
            if verbose:
                print(f"[Qwen32b] 内部API调用失败: {e}")
            return ""

    def extract_headings_parallel(
        self,
        file_path: str,
        header_count: int = 0,
        verbose: bool = True
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        并行调用外部千问long和内部千问32b提取标题

        Args:
            file_path: Markdown 文件路径
            header_count: 原文档中的标题数量
            verbose: 是否打印详细信息

        Returns:
            (外部API结果, 内部API结果) 元组
        """
        # 读取文件内容（内部API需要）
        try:
            content = Path(file_path).read_text(encoding='utf-8')
        except Exception as e:
            if verbose:
                print(f"[Qwen] 读取文件失败: {e}")
            content = ""

        # 上传文件获取 file_id（外部API需要）
        file_id = self.upload_file(file_path, verbose=verbose)

        if verbose:
            print(f"[Qwen] 开始并行调用两个API...")

        # 使用线程池并行执行两个调用
        with ThreadPoolExecutor(max_workers=2) as executor:
            # 外部千问long API
            future_external = executor.submit(
                self.extract_headings_by_file_id,
                file_id, header_count, verbose
            )

            # 内部千问32b API
            future_internal = executor.submit(
                self._extract_headings_internal,
                content, header_count, verbose
            )

            # 等待两个结果
            external_result = future_external.result()
            internal_result = future_internal.result()

        if verbose:
            print(f"[Qwen] 并行调用完成")
            print(f"  - 外部API (qwen-long): {len(external_result)} 个标题")
            print(f"  - 内部API (qwen3-32b): {len(internal_result)} 个标题")

        return external_result, internal_result

    def _extract_headings_internal(
        self,
        content: str,
        header_count: int = 0,
        verbose: bool = True,
        save_response_path: Optional[Path] = None
    ) -> List[Dict[str, Any]]:
        """
        使用内部千问32b API提取标题

        Args:
            content: Markdown 文件内容
            header_count: 原文档中的标题数量
            verbose: 是否打印详细信息
            save_response_path: 保存完整响应的路径（可选）

        Returns:
            标题列表
        """
        if not content:
            return []

        response = self._call_internal_qwen32b(
            content, header_count, verbose,
            save_response_path=save_response_path
        )

        if not response:
            return []

        return self._parse_response(response)

    def extract_headings_internal(
        self,
        file_path: str,
        header_count: int = 0,
        verbose: bool = True,
        save_response: bool = True
    ) -> List[Dict[str, Any]]:
        """
        使用内部千问32b API提取标题（公开方法）

        Args:
            file_path: Markdown 文件路径
            header_count: 原文档中的标题数量
            verbose: 是否打印详细信息
            save_response: 是否保存完整响应到文件

        Returns:
            标题列表
        """
        file_path = Path(file_path)

        # 读取文件内容
        try:
            content = file_path.read_text(encoding='utf-8')
        except Exception as e:
            if verbose:
                print(f"[Qwen32b] 读取文件失败: {e}")
            return []

        # 计算保存路径
        save_response_path = None
        if save_response:
            base_name = file_path.stem.replace('_sectionHeader_only', '')
            output_dir = file_path.parent
            save_response_path = output_dir / f"{base_name}_level12_response.json"

        if verbose:
            print(f"[Qwen32b] 开始提取一二级标题...")
            print(f"[Qwen32b] 输入文件: {file_path.name}")

        headings = self._extract_headings_internal(
            content, header_count, verbose,
            save_response_path=save_response_path
        )

        if verbose:
            print(f"[Qwen32b] 提取完成，共 {len(headings)} 个标题")

        return headings

    async def extract_headings_parallel_async(
        self,
        file_path: str,
        header_count: int = 0,
        verbose: bool = True
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        异步并行调用外部千问long和内部千问32b提取标题

        Args:
            file_path: Markdown 文件路径
            header_count: 原文档中的标题数量
            verbose: 是否打印详细信息

        Returns:
            (外部API结果, 内部API结果) 元组
        """
        # 读取文件内容
        try:
            content = Path(file_path).read_text(encoding='utf-8')
        except Exception as e:
            if verbose:
                print(f"[Qwen] 读取文件失败: {e}")
            content = ""

        # 上传文件获取 file_id
        file_id = self.upload_file(file_path, verbose=verbose)

        if verbose:
            print(f"[Qwen] 开始异步并行调用两个API...")

        # 定义外部API调用的包装函数（在线程中运行同步代码）
        loop = asyncio.get_event_loop()

        async def call_external():
            return await loop.run_in_executor(
                None,
                lambda: self.extract_headings_by_file_id(file_id, header_count, verbose)
            )

        async def call_internal():
            response = await self._call_internal_qwen32b_async(content, header_count, verbose)
            return self._parse_response(response) if response else []

        # 并行执行
        external_result, internal_result = await asyncio.gather(
            call_external(),
            call_internal()
        )

        if verbose:
            print(f"[Qwen] 异步并行调用完成")
            print(f"  - 外部API (qwen-long): {len(external_result)} 个标题")
            print(f"  - 内部API (qwen3-32b): {len(internal_result)} 个标题")

        return external_result, internal_result