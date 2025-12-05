"""
千问标题提取 API 调用

主要功能：
1. 调用内部千问 API 进行标题层级分析
2. 解析 API 返回的 Markdown 格式响应
3. Stage 1: 提取一二级标题

使用方式：
    from tender_ontology.utils.unstructured.qwen_heading_api import QwenHeadingAPI

    api = QwenHeadingAPI()
    headings = api.extract_level12_headings(sectionheader_md_path)
"""

import re
import json
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

from .heading_prompt import get_level12_prompt


class QwenHeadingAPI:
    """千问标题提取 API"""

    # 内部千问模型
    INTERNAL_MODEL = "qwen3-32b"

    def __init__(self, verbose: bool = True):
        """
        初始化 API 客户端

        Args:
            verbose: 是否打印详细信息
        """
        self.verbose = verbose

    @property
    def api_url(self) -> str:
        """从配置读取千问 API URL"""
        from tender_ontology.config.settings import settings
        return settings.qwen_api_url

    def call_api(
        self,
        content: str,
        system_prompt: str,
        save_response_path: Optional[Path] = None
    ) -> str:
        """
        调用内部千问 API

        Args:
            content: 用户内容
            system_prompt: 系统提示词
            save_response_path: 保存响应的路径（可选）

        Returns:
            API 响应文本
        """
        payload = {
            "model": self.INTERNAL_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ],
            "temperature": 0.0,
            "top_p": 1.0,
            "repetition_penalty": 1.05,
            "max_tokens": 8192
        }

        if self.verbose:
            print(f"[Qwen] 调用内部 API: {self.api_url}")

        try:
            response = requests.post(
                self.api_url,
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
                if self.verbose:
                    print(f"[Qwen] 响应已保存: {save_response_path.name}")

            content_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")

            if self.verbose:
                print(f"[Qwen] API 调用成功")

            return content_text

        except Exception as e:
            if self.verbose:
                print(f"[Qwen] API 调用失败: {e}")
            return ""

    def parse_response(self, response: str) -> List[Dict[str, Any]]:
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

        # 正则匹配
        type_id_pattern = re.compile(r'\{type=(\w+),\s*id=([^}]+)\}')
        id_only_pattern = re.compile(r'\{id=([^}]+)\}')
        attr_pattern = re.compile(r'\{[^}]+\}')

        headings = []
        for line in markdown_content.split('\n'):
            line = line.strip()
            if line.startswith('#'):
                level = len(line) - len(line.lstrip('#'))
                text_with_attrs = line.lstrip('#').strip()

                type_id_match = type_id_pattern.search(text_with_attrs)
                if type_id_match:
                    node_type = type_id_match.group(1)
                    node_id = type_id_match.group(2)
                else:
                    id_match = id_only_pattern.search(text_with_attrs)
                    node_id = id_match.group(1) if id_match else None
                    node_type = None

                text = attr_pattern.sub('', text_with_attrs).strip()

                if text:
                    heading = {
                        "id": node_id,
                        "text": text,
                        "level": level,
                    }
                    if node_type:
                        heading["type"] = node_type
                    headings.append(heading)

        return headings

    def extract_level12_headings(
        self,
        sectionheader_md_path: Union[str, Path],
        save_response: bool = True
    ) -> List[Dict[str, Any]]:
        """
        阶段1：提取标题层级

        Args:
            sectionheader_md_path: _sectionHeader_only.md 文件路径
            save_response: 是否保存响应

        Returns:
            标题列表
        """
        sectionheader_md_path = Path(sectionheader_md_path)

        if self.verbose:
            print(f"\n[阶段1] 提取标题层级...")
            print(f"[阶段1] 输入文件: {sectionheader_md_path.name}")

        # 读取文件内容
        content = sectionheader_md_path.read_text(encoding='utf-8')

        # 转换为 markdown 格式的标题列表
        # 输入格式：- [category] 标题文本 {id=xxx, align=center}
        # 输出格式：# 标题文本 {id=xxx}  （只保留 id）
        markdown_lines = []
        id_pattern = re.compile(r'\{[^}]*id=([^},]+)[^}]*\}')
        for line in content.split('\n'):
            line = line.strip()
            # 跳过空行、注释行、标题行
            if not line or line.startswith('>') or line.startswith('# '):
                continue
            # 匹配 - [category] 格式的行
            if line.startswith('- ['):
                # 移除 "- [category] " 前缀
                match = re.match(r'^-\s*\[[^\]]+\]\s*(.+)$', line)
                if match:
                    title_with_attrs = match.group(1)
                    # 提取 id
                    id_match = id_pattern.search(title_with_attrs)
                    if id_match:
                        item_id = id_match.group(1)
                        # 移除原始属性，只保留标题文本
                        title_text = re.sub(r'\{[^}]+\}', '', title_with_attrs).strip()
                        markdown_lines.append(f"# {title_text} {{id={item_id}}}")

        markdown_content = "\n".join(markdown_lines)

        if self.verbose:
            print(f"[阶段1] 转换为 {len(markdown_lines)} 行 markdown")

        if not markdown_lines:
            return []

        # 构建提示词
        system_prompt = get_level12_prompt()

        # 构建保存路径
        base_name = sectionheader_md_path.stem.replace('_unstructured_sectionHeader_only', '')
        save_path = None
        if save_response:
            save_path = sectionheader_md_path.parent / f"{base_name}_unstructured_level12_response.json"

        # 调用 API
        response = self.call_api(markdown_content, system_prompt, save_path)

        if not response:
            return []

        # 保存原始响应
        if save_response:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            raw_path = sectionheader_md_path.parent / f"{base_name}_unstructured_level12_raw_{timestamp}.txt"
            raw_path.write_text(response, encoding='utf-8')
            if self.verbose:
                print(f"[阶段1] 原始响应已保存: {raw_path.name}")

        # 解析 Markdown 格式的响应
        headings = self.parse_response(response)

        if self.verbose:
            print(f"[阶段1] 完成，共提取 {len(headings)} 个标题")

        return headings