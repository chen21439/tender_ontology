"""
AI 请求客户端
提供统一的 AI 模型调用接口
"""
from typing import Dict, Any, Optional, List
from openai import OpenAI
import time


class AIClient:
    """统一的 AI 客户端"""

    # 默认配置
    DEFAULT_CONFIG = {
        "model_name": "qwen3-14b",
        "base_url": "http://112.111.54.86:10011/v1",
        "api_key": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1aWQiOiIxOTE3MTIzNDc4NDI5ODg4NTEzIiwiZGVwdE5hbWUiOiIiLCJhcmVhQ29kZSI6IiIsInJvbGUiOiJjdXN0b20iLCJhcmVhTmFtZSI6IiIsImNyZWF0ZVRpbWUiOjE3NTg1OTY0ODQsImFwcElkIjoiMTAwMDAwMDAwMDAwMDAwMDAiLCJ0ZWxlcGhvbmUiOiIxODc1MDc5OTAxOSIsInVzZXJUeXBlIjoiaW5zaWRlIiwidXNlcm5hbWUiOiJjaGVueGlhb21pbiJ9.EtvuTHzkSfozetNefVBz4jMjhbHkGi3V-JtWp6_WebU",
        "temperature": 0.0,
        "max_tokens": 8192,
        "top_p": 1.0,
        "repetition_penalty": 1.0,
        "timeout": 60.0
    }

    def __init__(
        self,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        **kwargs
    ):
        """
        初始化 AI 客户端

        Args:
            model_name: 模型名称
            base_url: API 地址
            api_key: API 密钥
            **kwargs: 其他参数（temperature, max_tokens, top_p, repetition_penalty 等）
        """
        # 合并配置
        self.config = {**self.DEFAULT_CONFIG}

        if model_name:
            self.config["model_name"] = model_name
        if base_url:
            self.config["base_url"] = base_url
        if api_key:
            self.config["api_key"] = api_key

        # 更新其他参数
        for key, value in kwargs.items():
            if key in self.config:
                self.config[key] = value

        # 初始化 OpenAI 客户端
        self.client = OpenAI(
            api_key=self.config["api_key"],
            base_url=self.config["base_url"]
        )

        print(f"[AIClient] 初始化完成，模型: {self.config['model_name']}")

    def create_request_body(
        self,
        system_prompt: str,
        user_prompt: str,
        **override_params
    ) -> Dict[str, Any]:
        """
        构建请求体

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            **override_params: 覆盖默认参数（如 temperature, max_tokens 等）

        Returns:
            请求体字典
        """
        # 基础参数
        body = {
            "model": override_params.get("model", self.config["model_name"]),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": override_params.get("temperature", self.config["temperature"]),
            "max_tokens": override_params.get("max_tokens", self.config["max_tokens"]),
            "top_p": override_params.get("top_p", self.config["top_p"]),
        }

        # extra_body 参数
        extra_body = {}
        if "repetition_penalty" in override_params:
            extra_body["repetition_penalty"] = override_params["repetition_penalty"]
        elif "repetition_penalty" in self.config:
            extra_body["repetition_penalty"] = self.config["repetition_penalty"]

        if extra_body:
            body["extra_body"] = extra_body

        return body

    def send_request(
        self,
        system_prompt: str,
        user_prompt: str,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        verbose: bool = True,
        **override_params
    ) -> str:
        """
        发送请求并返回响应

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
            verbose: 是否打印详细信息
            **override_params: 覆盖默认参数

        Returns:
            AI 响应文本

        Raises:
            Exception: 所有重试失败后抛出最后一次异常
        """
        if verbose:
            print("\n" + "=" * 80)
            print("[AIClient] 发送请求")
            print("=" * 80)
            print(f"System Prompt (前200字):\n{system_prompt[:200]}...\n")
            print(f"User Prompt (前200字):\n{user_prompt[:200]}...")
            print("=" * 80 + "\n")

        last_error = None

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"[AIClient] 重试 {attempt}/{max_retries - 1}...")
                    time.sleep(retry_delay)

                # 构建请求参数
                timeout = override_params.get("timeout", self.config["timeout"])
                request_params = self.create_request_body(
                    system_prompt,
                    user_prompt,
                    **override_params
                )

                # 发送请求
                response = self.client.chat.completions.create(
                    **request_params,
                    timeout=timeout
                )

                result_text = response.choices[0].message.content.strip()

                if verbose:
                    print("\n" + "=" * 80)
                    print("[AIClient] 收到响应")
                    print("=" * 80)
                    print(result_text[:500] + ("..." if len(result_text) > 500 else ""))
                    print("=" * 80 + "\n")

                return result_text

            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    print(f"[AIClient] 请求失败: {e}，将在 {retry_delay} 秒后重试...")
                else:
                    print(f"[AIClient] 请求失败（已重试 {max_retries} 次）: {e}")

        # 所有重试都失败
        raise Exception(f"AI 请求失败: {last_error}")

    def send_request_safe(
        self,
        system_prompt: str,
        user_prompt: str,
        default_response: str = "",
        **kwargs
    ) -> str:
        """
        发送请求（安全版本，不会抛出异常）

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            default_response: 失败时的默认响应
            **kwargs: 其他参数

        Returns:
            AI 响应文本或默认响应
        """
        try:
            return self.send_request(system_prompt, user_prompt, **kwargs)
        except Exception as e:
            print(f"[AIClient] 请求失败，返回默认响应: {e}")
            return default_response


# 全局单例（可选）
_global_client: Optional[AIClient] = None


def get_global_client(**config) -> AIClient:
    """获取全局 AI 客户端（单例模式）"""
    global _global_client
    if _global_client is None:
        _global_client = AIClient(**config)
    return _global_client


def reset_global_client():
    """重置全局客户端"""
    global _global_client
    _global_client = None


if __name__ == "__main__":
    # 测试示例
    client = AIClient()

    system_prompt = "你是一个AI助手，擅长回答问题。"
    user_prompt = "1+1等于几？"

    try:
        response = client.send_request(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=100
        )
        print(f"\n最终响应:\n{response}")
    except Exception as e:
        print(f"\n请求失败: {e}")