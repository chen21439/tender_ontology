"""
章节处理器

主要功能：
1. 根据章节标题切分 fulltext.md 内容
2. Stage 2: 并发提取各章节的子标题
3. 聚合二阶段结果

使用方式：
    from tender_ontology.utils.unstructured.chapter_processor import ChapterProcessor

    processor = ChapterProcessor()
    results = processor.extract_headings_by_chapters(fulltext_md_path, chapter_headings)
"""

import re
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

from .heading_prompt import get_chapter_prompt, get_deepseek_chapter_prompt
from .qwen_heading_api import QwenHeadingAPI
from .deepseek_heading_api import DeepSeekHeadingAPI


class ChapterProcessor:
    """章节处理器"""

    # 内部千问模型
    INTERNAL_MODEL = "qwen3-32b"

    def __init__(self, verbose: bool = True, use_deepseek: bool = False):
        """
        初始化章节处理器

        Args:
            verbose: 是否打印详细信息
            use_deepseek: 是否使用 DeepSeek R1 模型（默认使用千问）
        """
        self.verbose = verbose
        self.use_deepseek = use_deepseek
        self._qwen_api = QwenHeadingAPI(verbose=False)
        self._deepseek_api = DeepSeekHeadingAPI(verbose=False)

    @property
    def api_url(self) -> str:
        """从配置读取千问 API URL"""
        from tender_ontology.config.settings import settings
        return settings.qwen_api_url

    @property
    def deepseek_api_url(self) -> str:
        """从配置读取 DeepSeek API URL"""
        from tender_ontology.config.settings import settings
        return settings.deepseek_api_url

    @property
    def deepseek_api_key(self) -> str:
        """从配置读取 DeepSeek API Key"""
        from tender_ontology.config.settings import settings
        return settings.deepseek_api_key

    @property
    def deepseek_model(self) -> str:
        """从配置读取 DeepSeek 模型名称"""
        from tender_ontology.config.settings import settings
        return settings.deepseek_model

    def _truncate_text(self, text: str, max_length: int = 20) -> str:
        """
        缩略文本：小于 max_length 个字完整发送，否则缩略为 前5字...省略N字...后5字

        Args:
            text: 原始文本
            max_length: 最大长度阈值（默认20）

        Returns:
            缩略后的文本
        """
        if len(text) < max_length:
            return text
        # 前5个字 + ...省略N字... + 后5个字
        omitted = len(text) - 10
        return f"{text[:5]}...省略{omitted}字...{text[-5:]}"

    def _extract_candidates_from_content(
        self,
        content: str,
        context_chars: int = 5,
        full_content: bool = False
    ) -> List[Dict[str, Any]]:
        """
        从 markdown 内容中提取章节内容

        Args:
            content: markdown 格式的章节内容
            context_chars: 上下文字符数（默认5个字符）
            full_content: 是否发送全量内容（DeepSeek 模式）

        Returns:
            候选内容列表，每个元素包含 id, text, is_heading, pre_para, next_para
        """
        id_pattern = re.compile(r'\{id=([^},]+)')

        # 第一遍：解析所有行，保存完整信息
        all_items = []
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            # 跳过文件头部的标题（如 "# 文件名 - 全文内容"）
            if line.startswith('# ') and ' - 全文内容' in line:
                continue
            # 跳过注释行
            if line.startswith('>'):
                continue
            # 跳过表格
            if line.startswith('[Table]'):
                continue

            # 提取 id
            id_match = id_pattern.search(line)
            item_id = id_match.group(1) if id_match else ""

            # 判断是标题还是普通段落
            is_heading = line.startswith('#')

            # 移除 markdown 前缀和属性
            if is_heading:
                text = re.sub(r'^#+\s*', '', line)  # 移除 # 前缀
            else:
                text = re.sub(r'^-\s*', '', line)  # 移除 - 前缀

            text = re.sub(r'\[[^\]]+\]\s*', '', text)  # 移除 [category]
            text = re.sub(r'\{[^}]+\}', '', text)  # 移除 {id=...}
            text = text.strip()

            if text and item_id:
                all_items.append({
                    "id": item_id,
                    "text": text,
                    "is_heading": is_heading
                })

        # 第二遍：筛选候选项并添加上下文
        candidates = []
        for i, item in enumerate(all_items):
            text = item["text"]
            is_heading = item["is_heading"]

            # full_content 模式：发送全部内容
            # 非 full_content 模式：只发送标题候选或短段落（<20字）
            if full_content or is_heading or len(text) < 20:
                # 获取前一个段落的前N个字符（不加省略号）
                pre_para = ""
                if i > 0:
                    prev_text = all_items[i - 1]["text"]
                    pre_para = prev_text[:context_chars]

                # 获取后一个段落的前N个字符（不加省略号）
                next_para = ""
                if i < len(all_items) - 1:
                    next_text = all_items[i + 1]["text"]
                    next_para = next_text[:context_chars]

                candidates.append({
                    "id": item["id"],
                    "text": text,
                    "display_text": text,
                    "is_heading": is_heading,
                    "pre_para": pre_para,
                    "next_para": next_para
                })

        return candidates

    def split_by_chapters(
        self,
        fulltext_md_content: str,
        chapter_headings: List[Dict[str, Any]],
        level12_headings: List[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        根据章节标题锚点切分 fulltext.md 内容

        如果存在 volume 结构，先按 volume 切分，再在每个 volume 内部按 chapter 切分，
        确保 chapter 不会跨越 volume 边界。

        Args:
            fulltext_md_content: fulltext.md 的完整内容
            chapter_headings: 章节标题列表（type=chapter 的标题）
            level12_headings: 一阶段返回的所有标题（用于获取 volume 信息）

        Returns:
            章节列表
        """
        lines = fulltext_md_content.split('\n')
        id_pattern = re.compile(r'\{id=([^},]+)')

        # 构建 id -> 行号 的映射
        id_to_line = {}
        for i, line in enumerate(lines):
            id_match = id_pattern.search(line)
            if id_match:
                id_to_line[id_match.group(1)] = i

        # 获取 volume 列表（如果存在）
        volume_headings = []
        if level12_headings:
            volume_headings = [h for h in level12_headings if h.get("type") == "volume"]

        # 构建 volume 边界
        volume_boundaries = []  # [(start_line, end_line, volume_id), ...]
        if volume_headings:
            for i, vol in enumerate(volume_headings):
                vol_id = vol.get("id")
                start_line = id_to_line.get(vol_id, 0)
                # 下一个 volume 的起始行，或文档末尾
                if i + 1 < len(volume_headings):
                    next_vol_id = volume_headings[i + 1].get("id")
                    end_line = id_to_line.get(next_vol_id, len(lines))
                else:
                    end_line = len(lines)
                volume_boundaries.append((start_line, end_line, vol_id))

            if self.verbose:
                print(f"[章节切分] 存在 {len(volume_boundaries)} 个 volume 边界")
                for start, end, vid in volume_boundaries:
                    print(f"  - {vid}: 行 {start}-{end}")

        # 构建 chapter_id -> volume 边界 的映射
        def get_chapter_end_line(chapter_id: str, chapter_line: int) -> int:
            """获取 chapter 的结束行（考虑 volume 边界）"""
            # 找到该 chapter 所在的 volume 边界
            volume_end = len(lines)
            for vol_start, vol_end, vol_id in volume_boundaries:
                if vol_start <= chapter_line < vol_end:
                    volume_end = vol_end
                    break

            # 找到下一个 chapter 的起始行
            next_chapter_line = len(lines)
            for ch in chapter_headings:
                ch_line = id_to_line.get(ch.get("id"), len(lines))
                if ch_line > chapter_line:
                    next_chapter_line = min(next_chapter_line, ch_line)

            # 取 volume 边界和下一个 chapter 的较小值
            return min(volume_end, next_chapter_line)

        # 切分章节内容
        chapters = []
        for ch in chapter_headings:
            ch_id = ch.get("id")
            ch_text = ch.get("text", "")
            start_line = id_to_line.get(ch_id)

            if start_line is None:
                if self.verbose:
                    print(f"  - 警告: 未找到章节 {ch_text[:20]}... 的位置")
                continue

            end_line = get_chapter_end_line(ch_id, start_line)
            chapter_content = '\n'.join(lines[start_line:end_line])

            chapters.append({
                "id": ch_id,
                "text": ch_text,
                "content": chapter_content,
                "start_line": start_line,
                "end_line": end_line,
                "line_count": end_line - start_line
            })

            if self.verbose:
                print(f"  - {ch_text[:30]}... ({end_line - start_line} 行)")

        if self.verbose:
            print(f"[章节切分] 共切分 {len(chapters)} 个章节")

        return chapters

    def extract_headings_by_chapters(
        self,
        fulltext_md_path: Union[str, Path],
        chapter_headings: List[Dict[str, Any]],
        level12_headings: List[Dict[str, Any]] = None,
        max_workers: int = 8
    ) -> List[Dict[str, Any]]:
        """
        阶段2：并发提取各章节的子标题

        Args:
            fulltext_md_path: fulltext.md 文件路径
            chapter_headings: 章节标题列表
            level12_headings: 一阶段返回的所有标题（用于获取 volume 边界）
            max_workers: 最大并发数

        Returns:
            各章节的标题结果列表
        """
        from tender_ontology.utils.request.ai_client import AIClient
        from tender_ontology.utils.request.batch_processor import BatchProcessor

        fulltext_md_path = Path(fulltext_md_path)

        if self.verbose:
            print(f"\n[阶段2] 并发提取章节子标题...")
            print(f"[阶段2] 输入文件: {fulltext_md_path.name}")

        # 读取文件
        content = fulltext_md_path.read_text(encoding='utf-8')

        # 切分章节（传入 level12_headings 以处理 volume 边界）
        chapters = self.split_by_chapters(content, chapter_headings, level12_headings)

        if not chapters:
            if self.verbose:
                print(f"[阶段2] 未找到任何章节")
            return []

        model_name = "DeepSeek R1" if self.use_deepseek else "Qwen"
        if self.verbose:
            print(f"[阶段2] 开始并发处理 {len(chapters)} 个章节 (max_workers={max_workers}, model={model_name})")

        # 根据配置选择 API
        if self.use_deepseek:
            # 使用 DeepSeek R1
            ai_client = AIClient(
                model_name=self.deepseek_model,
                base_url=self.deepseek_api_url.replace("/v1/chat/completions", "/v1"),
                api_key=self.deepseek_api_key,
                temperature=0.4,
                top_p=0.7,
                repetition_penalty=1.05,
                max_tokens=8192,
                timeout=120.0
            )
            chapter_system_prompt = get_deepseek_chapter_prompt()
        else:
            # 使用千问（默认）
            ai_client = AIClient(
                model_name=self.INTERNAL_MODEL,
                base_url=self.api_url.replace("/v1/chat/completions", "/v1"),
                api_key="not-needed",
                temperature=0.0,
                top_p=0.7,
                repetition_penalty=1.05,
                max_tokens=8192,
                timeout=120.0
            )
            chapter_system_prompt = get_chapter_prompt()

        # 创建 BatchProcessor
        batch_processor = BatchProcessor(
            ai_client=ai_client,
            verbose=self.verbose,
            max_workers=max_workers
        )

        # 构建批次
        batches = []

        # 统计信息
        chapter_stats = []

        for chapter in chapters:
            # 从章节内容中提取候选标题，构建 markdown 格式
            # DeepSeek 模式：发送全量内容；千问模式：只发送标题候选和短段落
            candidates = self._extract_candidates_from_content(
                chapter['content'],
                full_content=self.use_deepseek
            )

            # 构建 id -> 原始文本 的映射（用于修正千问返回的文本）
            id_to_original_text = {item.get("id"): item.get("text", "") for item in candidates}

            # 构建 markdown 格式
            markdown_lines = []
            heading_count = 0
            paragraph_count = 0
            for item in candidates:
                item_id = item.get("id", "")
                display_text = item.get("display_text", item.get("text", ""))
                is_heading = item.get("is_heading", False)

                # DeepSeek 全量发送模式：只需要 id，不需要 prePara/nextPara
                # 千问模式：需要 prePara/nextPara 辅助判断
                if self.use_deepseek:
                    attrs = f"id={item_id}"
                else:
                    pre_para = item.get("pre_para", "")
                    next_para = item.get("next_para", "")
                    attrs = f"id={item_id}"
                    if pre_para:
                        attrs += f", prePara={pre_para}"
                    if next_para:
                        attrs += f", nextPara={next_para}"

                if is_heading:
                    markdown_lines.append(f"# {display_text} {{{attrs}}}")
                    heading_count += 1
                else:
                    markdown_lines.append(f"- {display_text} {{{attrs}}}")
                    paragraph_count += 1
            markdown_content = "\n".join(markdown_lines)

            # 估算 token 数
            content_chars = len(markdown_content)
            estimated_tokens = content_chars // 2

            # 使用阶段2专用提示词
            context = {
                "chapter_id": chapter.get("id"),
                "chapter_text": chapter.get("text", ""),
                "heading_count": heading_count,
                "paragraph_count": paragraph_count,
                "content_chars": content_chars,
                "estimated_tokens": estimated_tokens,
                "id_to_original_text": id_to_original_text  # 保存原始文本映射
            }
            batches.append((chapter_system_prompt, markdown_content, context))

            # DEBUG: 打印发送给大模型的完整内容
            if self.verbose:
                print(f"\n[DEBUG 阶段2] 章节: {chapter.get('text', '')[:30]}...")
                print(f"[DEBUG 阶段2] 发送内容 ({len(markdown_content)} 字符):")
                print("-" * 60)
                print(markdown_content[:1000] + ("..." if len(markdown_content) > 1000 else ""))
                print("-" * 60)

            # 记录统计信息
            chapter_stats.append({
                "chapter_text": chapter.get("text", "")[:30],
                "heading_count": heading_count,
                "paragraph_count": paragraph_count,
                "content_chars": content_chars,
                "estimated_tokens": estimated_tokens
            })

        # 定义解析函数（保留原始响应，并用原始文本替换模型返回的文本）
        # 使用闭包捕获 self.use_deepseek
        use_deepseek = self.use_deepseek
        deepseek_api = self._deepseek_api
        qwen_api = self._qwen_api
        verbose = self.verbose

        def parse_response_with_raw(response_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
            # 根据使用的模型选择解析器
            if use_deepseek:
                headings = deepseek_api.parse_response(response_text)
            else:
                headings = qwen_api.parse_response(response_text)

            # 用原始文本替换模型返回的文本（模型可能擅自修改文本）
            id_to_original_text = context.get("id_to_original_text", {})
            for heading in headings:
                heading_id = heading.get("id")
                if heading_id and heading_id in id_to_original_text:
                    original_text = id_to_original_text[heading_id]
                    if original_text and heading.get("text") != original_text:
                        if verbose:
                            print(f"[阶段2] pid匹配还原: {heading_id}")
                        heading["text"] = original_text

            return {
                "chapter_id": context.get("chapter_id"),
                "chapter_text": context.get("chapter_text"),
                "headings": headings,
                "raw_response": response_text
            }

        # 并发处理
        try:
            results = batch_processor.process_batches(
                batches=batches,
                parse_response_func=parse_response_with_raw,
                merge_results_func=lambda x: x,
                parallel=True
            )
        except Exception as e:
            if self.verbose:
                print(f"[阶段2] 处理失败: {e}")
            return []

        # 保存二阶段结果到 _unstructured_model.md
        self._save_stage2_model_md(fulltext_md_path, results)

        if self.verbose:
            total_headings = sum(len(r.get("headings", [])) for r in results)
            print(f"\n[阶段2] 完成，共处理 {len(results)} 个章节，提取 {total_headings} 个标题")

            # 打印汇总统计
            print(f"\n{'=' * 80}")
            print(f"[阶段2 Token 统计汇总]")
            print(f"{'=' * 80}")
            print(f"{'章节':<35} {'标题数':>6} {'段落数':>6} {'字符数':>8} {'预估Token':>10}")
            print(f"{'-' * 80}")

            total_heading_count = 0
            total_paragraph_count = 0
            total_chars = 0
            total_tokens = 0

            for stat in chapter_stats:
                chapter_text = stat['chapter_text']
                if len(chapter_text) > 32:
                    chapter_text = chapter_text[:29] + "..."
                print(f"{chapter_text:<35} {stat['heading_count']:>6} {stat['paragraph_count']:>6} {stat['content_chars']:>8} {stat['estimated_tokens']:>10}")

                total_heading_count += stat['heading_count']
                total_paragraph_count += stat['paragraph_count']
                total_chars += stat['content_chars']
                total_tokens += stat['estimated_tokens']

            print(f"{'-' * 80}")
            print(f"{'合计':<35} {total_heading_count:>6} {total_paragraph_count:>6} {total_chars:>8} {total_tokens:>10}")
            print(f"{'=' * 80}")

        return results

    def _save_stage2_model_md(
        self,
        fulltext_md_path: Path,
        chapter_results: List[Dict[str, Any]]
    ) -> Path:
        """
        保存二阶段模型响应结果为 markdown 文件

        Args:
            fulltext_md_path: fulltext.md 文件路径
            chapter_results: 各章节的结果（包含 raw_response）

        Returns:
            保存的文件路径
        """
        base_name = fulltext_md_path.stem.replace('_unstructured_fulltext', '')
        model_md_path = fulltext_md_path.parent / f"{base_name}_unstructured_fulltext_unstructured_model.md"

        lines = []
        lines.append(f"# {base_name} - 模型层级分析结果\n")
        lines.append(f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"> 章节数: {len(chapter_results)}\n")
        lines.append("-" * 80 + "\n")

        for i, result in enumerate(chapter_results):
            chapter_text = result.get("chapter_text", "未知章节")
            chapter_id = result.get("chapter_id", "")
            raw_response = result.get("raw_response", "")

            lines.append(f"\n## 章节 {i + 1}: {chapter_text} {{id={chapter_id}}}\n")

            # 提取 markdown 代码块内容
            markdown_match = re.search(r'```markdown\s*(.*?)\s*```', raw_response, re.DOTALL)
            if markdown_match:
                md_content = markdown_match.group(1).strip()
                lines.append(md_content)
            else:
                lines.append(raw_response.strip() if raw_response else "(无响应)")

            lines.append("\n")

        # 写入文件
        model_md_path.write_text("\n".join(lines), encoding='utf-8')

        if self.verbose:
            print(f"[阶段2] 模型响应已保存: {model_md_path.name}")

        return model_md_path

    def merge_stage2_results(
        self,
        level12_headings: List[Dict[str, Any]],
        chapter_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        聚合二阶段结果

        Args:
            level12_headings: 一阶段返回的一二级标题
            chapter_results: 二阶段返回的各章节结果

        Returns:
            聚合后的完整标题列表
        """
        # 检查是否存在 volume
        volume_pattern = re.compile(r'第[一二三四五六七八九十\d]+[册部分节]')
        has_volume = any(
            volume_pattern.search(h.get("text", ""))
            for h in level12_headings
        )

        if self.verbose:
            print(f"\n[聚合] 是否存在 volume 结构: {has_volume}")

        # 构建 chapter_id -> level 的映射
        chapter_level_map = {}
        for h in level12_headings:
            if h.get("type") == "chapter":
                chapter_level_map[h.get("id")] = h.get("level", 1)

        # 收集所有二阶段中出现的子标题 id（用于去重）
        stage2_sub_ids = set()
        for chapter_result in chapter_results:
            chapter_id = chapter_result.get("chapter_id")
            for sub_h in chapter_result.get("headings", []):
                sub_id = sub_h.get("id")
                # 跳过 chapter 本身
                if sub_id and sub_id != chapter_id:
                    stage2_sub_ids.add(sub_id)

        if self.verbose and stage2_sub_ids:
            print(f"[聚合] 二阶段子标题 ID 数量: {len(stage2_sub_ids)}")

        # 聚合结果
        all_headings = []
        added_ids = set()  # 记录已添加的 id，避免重复

        for h in level12_headings:
            node_id = h.get("id")

            # 如果这个标题已经在二阶段子标题中出现，跳过（避免重复）
            if node_id in stage2_sub_ids and h.get("type") != "chapter":
                if self.verbose:
                    print(f"[聚合] 跳过重复标题: {h.get('text', '')[:30]}... (id={node_id})")
                continue

            if h.get("type") == "chapter":
                all_headings.append(h)
                added_ids.add(node_id)

                # 找到对应的二阶段结果
                chapter_result = next(
                    (r for r in chapter_results if r.get("chapter_id") == node_id),
                    None
                )

                if chapter_result:
                    chapter_original_level = chapter_level_map.get(node_id, 1)
                    level_offset = chapter_original_level - 1

                    # 添加子标题
                    for sub_h in chapter_result.get("headings", []):
                        sub_id = sub_h.get("id")
                        if sub_id != node_id and sub_id not in added_ids:
                            adjusted_heading = sub_h.copy()
                            adjusted_heading["level"] = sub_h.get("level", 1) + level_offset
                            all_headings.append(adjusted_heading)
                            added_ids.add(sub_id)

                    if self.verbose:
                        sub_count = len(chapter_result.get("headings", [])) - 1
                        print(f"[聚合] {h.get('text', '')[:20]}... -> {sub_count} 个子标题 (offset={level_offset})")
            else:
                if node_id not in added_ids:
                    all_headings.append(h)
                    added_ids.add(node_id)

        if self.verbose:
            print(f"[聚合] 总计 {len(all_headings)} 个标题")

        return all_headings

    def extract_headings_by_standalone(
        self,
        fulltext_md_path: Union[str, Path],
        standalone_headings: List[Dict[str, Any]],
        level12_headings: List[Dict[str, Any]] = None,
        max_workers: int = 8
    ) -> List[Dict[str, Any]]:
        """
        阶段2-独立：提取独立功能标题的子标题（合并成一个请求发送）

        Args:
            fulltext_md_path: fulltext.md 文件路径
            standalone_headings: 独立功能标题列表（没有 type 的标题）
            level12_headings: 一阶段返回的所有标题（用于确定边界）
            max_workers: 最大并发数（此方法不使用，保留参数兼容性）

        Returns:
            独立功能区块的标题结果列表
        """
        import requests
        from .heading_prompt import get_standalone_prompt

        fulltext_md_path = Path(fulltext_md_path)

        if not standalone_headings:
            if self.verbose:
                print(f"[阶段2-独立] 无独立功能标题，跳过")
            return []

        if self.verbose:
            print(f"\n[阶段2-独立] 提取独立功能标题子标题...")
            print(f"[阶段2-独立] 独立功能标题数: {len(standalone_headings)}")

        # 读取文件
        content = fulltext_md_path.read_text(encoding='utf-8')

        # 切分独立功能区块
        blocks = self._split_by_standalone(content, standalone_headings, level12_headings)

        if not blocks:
            if self.verbose:
                print(f"[阶段2-独立] 未找到任何独立功能区块")
            return []

        # 合并所有区块内容，构建一个请求
        all_markdown_lines = []
        id_to_original_text = {}
        block_id_list = []  # 记录所有区块的 id

        for block in blocks:
            # 从区块内容中提取候选标题
            candidates = self._extract_candidates_from_content(block['content'])

            # 合并 id -> 原始文本 的映射
            for item in candidates:
                id_to_original_text[item.get("id")] = item.get("text", "")

            # 构建 markdown 格式（附带上下文信息）
            for item in candidates:
                item_id = item.get("id", "")
                display_text = item.get("display_text", item.get("text", ""))
                is_heading = item.get("is_heading", False)
                pre_para = item.get("pre_para", "")
                next_para = item.get("next_para", "")

                # 构建属性字符串
                attrs = f"id={item_id}"
                if pre_para:
                    attrs += f", prePara={pre_para}"
                if next_para:
                    attrs += f", nextPara={next_para}"

                if is_heading:
                    all_markdown_lines.append(f"# {display_text} {{{attrs}}}")
                else:
                    all_markdown_lines.append(f"- {display_text} {{{attrs}}}")

            block_id_list.append(block.get("id"))

        markdown_content = "\n".join(all_markdown_lines)

        if self.verbose:
            print(f"[阶段2-独立] 合并 {len(blocks)} 个区块，共 {len(all_markdown_lines)} 行内容")

        # 发送单个请求
        standalone_system_prompt = get_standalone_prompt()

        payload = {
            "model": self.INTERNAL_MODEL,
            "messages": [
                {"role": "system", "content": standalone_system_prompt},
                {"role": "user", "content": markdown_content}
            ],
            "temperature": 0.0,
            "top_p": 0.7,
            "repetition_penalty": 1.05,
            "max_tokens": 8192
        }

        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=120
            )
            response.raise_for_status()
            result = response.json()
            response_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            if self.verbose:
                print(f"[阶段2-独立] API 调用失败: {e}")
            return []

        # 解析响应
        headings = self._qwen_api.parse_response(response_text)

        # 用原始文本替换千问返回的文本
        for heading in headings:
            heading_id = heading.get("id")
            if heading_id and heading_id in id_to_original_text:
                original_text = id_to_original_text[heading_id]
                if original_text and heading.get("text") != original_text:
                    if self.verbose:
                        print(f"[阶段2-独立] pid匹配还原: {heading_id}")
                    heading["text"] = original_text

        # 构建结果（按区块拆分）
        results = []
        for block in blocks:
            block_id = block.get("id")
            block_headings = [h for h in headings if self._heading_belongs_to_block(h, block, blocks)]
            results.append({
                "block_id": block_id,
                "block_text": block.get("text", ""),
                "headings": block_headings,
                "raw_response": response_text
            })
            if self.verbose:
                print(f"  - {block.get('text', '')[:20]}... -> {len(block_headings)} 个标题")

        if self.verbose:
            total_headings = len(headings)
            print(f"\n[阶段2-独立] 完成，提取 {total_headings} 个标题")
            # 打印 standalone_map 的 key，方便调试
            print(f"[阶段2-独立] 区块 ID: {[r.get('block_id') for r in results]}")

        return results

    def _heading_belongs_to_block(
        self,
        heading: Dict[str, Any],
        block: Dict[str, Any],
        all_blocks: List[Dict[str, Any]]
    ) -> bool:
        """
        判断标题是否属于某个区块

        通过比较 heading 的 id 是否在 block 的内容范围内
        """
        heading_id = heading.get("id", "")
        if not heading_id:
            return False

        # 简单判断：id 以 P_ 开头，提取数字部分比较
        try:
            if heading_id.startswith("P_"):
                heading_num = int(heading_id[2:])
                block_id = block.get("id", "")
                if block_id.startswith("P_"):
                    block_num = int(block_id[2:])

                    # 找到下一个区块的起始 id
                    next_block_num = 999999
                    block_idx = next((i for i, b in enumerate(all_blocks) if b.get("id") == block_id), -1)
                    if block_idx >= 0 and block_idx + 1 < len(all_blocks):
                        next_id = all_blocks[block_idx + 1].get("id", "")
                        if next_id.startswith("P_"):
                            next_block_num = int(next_id[2:])

                    return block_num <= heading_num < next_block_num
        except (ValueError, IndexError):
            pass

        return False

    def _split_by_standalone(
        self,
        fulltext_md_content: str,
        standalone_headings: List[Dict[str, Any]],
        level12_headings: List[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        根据独立功能标题切分 fulltext.md 内容

        Args:
            fulltext_md_content: fulltext.md 的完整内容
            standalone_headings: 独立功能标题列表
            level12_headings: 一阶段返回的所有标题（用于确定边界）

        Returns:
            区块列表
        """
        lines = fulltext_md_content.split('\n')
        id_pattern = re.compile(r'\{id=([^},]+)')

        # 构建 id -> 行号 的映射
        id_to_line = {}
        for i, line in enumerate(lines):
            id_match = id_pattern.search(line)
            if id_match:
                id_to_line[id_match.group(1)] = i

        # 获取所有一级标题的位置（用于确定边界）
        all_level1_lines = []
        if level12_headings:
            for h in level12_headings:
                h_id = h.get("id")
                if h_id and h_id in id_to_line:
                    all_level1_lines.append(id_to_line[h_id])
        all_level1_lines.sort()

        # 切分独立功能区块
        blocks = []
        for standalone in standalone_headings:
            s_id = standalone.get("id")
            s_text = standalone.get("text", "")
            start_line = id_to_line.get(s_id)

            if start_line is None:
                if self.verbose:
                    print(f"  - 警告: 未找到独立标题 {s_text[:20]}... 的位置")
                continue

            # 找下一个一级标题的位置作为结束行
            end_line = len(lines)
            for l1_line in all_level1_lines:
                if l1_line > start_line:
                    end_line = l1_line
                    break

            block_content = '\n'.join(lines[start_line:end_line])

            blocks.append({
                "id": s_id,
                "text": s_text,
                "content": block_content,
                "start_line": start_line,
                "end_line": end_line,
                "line_count": end_line - start_line
            })

            if self.verbose:
                print(f"  - {s_text[:30]}... ({end_line - start_line} 行)")

        if self.verbose:
            print(f"[独立区块切分] 共切分 {len(blocks)} 个区块")

        return blocks

    def merge_all_results(
        self,
        level12_headings: List[Dict[str, Any]],
        chapter_results: List[Dict[str, Any]],
        standalone_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        聚合所有结果（章节 + 独立功能标题）

        Args:
            level12_headings: 一阶段返回的一二级标题
            chapter_results: 章节的二阶段结果
            standalone_results: 独立功能标题的二阶段结果

        Returns:
            聚合后的完整标题列表
        """
        # 先用原来的方法聚合章节结果
        all_headings = self.merge_stage2_results(level12_headings, chapter_results)

        # 构建 block_id -> 结果 的映射
        standalone_map = {r.get("block_id"): r for r in standalone_results}

        if self.verbose:
            print(f"[聚合-独立] standalone_map keys: {list(standalone_map.keys())}")
            # 打印 all_headings 中没有 type 的标题
            no_type_ids = [h.get("id") for h in all_headings if not h.get("type")]
            print(f"[聚合-独立] all_headings 中无 type 的 ID: {no_type_ids}")

        # 找到独立功能标题并插入子标题
        final_headings = []
        added_ids = set()

        for h in all_headings:
            node_id = h.get("id")
            final_headings.append(h)
            added_ids.add(node_id)

            # 如果是独立功能标题，插入其子标题
            if node_id in standalone_map:
                standalone_result = standalone_map[node_id]
                original_level = h.get("level", 1)
                level_offset = original_level - 1

                for sub_h in standalone_result.get("headings", []):
                    sub_id = sub_h.get("id")
                    if sub_id != node_id and sub_id not in added_ids:
                        adjusted_heading = sub_h.copy()
                        adjusted_heading["level"] = sub_h.get("level", 1) + level_offset
                        final_headings.append(adjusted_heading)
                        added_ids.add(sub_id)

                if self.verbose:
                    sub_count = len(standalone_result.get("headings", [])) - 1
                    print(f"[聚合-独立] {h.get('text', '')[:20]}... -> {sub_count} 个子标题")

        if self.verbose:
            print(f"[聚合-全部] 总计 {len(final_headings)} 个标题")

        return final_headings