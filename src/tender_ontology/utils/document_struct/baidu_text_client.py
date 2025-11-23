"""
百度千帆纯文本 API 客户端
用于调用 ERNIE-Bot 等纯文本模型
"""
import requests
import json
from typing import Optional


class BaiduTextClient:
    """百度千帆纯文本客户端"""

    # 默认配置
    DEFAULT_API_KEY = "bce-v3/ALTAK-JkjnSArfweuMYH0Rr0RIN/45271747bda2067bcc0c855c7a6b6f61edd5b51f"
    DEFAULT_MODEL = "ernie-4.0-turbo-8k"  # 默认使用 ERNIE-4.0-Turbo

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL
    ):
        """
        初始化百度千帆文本客户端

        Args:
            api_key: 百度 API Key（bce-v3/ALTAK...格式）
            model: 模型名称，默认 ernie-4.0-turbo-8k
                可选模型：
                - ernie-4.0-turbo-8k: ERNIE 4.0 Turbo（推荐）
                - ernie-4.0-8k: ERNIE 4.0
                - ernie-3.5-8k: ERNIE 3.5
                - ernie-speed-8k: ERNIE Speed（高速）
        """
        self.api_key = api_key or self.DEFAULT_API_KEY
        self.model = model
        self.base_url = "https://qianfan.baidubce.com/v2/chat/completions"

        print(f"[BaiduTextClient] 初始化完成")
        print(f"  - Model: {model}")
        print(f"  - API Key: {self.api_key[:20]}...{self.api_key[-10:]}")

    def send_request(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.000001,
        top_p: float = 1.0,
        max_tokens: int = 2048,
        verbose: bool = True
    ) -> str:
        """
        发送文本请求

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）
            temperature: 温度参数（0-1）
            top_p: top_p 参数（0-1）
            max_tokens: 最大生成 token 数
            verbose: 是否打印详细信息

        Returns:
            AI 响应文本
        """
        # 构建 messages
        messages = []

        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })

        messages.append({
            "role": "user",
            "content": prompt
        })

        # 构建请求体
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens
        }

        # 设置 Header（Bearer 鉴权）
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        if verbose:
            print(f"\n{'=' * 80}")
            print(f"[BaiduTextClient] 发送请求")
            print(f"{'=' * 80}")
            print(f"Model: {self.model}")
            print(f"Prompt (前200字): {prompt[:200]}...")
            print(f"Temperature: {temperature}, Top_p: {top_p}")
            print(f"{'=' * 80}\n")

        # 发送 POST 请求
        try:
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=120
            )
            response.raise_for_status()

            # 解析响应
            result = response.json()

            # 检查错误
            if "error_code" in result or "error" in result:
                error_msg = f"API错误: {result.get('error_code', result.get('error', 'Unknown'))} - {result.get('error_msg', result.get('message', ''))}"
                raise Exception(error_msg)

            # 提取 choices[0].message.content
            if "choices" in result and len(result["choices"]) > 0:
                answer = result["choices"][0]["message"]["content"]
            else:
                answer = result.get("result", "")

            if verbose:
                print(f"\n{'=' * 80}")
                print(f"[BaiduTextClient] 收到响应")
                print(f"{'=' * 80}")
                print(answer[:500] + ("..." if len(answer) > 500 else ""))
                print(f"{'=' * 80}\n")

            return answer

        except requests.exceptions.HTTPError as e:
            print(f"\n[错误] HTTP 请求失败:")
            print(f"  - Status Code: {response.status_code}")
            print(f"  - Response: {response.text}")
            raise Exception(f"HTTP错误 {response.status_code}: {response.text}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"请求失败: {e}")
        except Exception as e:
            raise Exception(f"处理响应失败: {e}")


# 全局单例
_global_text_client: Optional[BaiduTextClient] = None


def get_baidu_text_client(
    api_key: Optional[str] = None,
    model: str = BaiduTextClient.DEFAULT_MODEL
) -> BaiduTextClient:
    """获取全局百度文本客户端（单例模式）"""
    global _global_text_client
    if _global_text_client is None:
        _global_text_client = BaiduTextClient(
            api_key=api_key,
            model=model
        )
    return _global_text_client


def reset_baidu_text_client():
    """重置全局客户端"""
    global _global_text_client
    _global_text_client = None


if __name__ == "__main__":
    print("""
BaiduTextClient 模块已加载

使用示例:

from tender_ontology.utils.document_struct.baidu_text_client import BaiduTextClient

# 方式1：使用默认配置
client = BaiduTextClient()

# 方式2：自定义配置
client = BaiduTextClient(
    api_key="your_api_key",
    model="ernie-4.0-turbo-8k"
)

# 发送请求
response = client.send_request(
    prompt="请帮我分析这段文档...",
    system_prompt="你是一个专业的文档分析专家",
    temperature=0.7
)

print(response)
    """)