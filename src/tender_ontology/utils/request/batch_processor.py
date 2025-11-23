"""
批量请求处理器
处理分批发送和结果合并的通用逻辑
"""
from typing import List, Dict, Any, Callable, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


class BatchProcessor:
    """批量请求处理器"""

    def __init__(
        self,
        ai_client=None,
        batch_manager=None,
        verbose: bool = True,
        max_workers: int = 10
    ):
        """
        初始化批量处理器

        Args:
            ai_client: AIClient 实例（如果为 None，将创建默认客户端）
            batch_manager: BatchManager 实例（如果为 None，将使用默认配置）
            verbose: 是否打印详细信息
            max_workers: 最大并发线程数（默认 10）
        """
        self.verbose = verbose
        self.max_workers = max_workers
        self._print_lock = threading.Lock()

        # 延迟导入以避免循环依赖
        from .ai_client import AIClient
        from .batch_manager import BatchManager, get_default_batch_manager

        if ai_client is None:
            self.ai_client = AIClient()
        else:
            self.ai_client = ai_client

        if batch_manager is None:
            self.batch_manager = get_default_batch_manager()
        else:
            self.batch_manager = batch_manager

    def _print_thread_safe(self, message: str):
        """线程安全的打印"""
        if self.verbose:
            with self._print_lock:
                print(message)

    def _process_single_batch(
        self,
        batch_idx: int,
        total_batches: int,
        system_prompt: str,
        user_prompt: str,
        context: Any,
        parse_response_func: Callable[[str, Any], dict],
        request_params: dict
    ) -> Tuple[int, Optional[dict]]:
        """
        处理单个批次

        Returns:
            (batch_idx, result_dict) 或 (batch_idx, None) 如果失败
        """
        try:
            self._print_thread_safe(f"\n[Batch {batch_idx}/{total_batches}] 开始发送请求")

            # 发送请求
            response_text = self.ai_client.send_request(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                verbose=False,  # 并发时关闭详细输出，避免混乱
                **request_params
            )

            # 解析结果
            batch_result = parse_response_func(response_text, context)

            self._print_thread_safe(f"[Batch {batch_idx}/{total_batches}] 处理成功")

            return (batch_idx, batch_result)

        except Exception as e:
            self._print_thread_safe(f"[Batch {batch_idx}/{total_batches}] 处理失败: {e}")
            return (batch_idx, None)

    def process_batches(
        self,
        batches: List[Tuple[str, str, Any]],
        parse_response_func: Callable[[str, Any], dict],
        merge_results_func: Callable[[List[dict]], dict],
        parallel: bool = True,
        **request_params
    ) -> dict:
        """
        通用的批量请求处理流程（支持并行）

        Args:
            batches: 批次列表，每个元素为 (system_prompt, user_prompt, context)
            parse_response_func: 解析单个响应的函数，签名为 (response_text: str, context: Any) -> dict
            merge_results_func: 合并多个结果的函数，签名为 (results: List[dict]) -> dict
            parallel: 是否并行处理（默认 True）
            **request_params: 传递给 AIClient.send_request 的参数

        Returns:
            合并后的最终结果
        """
        if not batches:
            raise ValueError("批次列表不能为空")

        total_batches = len(batches)

        if self.verbose:
            mode = "并行" if parallel else "串行"
            print(f"\n[BatchProcessor] 开始{mode}处理 {total_batches} 个批次")
            if parallel:
                print(f"[BatchProcessor] 最大并发数: {self.max_workers}")

        if not parallel:
            # 串行处理（原逻辑）
            return self._process_batches_serial(
                batches, parse_response_func, merge_results_func, **request_params
            )

        # 并行处理
        all_results = [None] * total_batches  # 预分配结果列表，保持顺序

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_idx = {}
            for batch_idx, (system_prompt, user_prompt, context) in enumerate(batches, 1):
                future = executor.submit(
                    self._process_single_batch,
                    batch_idx,
                    total_batches,
                    system_prompt,
                    user_prompt,
                    context,
                    parse_response_func,
                    request_params
                )
                future_to_idx[future] = batch_idx

            # 收集结果
            success_count = 0
            for future in as_completed(future_to_idx):
                batch_idx, result = future.result()
                if result is not None:
                    all_results[batch_idx - 1] = result  # 保持原始顺序
                    success_count += 1

        # 过滤掉失败的批次
        all_results = [r for r in all_results if r is not None]

        if not all_results:
            raise Exception("所有批次都处理失败")

        if self.verbose:
            print(f"\n[BatchProcessor] 成功处理 {success_count}/{total_batches} 个批次")

        # 合并结果（第 104 行：结果汇总入口）
        if self.verbose:
            print(f"\n{'=' * 80}")
            print(f"[BatchProcessor] 合并 {len(all_results)} 个批次的结果")
            print(f"{'=' * 80}")

        final_result = merge_results_func(all_results)

        if self.verbose:
            print(f"\n[BatchProcessor] 处理完成")

        return final_result

    def _process_batches_serial(
        self,
        batches: List[Tuple[str, str, Any]],
        parse_response_func: Callable[[str, Any], dict],
        merge_results_func: Callable[[List[dict]], dict],
        **request_params
    ) -> dict:
        """串行处理批次（原逻辑）"""
        all_results = []

        for batch_idx, (system_prompt, user_prompt, context) in enumerate(batches, 1):
            if self.verbose:
                print(f"\n{'=' * 80}")
                print(f"[Batch {batch_idx}/{len(batches)}] 发送请求")
                print(f"{'=' * 80}")

            try:
                # 发送请求
                response_text = self.ai_client.send_request(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    verbose=self.verbose,
                    **request_params
                )

                # 解析结果
                batch_result = parse_response_func(response_text, context)
                all_results.append(batch_result)

                if self.verbose:
                    print(f"[Batch {batch_idx}/{len(batches)}] 处理成功")

            except Exception as e:
                print(f"\n[Batch {batch_idx}/{len(batches)}] 处理失败: {e}")
                # 继续处理下一个批次
                continue

        if not all_results:
            raise Exception("所有批次都处理失败")

        # 合并结果
        if self.verbose:
            print(f"\n{'=' * 80}")
            print(f"[BatchProcessor] 合并 {len(all_results)} 个批次的结果")
            print(f"{'=' * 80}")

        final_result = merge_results_func(all_results)

        if self.verbose:
            print(f"\n[BatchProcessor] 处理完成")

        return final_result


def merge_candidates_with_dedup(
    all_results: List[dict],
    candidates_key: str = "candidates",
    id_key: str = "id",
    score_key: str = "score",
    verbose: bool = True
) -> dict:
    """
    通用的候选结果合并函数（带去重和排序）

    Args:
        all_results: 所有批次的结果列表
        candidates_key: 候选列表的键名
        id_key: 候选项中 ID 的键名
        score_key: 候选项中分数的键名
        verbose: 是否打印详细信息

    Returns:
        合并后的结果，包含去重和排序后的候选列表
    """
    all_candidates = []

    # 收集所有候选
    for result in all_results:
        candidates = result.get(candidates_key, [])
        all_candidates.extend(candidates)

    if verbose:
        print(f"[merge_candidates_with_dedup] 收集到 {len(all_candidates)} 个候选")

    # 去重（基于 ID）
    seen_ids = set()
    unique_candidates = []

    for candidate in all_candidates:
        item_id = candidate.get(id_key)
        if item_id not in seen_ids:
            seen_ids.add(item_id)
            unique_candidates.append(candidate)
        elif verbose:
            print(f"[去重] 跳过重复的 {id_key}: {item_id}")

    if verbose:
        print(f"[merge_candidates_with_dedup] 去重后: {len(unique_candidates)} 个候选")

    # 按分数降序排序
    unique_candidates.sort(key=lambda x: x.get(score_key, 0), reverse=True)

    return {
        candidates_key: unique_candidates,
        "total_candidates": len(all_candidates),
        "unique_candidates": len(unique_candidates),
        "batch_count": len(all_results)
    }


# 全局默认实例
_default_processor: Optional[BatchProcessor] = None


def get_default_batch_processor(**config) -> BatchProcessor:
    """获取默认的批量处理器（单例）"""
    global _default_processor
    if _default_processor is None:
        _default_processor = BatchProcessor(**config)
    return _default_processor


def reset_default_batch_processor():
    """重置默认批量处理器"""
    global _default_processor
    _default_processor = None


if __name__ == "__main__":
    # 测试示例
    print("BatchProcessor 模块已加载")
    print("使用示例请参考 tag_prompt.py 中的 process_h1_detection_with_batching 函数")