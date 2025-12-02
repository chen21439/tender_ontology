"""
AI 模型配置
定义项目中使用的各种 AI 模型

模型选择指南：
- ERNIE-Speed: 快速响应，适合结构化输出、分类任务
- ERNIE-Lite: 轻量级，适合简单判断
- ERNIE-4.0-Turbo: 平衡性能和质量，适合通用场景
- ERNIE-Thinking: 复杂推理（慢，谨慎使用）
- Qwen-Long: 超长文档处理，支持 file_id 模式
"""
from enum import Enum


class BaiduModel(str, Enum):
    """百度千帆模型枚举"""

    # ERNIE 4.0 系列
    ERNIE_4_0_TURBO_128K = "ernie-4.0-turbo-128k"
    ERNIE_4_0_TURBO_8K = "ernie-4.0-turbo-8k"
    ERNIE_4_0_8K = "ernie-4.0-8k"

    # ERNIE 3.5 系列
    ERNIE_3_5_8K = "ernie-3.5-8k"
    ERNIE_3_5_128K = "ernie-3.5-128k"

    # ERNIE Speed 系列
    ERNIE_SPEED_128K = "ernie-speed-128k"
    ERNIE_SPEED_8K = "ernie-speed-8k"

    # ERNIE Lite 系列
    ERNIE_LITE_8K = "ernie-lite-8k"

    # ERNIE Tiny 系列
    ERNIE_TINY_8K = "ernie-tiny-8k"

    # ERNIE 5.0 系列（推理增强）
    ERNIE_5_0_THINKING_LATEST = "ernie-5.0-thinking-latest"

    @property
    def display_name(self) -> str:
        """返回模型的显示名称"""
        display_names = {
            self.ERNIE_4_0_TURBO_128K: "ERNIE 4.0 Turbo (128K)",
            self.ERNIE_4_0_TURBO_8K: "ERNIE 4.0 Turbo (8K)",
            self.ERNIE_4_0_8K: "ERNIE 4.0 (8K)",
            self.ERNIE_3_5_8K: "ERNIE 3.5 (8K)",
            self.ERNIE_3_5_128K: "ERNIE 3.5 (128K)",
            self.ERNIE_SPEED_128K: "ERNIE Speed (128K)",
            self.ERNIE_SPEED_8K: "ERNIE Speed (8K)",
            self.ERNIE_LITE_8K: "ERNIE Lite (8K)",
            self.ERNIE_TINY_8K: "ERNIE Tiny (8K)",
            self.ERNIE_5_0_THINKING_LATEST: "ERNIE 5.0 Thinking (Latest)",
        }
        return display_names.get(self, self.value)

    @property
    def max_tokens(self) -> int:
        """返回模型的最大 token 数"""
        max_tokens_map = {
            self.ERNIE_4_0_TURBO_128K: 131072,  # 128K 上下文
            self.ERNIE_4_0_TURBO_8K: 8192,
            self.ERNIE_4_0_8K: 8192,
            self.ERNIE_3_5_8K: 8192,
            self.ERNIE_3_5_128K: 131072,
            self.ERNIE_SPEED_128K: 131072,
            self.ERNIE_SPEED_8K: 8192,
            self.ERNIE_LITE_8K: 8192,
            self.ERNIE_TINY_8K: 8192,
            self.ERNIE_5_0_THINKING_LATEST: 131072,  # 128K 上下文
        }
        return max_tokens_map.get(self, 8192)


class QwenModel(str, Enum):
    """通义千问模型枚举"""

    # Qwen-Long 系列（超长文档处理）
    QWEN_LONG = "qwen-long"

    # Qwen-Turbo 系列（快速响应）
    QWEN_TURBO = "qwen-turbo"
    QWEN_TURBO_LATEST = "qwen-turbo-latest"

    # Qwen-Plus 系列（平衡性能）
    QWEN_PLUS = "qwen-plus"
    QWEN_PLUS_LATEST = "qwen-plus-latest"

    # Qwen-Max 系列（最高性能）
    QWEN_MAX = "qwen-max"
    QWEN_MAX_LATEST = "qwen-max-latest"

    @property
    def display_name(self) -> str:
        """返回模型的显示名称"""
        display_names = {
            self.QWEN_LONG: "Qwen-Long (超长文档)",
            self.QWEN_TURBO: "Qwen-Turbo",
            self.QWEN_TURBO_LATEST: "Qwen-Turbo (Latest)",
            self.QWEN_PLUS: "Qwen-Plus",
            self.QWEN_PLUS_LATEST: "Qwen-Plus (Latest)",
            self.QWEN_MAX: "Qwen-Max",
            self.QWEN_MAX_LATEST: "Qwen-Max (Latest)",
        }
        return display_names.get(self, self.value)

    @property
    def max_tokens(self) -> int:
        """返回模型的最大 token 数"""
        max_tokens_map = {
            self.QWEN_LONG: 1000000,  # 1M tokens 上下文
            self.QWEN_TURBO: 131072,  # 128K 上下文
            self.QWEN_TURBO_LATEST: 131072,
            self.QWEN_PLUS: 131072,
            self.QWEN_PLUS_LATEST: 131072,
            self.QWEN_MAX: 131072,
            self.QWEN_MAX_LATEST: 131072,
        }
        return max_tokens_map.get(self, 131072)


# 任务类型枚举（用于选择最合适的模型）
class TaskType(str, Enum):
    """任务类型，自动映射到最优模型"""

    # 文档结构分析任务
    HIERARCHY_PREDICTION = "hierarchy_prediction"      # 标题层级关系预测
    SECTION_CLASSIFICATION = "section_classification"  # 段落分类（标题/正文/表格）

    # 文本生成任务
    TEXT_GENERATION = "text_generation"                # 通用文本生成
    SUMMARIZATION = "summarization"                    # 文本摘要

    # 分类与判断任务
    BINARY_CLASSIFICATION = "binary_classification"    # 二分类（是/否）
    MULTI_CLASSIFICATION = "multi_classification"      # 多分类

    # 推理任务
    COMPLEX_REASONING = "complex_reasoning"            # 复杂推理（需要多步思考）
    SIMPLE_REASONING = "simple_reasoning"              # 简单推理

    def get_recommended_model(self) -> BaiduModel:
        """获取该任务推荐的模型"""
        task_model_map = {
            # 文档结构分析 -> ERNIE-4.0-Turbo-128K（大上下文 + 高质量）
            # 注意：244 个候选项需要 ~26K tokens，必须用 128K 模型
            self.HIERARCHY_PREDICTION: BaiduModel.ERNIE_4_0_TURBO_128K,
            self.SECTION_CLASSIFICATION: BaiduModel.ERNIE_4_0_TURBO_128K,

            # 文本生成 -> ERNIE-4.0-Turbo-8K（质量 + 速度平衡）
            self.TEXT_GENERATION: BaiduModel.ERNIE_4_0_TURBO_8K,
            self.SUMMARIZATION: BaiduModel.ERNIE_4_0_TURBO_8K,

            # 分类判断 -> ERNIE-Lite（轻量快速）
            self.BINARY_CLASSIFICATION: BaiduModel.ERNIE_LITE_8K,
            self.MULTI_CLASSIFICATION: BaiduModel.ERNIE_LITE_8K,

            # 推理任务 -> 根据复杂度选择
            self.SIMPLE_REASONING: BaiduModel.ERNIE_4_0_TURBO_8K,
            self.COMPLEX_REASONING: BaiduModel.ERNIE_4_0_TURBO_8K,  # 不要用 Thinking，太慢
        }
        return task_model_map.get(self, BaiduModel.ERNIE_4_0_TURBO_8K)


# 默认模型配置（向后兼容）
class DefaultModels:
    """默认使用的模型配置"""

    # 文本理解与生成（通用场景）
    TEXT_GENERATION = TaskType.TEXT_GENERATION.get_recommended_model()

    # 文档结构分析（层级关系预测）
    # 使用 ERNIE-4.0-Turbo-128K：大上下文窗口（支持 ~26K tokens 输入）
    # 任务特点：244 个候选项判断 + 关系预测（parent_id, left_sibling_id）
    DOCUMENT_HIERARCHY = TaskType.HIERARCHY_PREDICTION.get_recommended_model()

    # 快速分类/标注任务（简单的是非判断）
    FAST_TASK = TaskType.BINARY_CLASSIFICATION.get_recommended_model()

    # 复杂推理任务（需要多步思考）
    REASONING_TASK = TaskType.COMPLEX_REASONING.get_recommended_model()

    # Qwen 模型（超长文档处理）
    QWEN_LONG_DOC = QwenModel.QWEN_LONG