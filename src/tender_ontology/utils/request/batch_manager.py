"""
批量请求管理器
基于 token 限制智能分批发送请求
"""
from typing import List, Dict, Any, Callable, Optional

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    print("[BatchManager] 警告: tiktoken 未安装，将使用简单估算方法（1 token ≈ 1.5 字符）")


class BatchManager:
    """智能分批管理器"""

    def __init__(
        self,
        max_context_tokens: int = 32768,
        max_output_tokens: int = 8192,
        safety_margin: float = 0.1,
        encoding_name: str = "cl100k_base"
    ):
        """
        初始化分批管理器

        Args:
            max_context_tokens: 模型上下文窗口大小
            max_output_tokens: 输出最大 token
            safety_margin: 安全边际（比例，默认 10%）
            encoding_name: tiktoken 编码名称
        """
        self.max_context_tokens = max_context_tokens
        self.max_output_tokens = max_output_tokens
        self.max_input_tokens = max_context_tokens - max_output_tokens
        self.safety_margin = safety_margin

        # 初始化 tiktoken encoder（如果可用）
        self._encoder = None
        if TIKTOKEN_AVAILABLE:
            try:
                self._encoder = tiktoken.get_encoding(encoding_name)
            except Exception as e:
                print(f"[BatchManager] 警告: tiktoken 初始化失败: {e}")

    def count_tokens(self, text: str) -> int:
        """
        计算文本的 token 数量

        Args:
            text: 要计算的文本

        Returns:
            token 数量
        """
        if self._encoder:
            # 使用 tiktoken 精确计算
            return len(self._encoder.encode(text))
        else:
            # 简单估算：1 token ≈ 1.5 字符
            return int(len(text) / 1.5)

    def split_items_by_tokens(
        self,
        items: List[Any],
        system_prompt: str,
        build_item_content_func: Callable[[Any], str],
        prompt_header: str = "",
        prompt_footer: str = ""
    ) -> List[List[Any]]:
        """
        根据 token 限制将 items 分批

        Args:
            items: 要处理的项目列表
            system_prompt: 系统提示词
            build_item_content_func: 构建单个 item 内容的函数
            prompt_header: 用户提示词的头部固定内容
            prompt_footer: 用户提示词的尾部固定内容

        Returns:
            分批后的 items 列表
        """
        if not items:
            return []

        # 计算固定开销
        system_tokens = self.count_tokens(system_prompt)
        header_tokens = self.count_tokens(prompt_header)
        footer_tokens = self.count_tokens(prompt_footer)
        base_tokens = system_tokens + header_tokens + footer_tokens

        # 有效最大 token（预留安全边际）
        effective_max_tokens = int(self.max_input_tokens * (1 - self.safety_margin))

        print(f"[BatchManager] Token 配置:")
        print(f"  - 上下文窗口: {self.max_context_tokens}")
        print(f"  - 最大输出: {self.max_output_tokens}")
        print(f"  - 最大输入: {self.max_input_tokens}")
        print(f"  - 有效最大输入: {effective_max_tokens}")
        print(f"  - 固定开销: {base_tokens}")

        batches = []
        current_batch = []
        current_tokens = base_tokens

        for item in items:
            # 计算这个 item 的 token
            item_content = build_item_content_func(item)
            item_tokens = self.count_tokens(item_content)

            # 如果加上这个 item 超过限制，先保存当前批次
            if current_batch and (current_tokens + item_tokens > effective_max_tokens):
                batches.append(current_batch)
                print(f"[BatchManager] 批次 {len(batches)}: {len(current_batch)} 个项目, ~{current_tokens} tokens")
                current_batch = [item]
                current_tokens = base_tokens + item_tokens
            else:
                current_batch.append(item)
                current_tokens += item_tokens

        # 添加最后一批
        if current_batch:
            batches.append(current_batch)
            print(f"[BatchManager] 批次 {len(batches)}: {len(current_batch)} 个项目, ~{current_tokens} tokens")

        print(f"[BatchManager] 总共分为 {len(batches)} 个批次")
        return batches

    def estimate_tokens(self, text: str) -> int:
        """估算文本的 token 数（别名方法）"""
        return self.count_tokens(text)


# 全局默认配置
DEFAULT_BATCH_MANAGER = None


def get_default_batch_manager(**config) -> BatchManager:
    """获取默认的批量管理器（单例）"""
    global DEFAULT_BATCH_MANAGER
    if DEFAULT_BATCH_MANAGER is None:
        DEFAULT_BATCH_MANAGER = BatchManager(**config)
    return DEFAULT_BATCH_MANAGER


def reset_default_batch_manager():
    """重置默认批量管理器"""
    global DEFAULT_BATCH_MANAGER
    DEFAULT_BATCH_MANAGER = None


if __name__ == "__main__":
    # 测试示例
    manager = BatchManager(
        max_context_tokens=8192,
        max_output_tokens=2048
    )

    # 模拟 items
    items = [
        {"id": i, "content": "这是一段测试文本" * 50}
        for i in range(100)
    ]

    system_prompt = "你是一个助手"
    prompt_header = "请处理以下内容:\n"
    prompt_footer = "\n请输出 JSON 格式的结果"

    def build_item_content(item):
        return f"## 项目 {item['id']}\n{item['content']}\n"

    # 分批
    batches = manager.split_items_by_tokens(
        items,
        system_prompt,
        build_item_content,
        prompt_header,
        prompt_footer
    )

    print(f"\n分批结果: {len(batches)} 个批次")
    for i, batch in enumerate(batches, 1):
        print(f"批次 {i}: {len(batch)} 个项目")