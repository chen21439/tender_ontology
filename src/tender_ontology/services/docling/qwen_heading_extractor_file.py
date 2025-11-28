"""
千问标题提取服务 - 上传文件模式 (fileid://)

支持两种模式并行调用：
1. 外部千问 long API (fileid://)
2. 内部千问 32b API (http://175.42.62.118:9102)
"""

import re
import asyncio
import aiohttp
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor

# 导入工具类
from tender_ontology.utils.request.ai_client import AIClient
from tender_ontology.utils.request.batch_processor import BatchProcessor


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
        prompt = """/no_think
        你是一个专业的文档结构分析引擎，专门负责识别招标文件中的一级标题和二级标题。

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
- 一级标题 `#`：**"第X章"** 格式的标题一起
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

        # 正则匹配 {type=xxx, id=xxx} 或 {id=xxx} 格式
        # 格式1: {type=volume, id=texts-56}
        # 格式2: {id=texts-57}
        type_id_pattern = re.compile(r'\{type=(\w+),\s*id=([^}]+)\}')
        id_only_pattern = re.compile(r'\{id=([^}]+)\}')
        # 用于移除整个 {...} 部分
        attr_pattern = re.compile(r'\{[^}]+\}')

        # 解析标题
        headings = []
        for line in markdown_content.split('\n'):
            line = line.strip()
            if line.startswith('#'):
                level = len(line) - len(line.lstrip('#'))
                text_with_attrs = line.lstrip('#').strip()

                # 先尝试匹配 {type=xxx, id=xxx} 格式
                type_id_match = type_id_pattern.search(text_with_attrs)
                if type_id_match:
                    node_type = type_id_match.group(1)
                    node_id = type_id_match.group(2)
                else:
                    # 再尝试匹配 {id=xxx} 格式
                    id_match = id_only_pattern.search(text_with_attrs)
                    node_id = id_match.group(1) if id_match else None
                    node_type = None

                # 移除 {...} 部分，得到纯文本
                text = attr_pattern.sub('', text_with_attrs).strip()

                if text:
                    heading = {
                        "id": node_id,
                        "text": text,
                        "level": level,
                        "page": None,
                        "bboxes": []
                    }
                    # 只有当 type 存在时才添加
                    if node_type:
                        heading["type"] = node_type
                    headings.append(heading)

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

    def _enrich_markdown_with_type(self, markdown_content: str) -> str:
        """
        为 markdown 标题添加 type 标记

        规则：
        - 册/部分/节 → type=volume
        - 章 → type=chapter

        Args:
            markdown_content: 原始 markdown 内容

        Returns:
            添加了 type 标记的 markdown 内容
        """
        # 匹配 册/部分/节 的模式
        volume_pattern = re.compile(r'第[一二三四五六七八九十\d]+[册部分节]')
        # 匹配 章 的模式
        chapter_pattern = re.compile(r'第[一二三四五六七八九十\d]+章')

        enriched_lines = []
        for line in markdown_content.split('\n'):
            if line.strip().startswith('#'):
                # 判断标题类型
                if volume_pattern.search(line):
                    # 在 {id=xxx} 前插入 type=volume
                    if '{id=' in line:
                        line = re.sub(r'\{id=', '{type=volume, id=', line)
                    else:
                        line = line.rstrip() + ' {type=volume}'
                elif chapter_pattern.search(line):
                    # 在 {id=xxx} 前插入 type=chapter
                    if '{id=' in line:
                        line = re.sub(r'\{id=', '{type=chapter, id=', line)
                    else:
                        line = line.rstrip() + ' {type=chapter}'
            enriched_lines.append(line)

        return '\n'.join(enriched_lines)

    # ========== 内部千问32b API 调用 ==========

    INTERNAL_MODEL = "qwen3-32b"

    @property
    def INTERNAL_API_URL(self) -> str:
        """从配置读取千问 API URL"""
        from tender_ontology.config.settings import settings
        return settings.qwen_api_url

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
            "top_p": 1.0,
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

            # 为响应内容添加 type 标记（册→volume，章→chapter）
            if content_text:
                content_text = self._enrich_markdown_with_type(content_text)

            # 保存带 type 标记的 markdown 内容（带时间戳）
            if save_response_path and content_text:
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                md_path = save_response_path.parent / f"{save_response_path.stem}_{timestamp}.md"
                md_path.write_text(content_text, encoding='utf-8')
                if verbose:
                    print(f"[Qwen32b] Markdown响应已保存: {md_path.name}")

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
            "top_p": 1.0,
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

    # ========== 章节切分与并发层级重建 ==========

    def parse_stage1_markdown(
        self,
        md_content: str,
        verbose: bool = True
    ) -> List[Dict[str, Any]]:
        """
        解析一阶段返回的 markdown 内容，提取 type=chapter 的标题

        Args:
            md_content: 一阶段返回的 markdown 内容（带 type 标记）
            verbose: 是否打印详细信息

        Returns:
            章节标题列表 [{id, text, level, type}, ...]
        """
        chapter_headings = []
        # 匹配带 type=chapter 的标题行
        # 格式如: # 第一章 招标公告 {type=chapter, id=texts-100}
        pattern = re.compile(
            r'^(#+)\s*(.+?)\s*\{type=chapter,\s*id=([^}]+)\}',
            re.MULTILINE
        )

        for match in pattern.finditer(md_content):
            level = len(match.group(1))
            text = match.group(2).strip()
            node_id = match.group(3).strip()

            chapter_headings.append({
                "id": node_id,
                "text": text,
                "level": level,
                "type": "chapter"
            })

        if verbose:
            print(f"[阶段1解析] 从 markdown 中提取到 {len(chapter_headings)} 个章节标题")

        return chapter_headings

    def find_latest_stage1_markdown(
        self,
        task_dir: Path,
        verbose: bool = True
    ) -> Optional[Path]:
        """
        查找任务目录中最新的一阶段 markdown 文件

        一阶段文件命名格式: *_level12_response_YYYYMMDD_HHMMSS.md

        Args:
            task_dir: 任务目录
            verbose: 是否打印详细信息

        Returns:
            最新的一阶段 markdown 文件路径，未找到返回 None
        """
        # 查找所有一阶段响应文件
        pattern = "*_level12_response_*.md"
        md_files = list(task_dir.glob(pattern))

        if not md_files:
            if verbose:
                print(f"[查找] 未找到一阶段 markdown 文件 (pattern: {pattern})")
            return None

        # 按修改时间排序，取最新的
        md_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        latest = md_files[0]

        if verbose:
            print(f"[查找] 找到 {len(md_files)} 个一阶段文件，使用最新的: {latest.name}")

        return latest

    def merge_stage2_results(
        self,
        level12_headings: List[Dict[str, Any]],
        chapter_results: List[Dict[str, Any]],
        verbose: bool = True
    ) -> List[Dict[str, Any]]:
        """
        聚合二阶段结果

        将章节内的子标题挂载到正确的层级：
        - 如果存在 volume（册），chapter 的 level=2，子标题从 level=3 开始
        - 如果不存在 volume，chapter 的 level=1，子标题从 level=2 开始

        Args:
            level12_headings: 一阶段返回的一二级标题
            chapter_results: 二阶段返回的各章节结果
            verbose: 是否打印详细信息

        Returns:
            聚合后的完整标题列表
        """
        # 检查是否存在 volume（册/部分/节）
        volume_pattern = re.compile(r'第[一二三四五六七八九十\d]+[册部分节]')
        has_volume = any(
            volume_pattern.search(h.get("text", ""))
            for h in level12_headings
        )

        if verbose:
            print(f"[聚合] 是否存在 volume 结构: {has_volume}")

        # 构建 chapter_id -> 原始 level 的映射（用 type=chapter 判断）
        chapter_level_map = {}
        for h in level12_headings:
            if h.get("type") == "chapter":
                chapter_level_map[h.get("id")] = h.get("level", 1)

        # 聚合结果
        all_headings = []
        processed_chapter_ids = set()

        for h in level12_headings:
            node_id = h.get("id")

            # 如果是 chapter，插入其子标题（用 type=chapter 判断）
            if h.get("type") == "chapter":
                # 先添加 chapter 本身
                all_headings.append(h)
                processed_chapter_ids.add(node_id)

                # 找到对应的二阶段结果
                chapter_result = next(
                    (r for r in chapter_results if r.get("chapter_id") == node_id),
                    None
                )

                if chapter_result:
                    chapter_original_level = chapter_level_map.get(node_id, 1)
                    # 二阶段中 chapter 是 level=1，需要计算偏移量
                    level_offset = chapter_original_level - 1

                    # 添加子标题（跳过 chapter 本身，它已经添加了）
                    for sub_h in chapter_result.get("headings", []):
                        if sub_h.get("id") != node_id:
                            # 调整 level
                            adjusted_heading = sub_h.copy()
                            adjusted_heading["level"] = sub_h.get("level", 1) + level_offset
                            all_headings.append(adjusted_heading)

                    if verbose:
                        sub_count = len(chapter_result.get("headings", [])) - 1
                        print(f"[聚合] {h.get('text', '')[:20]}... -> {sub_count} 个子标题 (offset={level_offset})")
            else:
                # 非 chapter 标题（volume 或其他），直接添加
                all_headings.append(h)

        if verbose:
            print(f"[聚合] 总计 {len(all_headings)} 个标题")

        return all_headings

    def build_document_tree(
        self,
        model_headings: List[Dict[str, Any]],
        fulltext_data: List[Dict[str, Any]],
        verbose: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        使用 LevelTreeConstructor 构建文档层级树

        Args:
            model_headings: 标题列表（带 level）
            fulltext_data: docling fulltext 数据（按阅读顺序）
            verbose: 是否打印详细信息

        Returns:
            树结构和统计信息
        """
        try:
            from tender_ontology.utils.document_struct.tree import LevelTreeConstructor

            constructor = LevelTreeConstructor(verbose=verbose)
            result = constructor.build_tree(model_headings, fulltext_data)

            # 打印树结构预览（只显示标题）
            if verbose:
                constructor.print_tree(max_depth=4, show_non_headers=False)

            return result
        except Exception as e:
            if verbose:
                print(f"[构建树] 构建文档树失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def extract_stage2_only(
        self,
        task_id: str,
        base_dir: str = r"E:\programFile\AIProgram\tender_ontology\static\upload",
        max_workers: int = 8,
        verbose: bool = True,
        build_tree: bool = True
    ) -> Dict[str, Any]:
        """
        直接进行二阶段提取（跳过一阶段，使用已有的一阶段结果）

        Args:
            task_id: 任务ID
            base_dir: 上传目录基础路径
            max_workers: 章节并发数
            verbose: 是否打印详细信息
            build_tree: 是否构建文档树并保存 _agent.json

        Returns:
            {
                "chapter_headings": [...],  # 从一阶段解析出的章节标题
                "chapter_results": [...],   # 各章节的层级结果
                "all_headings": [...],      # 合并后的所有标题
                "stage2_time": float,       # 二阶段耗时(秒)
                "tree_result": {...},       # 树结构（如果 build_tree=True）
                "agent_json_path": str      # _agent.json 路径（如果 build_tree=True）
            }
        """
        import json

        stage2_start = time.time()
        task_dir = Path(base_dir) / task_id

        if verbose:
            print(f"{'=' * 80}")
            print(f"[二阶段提取] 直接进行二阶段提取")
            print(f"{'=' * 80}")
            print(f"任务ID: {task_id}")
            print(f"任务目录: {task_dir}\n")

        # 1. 查找最新的一阶段 markdown
        stage1_md_path = self.find_latest_stage1_markdown(task_dir, verbose)
        if not stage1_md_path:
            raise FileNotFoundError(f"未找到一阶段 markdown 文件，请先运行一阶段提取")

        # 2. 解析一阶段 markdown，提取章节标题
        stage1_content = stage1_md_path.read_text(encoding='utf-8')
        chapter_headings = self.parse_stage1_markdown(stage1_content, verbose)

        if not chapter_headings:
            raise ValueError(f"一阶段 markdown 中未找到章节标题 (type=chapter)")

        # 3. 查找 title_with_id.md 文件
        title_files = list(task_dir.glob("*_title_with_id.md"))
        if not title_files:
            raise FileNotFoundError(f"未找到 title_with_id.md 文件")
        title_file = title_files[0]

        # 4. 查找 _level12.json 获取一阶段完整结果
        level12_files = list(task_dir.glob("*_level12.json"))
        if not level12_files:
            raise FileNotFoundError(f"未找到 _level12.json 文件")
        level12_file = level12_files[0]
        level12_headings = json.loads(level12_file.read_text(encoding='utf-8'))

        if verbose:
            print(f"[二阶段提取] 一阶段文件: {stage1_md_path.name}")
            print(f"[二阶段提取] 一二级标题文件: {level12_file.name}")
            print(f"[二阶段提取] 章节标题数: {len(chapter_headings)}")
            print(f"[二阶段提取] 标题文件: {title_file.name}\n")

        # 5. 并发章节层级重建
        if verbose:
            print(f"[二阶段提取] 开始并发章节层级重建...")

        chapter_results = self.extract_headings_by_chapters(
            str(title_file),
            chapter_headings,
            max_workers=max_workers,
            verbose=verbose,
            save_responses=False
        )

        # 6. 聚合结果
        if verbose:
            print(f"\n[二阶段提取] 开始聚合结果...")

        all_headings = self.merge_stage2_results(
            level12_headings,
            chapter_results,
            verbose=verbose
        )

        stage2_time = time.time() - stage2_start

        result = {
            "chapter_headings": chapter_headings,
            "chapter_results": chapter_results,
            "all_headings": all_headings,
            "stage2_time": stage2_time
        }

        # 7. 构建文档树并保存 _agent.json
        if build_tree:
            if verbose:
                print(f"\n[二阶段提取] 开始构建文档树...")

            # 查找 fulltext.json
            fulltext_files = list(task_dir.glob("*_fulltext.json"))
            if fulltext_files:
                fulltext_data = json.loads(fulltext_files[0].read_text(encoding='utf-8'))

                # 填充位置信息
                self.enrich_headings_with_location(all_headings, fulltext_data, verbose=verbose)

                # 构建树
                tree_result = self.build_document_tree(all_headings, fulltext_data, verbose=verbose)

                if tree_result:
                    result["tree_result"] = tree_result

                    # 保存文件
                    base_name = title_file.stem.replace('_title_with_id', '')

                    # 保存 _agent_headings.json
                    agent_headings_path = task_dir / f"{base_name}_agent_headings.json"
                    agent_headings_path.write_text(
                        json.dumps(all_headings, ensure_ascii=False, indent=2),
                        encoding='utf-8'
                    )
                    if verbose:
                        print(f"[二阶段提取] 聚合标题已保存: {agent_headings_path.name}")

                    # 保存 _agent_tree.json
                    tree_json_path = task_dir / f"{base_name}_agent_tree.json"
                    tree_json_path.write_text(
                        json.dumps(tree_result, ensure_ascii=False, indent=2),
                        encoding='utf-8'
                    )
                    if verbose:
                        print(f"[二阶段提取] 文档树已保存: {tree_json_path.name}")

                    # 保存 _agent.json（和 _forward.json 格式相同）
                    if "artifact" in tree_result:
                        agent_json_path = task_dir / f"{base_name}_agent.json"
                        agent_json_path.write_text(
                            json.dumps(tree_result["artifact"], ensure_ascii=False, indent=2),
                            encoding='utf-8'
                        )
                        if verbose:
                            print(f"[二阶段提取] Agent JSON 已保存: {agent_json_path.name}")
                        result["agent_json_path"] = str(agent_json_path)
            else:
                if verbose:
                    print(f"[二阶段提取] 未找到 fulltext.json，跳过构建树")

        if verbose:
            print(f"\n{'=' * 80}")
            print(f"[二阶段提取] 完成！")
            print(f"  - 章节数: {len(chapter_results)} 个")
            print(f"  - 总标题数: {len(all_headings)} 个")
            print(f"{'=' * 80}")
            print(f"[耗时统计]")
            print(f"  - 阶段2 (章节并发重建+聚合+构建树): {stage2_time:.2f} 秒")
            print(f"{'=' * 80}")

        return result

    def _build_chapter_prompt(self) -> str:
        """
        构建章节内标题层级重建的提示词

        Returns:
            提示词字符串
        """
        prompt = """/no_think
你是一个专业的文档结构分析引擎，负责识别章节内的标题层级结构。

## 任务说明
分析给定的**单个章节**内容，识别其中所有的标题并确定层级关系。

## 关键约束（必须遵守）
1. **整个输入内容属于同一个章节**，章节标题（第X章）是唯一的顶层标题
2. **只能有一个 `#` 一级标题**，就是章节标题本身
3. **章节内的所有其他标题都是该章节的后代**，必须从 `##` 开始，绝对不能出现第二个 `#`

## 层级判断规则

### 第一步：根据数字序号快速识别候选标题并排序
标题通常带有数字序号，如：
- 中文数字：一、二、三、（一）（二）（三）
- 阿拉伯数字：1. 2. 3.、(1) (2) (3)、1) 2) 3)
- 其他格式：第X节、① ② ③ 等

根据序号的嵌套关系确定层级，例如：
- "一、" 下面出现 "1."，则 "1." 是 "一、" 的子标题
- "1." 下面出现 "(1)"，则 "(1)" 是 "1." 的子标题

### 第二步：对难以直接区分的标题，结合语义和上下文确认
- 无序号标题（如"重要提示"、"备注"、"说明"）：根据它们在文档中的位置和前后标题的关系判断层级
- 序号格式相近时：结合标题的语义内容和上下文关系确定

## 输出要求
1. 仅在 ```markdown``` 代码块中返回识别到的标题
2. **必须保留每个标题后的 {id=...} 标识符**，原样附在标题行末尾
3. 层级必须连续，不能跳级
4. 保持标题在原文中的顺序
5. **只输出一个 `#` 一级标题**

## 输出示例
```markdown
# 第一章 招标公告 {id=texts-100}
## 一、项目概况 {id=texts-105}
### 1. 项目名称 {id=texts-106}
### 2. 项目编号 {id=texts-107}
## 二、投标人资格要求 {id=texts-120}
### 1. 基本资格条件 {id=texts-121}
#### (1) 具体要求 {id=texts-122}
## 备注 {id=texts-135}
```

现在，请分析以下章节内容，识别所有标题及其层级。"""

        return prompt

    def split_by_chapters(
        self,
        title_md_content: str,
        chapter_headings: List[Dict[str, Any]],
        verbose: bool = True
    ) -> List[Dict[str, Any]]:
        """
        根据章节标题锚点切分 title_with_id.md 内容

        Args:
            title_md_content: title_with_id.md 的完整内容
            chapter_headings: 章节标题列表（type=chapter 的标题）
            verbose: 是否打印详细信息

        Returns:
            章节列表，每个章节包含 {id, text, content, start_line, end_line}
        """
        lines = title_md_content.split('\n')

        # 提取所有章节的 id 和位置
        chapter_positions = []
        id_pattern = re.compile(r'\{id=([^}]+)\}')

        for i, line in enumerate(lines):
            id_match = id_pattern.search(line)
            if id_match:
                line_id = id_match.group(1)
                # 检查是否是章节标题
                for ch in chapter_headings:
                    if ch.get("id") == line_id:
                        chapter_positions.append({
                            "id": line_id,
                            "text": ch.get("text", ""),
                            "line_index": i
                        })
                        break

        if verbose:
            print(f"[章节切分] 找到 {len(chapter_positions)} 个章节锚点")

        # 切分章节内容
        chapters = []
        for i, ch_pos in enumerate(chapter_positions):
            start_line = ch_pos["line_index"]
            # 下一个章节的起始位置，或文件末尾
            end_line = chapter_positions[i + 1]["line_index"] if i + 1 < len(chapter_positions) else len(lines)

            chapter_content = '\n'.join(lines[start_line:end_line])

            chapters.append({
                "id": ch_pos["id"],
                "text": ch_pos["text"],
                "content": chapter_content,
                "start_line": start_line,
                "end_line": end_line,
                "line_count": end_line - start_line
            })

            if verbose:
                print(f"  - {ch_pos['text'][:30]}... ({end_line - start_line} 行)")

        return chapters

    def _create_internal_ai_client(self) -> AIClient:
        """
        创建指向内部 qwen3-32b API 的 AIClient

        Returns:
            配置好的 AIClient 实例
        """
        return AIClient(
            model_name=self.INTERNAL_MODEL,
            base_url=self.INTERNAL_API_URL.replace("/v1/chat/completions", "/v1"),
            api_key="not-needed",  # 内部 API 不需要 key
            temperature=0.0,
            top_p=0.7,
            repetition_penalty=1.05,
            max_tokens=8192,
            timeout=120.0
        )

    def _parse_chapter_response(self, response_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        解析章节标题提取的响应（供 BatchProcessor 使用）

        Args:
            response_text: API 响应文本
            context: 上下文信息（包含 chapter_id, chapter_text）

        Returns:
            解析后的结果
        """
        headings = self._parse_response(response_text)
        return {
            "chapter_id": context.get("chapter_id"),
            "chapter_text": context.get("chapter_text"),
            "headings": headings,
            "raw_response": response_text
        }

    def _merge_chapter_results(self, all_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        合并章节结果（供 BatchProcessor 使用）

        Args:
            all_results: 所有批次的结果

        Returns:
            合并后的结果列表（保持原顺序）
        """
        # BatchProcessor 已经保序，直接返回
        return all_results

    def extract_headings_by_chapters(
        self,
        title_md_path: str,
        chapter_headings: List[Dict[str, Any]],
        max_workers: int = 8,
        verbose: bool = True,
        save_responses: bool = True
    ) -> List[Dict[str, Any]]:
        """
        根据章节并发提取标题层级（使用 BatchProcessor）

        Args:
            title_md_path: title_with_id.md 文件路径
            chapter_headings: 章节标题列表（从第一次调用获取的 type=chapter 标题）
            max_workers: 最大并发数
            verbose: 是否打印详细信息
            save_responses: 是否保存各章节的响应

        Returns:
            所有章节的标题结果列表
        """
        title_md_path = Path(title_md_path)

        # 读取文件
        try:
            content = title_md_path.read_text(encoding='utf-8')
        except Exception as e:
            if verbose:
                print(f"[章节重建] 读取文件失败: {e}")
            return []

        # 切分章节
        chapters = self.split_by_chapters(content, chapter_headings, verbose)

        if not chapters:
            if verbose:
                print(f"[章节重建] 未找到任何章节")
            return []

        if verbose:
            print(f"\n[章节重建] 开始并发处理 {len(chapters)} 个章节 (max_workers={max_workers})")

        # 创建内部 API 客户端
        ai_client = self._create_internal_ai_client()

        # 创建 BatchProcessor
        batch_processor = BatchProcessor(
            ai_client=ai_client,
            verbose=verbose,
            max_workers=max_workers
        )

        # 构建批次列表: (system_prompt, user_prompt, context)
        system_prompt = self._build_chapter_prompt()
        batches = []
        for chapter in chapters:
            user_prompt = f"请分析以下章节内容，识别所有标题及其层级：\n\n{chapter['content']}"
            context = {
                "chapter_id": chapter.get("id"),
                "chapter_text": chapter.get("text", "")
            }
            batches.append((system_prompt, user_prompt, context))

        # 使用 BatchProcessor 并发处理
        try:
            results = batch_processor.process_batches(
                batches=batches,
                parse_response_func=self._parse_chapter_response,
                merge_results_func=self._merge_chapter_results,
                parallel=True
            )
        except Exception as e:
            if verbose:
                print(f"[章节重建] BatchProcessor 处理失败: {e}")
            return []

        if verbose:
            total_headings = sum(len(r.get("headings", [])) for r in results)
            print(f"\n[章节重建] 完成！共处理 {len(results)} 个章节，提取 {total_headings} 个标题")

        return results

    def extract_full_hierarchy(
        self,
        sectionheader_only_path: str,
        title_md_path: str,
        max_workers: int = 4,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        完整的两阶段标题层级提取

        阶段1: 提取一二级标题（章节）
        阶段2: 并发对每个章节做层级重建

        Args:
            sectionheader_only_path: sectionHeader_only.md 文件路径
            title_md_path: title_with_id.md 文件路径
            max_workers: 章节并发数
            verbose: 是否打印详细信息

        Returns:
            {
                "level12_headings": [...],  # 一二级标题
                "chapter_results": [...],   # 各章节的层级结果
                "all_headings": [...]       # 合并后的所有标题
                "stage1_time": float,       # 阶段1耗时(秒)
                "stage2_time": float,       # 阶段2耗时(秒)
                "total_time": float         # 总耗时(秒)
            }
        """
        total_start = time.time()

        if verbose:
            print(f"{'=' * 80}")
            print(f"[完整层级提取] 开始两阶段提取")
            print(f"{'=' * 80}\n")

        # 阶段1: 提取一二级标题
        stage1_start = time.time()
        if verbose:
            print(f"[阶段1] 提取一二级标题...")

        level12_headings = self.extract_headings_internal(
            sectionheader_only_path,
            verbose=verbose,
            save_response=True
        )

        # 筛选出 type=chapter 的标题作为锚点
        chapter_headings = [
            h for h in level12_headings
            if h.get("type") == "chapter"
        ]

        stage1_time = time.time() - stage1_start

        if verbose:
            print(f"\n[阶段1] 完成！找到 {len(level12_headings)} 个一二级标题，其中 {len(chapter_headings)} 个章节标题")
            print(f"[阶段1] 耗时: {stage1_time:.2f} 秒\n")

        # 阶段2: 并发章节层级重建
        stage2_start = time.time()
        if verbose:
            print(f"[阶段2] 并发章节层级重建...")

        chapter_results = self.extract_headings_by_chapters(
            title_md_path,
            chapter_headings,
            max_workers=max_workers,
            verbose=verbose,
            save_responses=True
        )

        stage2_time = time.time() - stage2_start

        # 合并所有标题
        all_headings = []
        for result in chapter_results:
            all_headings.extend(result.get("headings", []))

        total_time = time.time() - total_start

        if verbose:
            print(f"\n{'=' * 80}")
            print(f"[完整层级提取] 完成！")
            print(f"  - 一二级标题: {len(level12_headings)} 个")
            print(f"  - 章节数: {len(chapter_results)} 个")
            print(f"  - 总标题数: {len(all_headings)} 个")
            print(f"{'=' * 80}")
            print(f"[耗时统计]")
            print(f"  - 阶段1 (一二级标题提取): {stage1_time:.2f} 秒")
            print(f"  - 阶段2 (章节并发重建): {stage2_time:.2f} 秒")
            print(f"  - 总耗时: {total_time:.2f} 秒")
            print(f"{'=' * 80}")

        return {
            "level12_headings": level12_headings,
            "chapter_results": chapter_results,
            "all_headings": all_headings,
            "stage1_time": stage1_time,
            "stage2_time": stage2_time,
            "total_time": total_time
        }


if __name__ == "__main__":
    """
    直接运行测试：两阶段标题层级提取

    用法：
        # 完整两阶段提取（默认）
        python src/tender_ontology/services/docling/qwen_heading_extractor_file.py

        # 仅运行二阶段提取（使用已有的一阶段结果）
        python src/tender_ontology/services/docling/qwen_heading_extractor_file.py --stage2-only

        # 指定任务ID
        python src/tender_ontology/services/docling/qwen_heading_extractor_file.py --task-id 25112719364823166528

        # 组合使用
        python src/tender_ontology/services/docling/qwen_heading_extractor_file.py --stage2-only --task-id xxx
    """
    import json
    import argparse

    # 解析命令行参数
    parser = argparse.ArgumentParser(description="两阶段标题层级提取")
    parser.add_argument(
        "--stage2-only",
        action="store_true",
        help="仅运行二阶段提取（跳过一阶段，使用已有的一阶段 markdown 结果）"
    )
    parser.add_argument(
        "--task-id",
        type=str,
        default="25112810051018695596",
        help="任务ID（默认：25112719364823166528）"
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="章节并发数（默认：8）"
    )
    args = parser.parse_args()

    TASK_ID = args.task_id
    BASE_DIR = Path(r"E:\programFile\AIProgram\tender_ontology\static\upload") / TASK_ID

    # 创建提取器
    extractor = QwenHeadingExtractor()

    try:
        if args.stage2_only:
            # ========== 仅运行二阶段提取 ==========
            print(f"[模式] 仅运行二阶段提取（使用已有的一阶段结果）\n")

            result = extractor.extract_stage2_only(
                task_id=TASK_ID,
                max_workers=args.max_workers,
                verbose=True
            )

            result_path = BASE_DIR / "stage2_hierarchy_result.md"

        else:
            # ========== 完整两阶段提取 ==========
            # 查找需要的文件
            header_files = list(BASE_DIR.glob("*_sectionHeader_only.md"))
            title_files = list(BASE_DIR.glob("*_title_with_id.md"))

            if not header_files:
                print(f"[测试] 未找到 sectionHeader_only.md 文件在目录: {BASE_DIR}")
                exit(1)

            if not title_files:
                print(f"[测试] 未找到 title_with_id.md 文件在目录: {BASE_DIR}")
                exit(1)

            sectionheader_file = header_files[0]
            title_file = title_files[0]

            print(f"{'=' * 80}")
            print(f"[测试] 完整两阶段标题层级提取")
            print(f"{'=' * 80}")
            print(f"任务ID: {TASK_ID}")
            print(f"阶段1输入: {sectionheader_file.name}")
            print(f"阶段2输入: {title_file.name}")
            print(f"{'=' * 80}\n")

            result = extractor.extract_full_hierarchy(
                str(sectionheader_file),
                str(title_file),
                max_workers=args.max_workers,
                verbose=True
            )

            result_path = BASE_DIR / "full_hierarchy_result.md"

        # 将结果合并为 markdown 格式
        md_lines = []
        for h in result["all_headings"]:
            level = h.get("level", 0)
            text = h.get("text", "")
            node_id = h.get("id", "")
            prefix = "#" * level
            md_lines.append(f"{prefix} {text} {{id={node_id}}}")

        md_content = "\n".join(md_lines)

        # 保存 markdown 结果
        result_path.write_text(md_content, encoding='utf-8')
        print(f"\n[测试] 完整结果已保存: {result_path.name}")

        # 打印所有标题层级
        print(f"\n{'=' * 80}")
        print(f"[测试] 完整标题层级树")
        print(f"{'=' * 80}\n")
        print(md_content)

    except Exception as e:
        print(f"\n[测试] 提取失败: {e}")
        import traceback
        traceback.print_exc()
