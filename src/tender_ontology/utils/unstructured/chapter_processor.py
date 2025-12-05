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

from .heading_prompt import get_chapter_prompt
from .qwen_heading_api import QwenHeadingAPI


class ChapterProcessor:
    """章节处理器"""

    # 内部千问模型
    INTERNAL_MODEL = "qwen3-32b"

    def __init__(self, verbose: bool = True):
        """
        初始化章节处理器

        Args:
            verbose: 是否打印详细信息
        """
        self.verbose = verbose
        self._qwen_api = QwenHeadingAPI(verbose=False)

    @property
    def api_url(self) -> str:
        """从配置读取千问 API URL"""
        from tender_ontology.config.settings import settings
        return settings.qwen_api_url

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

    def _extract_candidates_from_content(self, content: str) -> List[Dict[str, Any]]:
        """
        从 markdown 内容中提取章节内容（标题完整发送，正文缩略）

        Args:
            content: markdown 格式的章节内容

        Returns:
            候选内容列表，每个元素包含 id, text, is_heading
        """
        candidates = []
        id_pattern = re.compile(r'\{id=([^},]+)')

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
                # 标题完整发送，正文大于20字符直接跳过
                if is_heading:
                    candidates.append({
                        "id": item_id,
                        "text": text,
                        "display_text": text,
                        "is_heading": True
                    })
                elif len(text) < 20:
                    # 只保留短段落（可能是遗漏的标题）
                    candidates.append({
                        "id": item_id,
                        "text": text,
                        "display_text": text,
                        "is_heading": False
                    })
                # 长段落直接跳过，不发送给模型

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

        if self.verbose:
            print(f"[阶段2] 开始并发处理 {len(chapters)} 个章节 (max_workers={max_workers})")

        # 创建 AI 客户端
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

        # 创建 BatchProcessor
        batch_processor = BatchProcessor(
            ai_client=ai_client,
            verbose=self.verbose,
            max_workers=max_workers
        )

        # 构建批次（使用阶段2专用提示词）
        batches = []
        chapter_system_prompt = get_chapter_prompt()

        # 统计信息
        chapter_stats = []

        for chapter in chapters:
            # 从章节内容中提取候选标题，构建 markdown 格式
            candidates = self._extract_candidates_from_content(chapter['content'])

            # 构建 markdown 格式
            markdown_lines = []
            heading_count = 0
            paragraph_count = 0
            for item in candidates:
                item_id = item.get("id", "")
                display_text = item.get("display_text", item.get("text", ""))
                is_heading = item.get("is_heading", False)

                if is_heading:
                    markdown_lines.append(f"# {display_text} {{id={item_id}}}")
                    heading_count += 1
                else:
                    markdown_lines.append(f"- {display_text} {{id={item_id}}}")
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
                "estimated_tokens": estimated_tokens
            }
            batches.append((chapter_system_prompt, markdown_content, context))

            # 记录统计信息
            chapter_stats.append({
                "chapter_text": chapter.get("text", "")[:30],
                "heading_count": heading_count,
                "paragraph_count": paragraph_count,
                "content_chars": content_chars,
                "estimated_tokens": estimated_tokens
            })

        # 定义解析函数（保留原始响应）
        def parse_response_with_raw(response_text: str, context: Dict[str, Any]) -> Dict[str, Any]:
            headings = self._qwen_api.parse_response(response_text)
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