"""
通义千问 API 客户端
支持文件上传模式（file_id）和直接文本模式
"""
import requests
import json
import os
from typing import Optional, Union, List, Dict, Any
from pathlib import Path


class QwenClient:
    """通义千问 API 客户端（支持 file_id 模式）"""

    # API 端点
    FILES_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/files"
    CHAT_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "qwen-long"
    ):
        """
        初始化通义千问客户端

        Args:
            api_key: 通义千问 API Key（如果为 None，从环境变量 DASHSCOPE_API_KEY 读取）
            model: 模型名称，默认 qwen-long（支持长文档）
        """
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise ValueError("未找到 API Key，请传入 api_key 或设置环境变量 DASHSCOPE_API_KEY")

        self.model = model
        self.uploaded_files: Dict[str, str] = {}  # 缓存：文件路径 -> file_id

        print(f"[QwenClient] 初始化完成")
        print(f"  - Model: {self.model}")
        print(f"  - API Key: {self.api_key[:10]}...{self.api_key[-6:]}")

    def upload_file(
        self,
        file_path: str,
        purpose: str = "file-extract",
        verbose: bool = True
    ) -> str:
        """
        上传文件到通义千问

        Args:
            file_path: 本地文件路径
            purpose: 文件用途，默认 "file-extract"（文档解析）
            verbose: 是否打印详细信息

        Returns:
            file_id: 上传成功后返回的文件 ID
        """
        file_path = str(Path(file_path).resolve())

        # 检查缓存
        if file_path in self.uploaded_files:
            if verbose:
                print(f"[QwenClient] 使用缓存的 file_id: {self.uploaded_files[file_path]}")
            return self.uploaded_files[file_path]

        # 检查文件是否存在
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 准备上传
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }

        with open(file_path, "rb") as f:
            files = {
                "file": (os.path.basename(file_path), f),
                "purpose": (None, purpose)
            }

            if verbose:
                print(f"\n{'=' * 80}")
                print(f"[QwenClient] 上传文件")
                print(f"{'=' * 80}")
                print(f"File: {file_path}")
                print(f"Size: {os.path.getsize(file_path):,} bytes")
                print(f"Purpose: {purpose}")
                print(f"{'=' * 80}\n")

            import time
            start_time = time.time()

            try:
                response = requests.post(
                    self.FILES_ENDPOINT,
                    headers=headers,
                    files=files,
                    timeout=120
                )

                elapsed_time = time.time() - start_time
                response.raise_for_status()

                result = response.json()

                # 检查错误
                if "error" in result:
                    error_msg = f"上传失败: {result['error'].get('message', 'Unknown error')}"
                    raise Exception(error_msg)

                # 提取 file_id
                file_id = result.get("id")
                if not file_id:
                    raise Exception(f"响应中未找到 file_id: {result}")

                # 缓存结果
                self.uploaded_files[file_path] = file_id

                if verbose:
                    print(f"\n{'=' * 80}")
                    print(f"[QwenClient] 上传成功")
                    print(f"{'=' * 80}")
                    print(f"File ID: {file_id}")
                    print(f"耗时: {elapsed_time:.2f} 秒")
                    print(f"{'=' * 80}\n")

                return file_id

            except requests.exceptions.HTTPError as e:
                print(f"\n[错误] 文件上传失败:")
                print(f"  - Status Code: {response.status_code}")
                print(f"  - Response: {response.text}")
                raise Exception(f"HTTP错误 {response.status_code}: {response.text}")
            except requests.exceptions.RequestException as e:
                raise Exception(f"上传请求失败: {e}")
            except Exception as e:
                raise Exception(f"处理上传响应失败: {e}")

    def send_request_with_file(
        self,
        file_path: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.000001,
        top_p: float = 1.0,
        max_tokens: Optional[int] = None,
        verbose: bool = True
    ) -> str:
        """
        使用文件 ID 模式发送请求（推荐）

        Args:
            file_path: 本地文件路径（自动上传并获取 file_id）
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）
            temperature: 温度参数（0-1）
            top_p: top_p 参数（0-1）
            max_tokens: 最大生成 token 数
            verbose: 是否打印详细信息

        Returns:
            AI 响应文本
        """
        # 1. 上传文件获取 file_id
        file_id = self.upload_file(file_path, verbose=verbose)

        # 2. 构建 messages
        messages = []

        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })

        # 用户消息中引用文件
        user_content = [
            {"type": "file", "file_id": file_id},
            {"type": "text", "text": prompt}
        ]

        messages.append({
            "role": "user",
            "content": user_content
        })

        # 3. 构建请求体
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p
        }

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        # 4. 发送请求
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        if verbose:
            print(f"\n{'=' * 80}")
            print(f"[QwenClient] 发送请求（file_id 模式）")
            print(f"{'=' * 80}")
            print(f"Model: {self.model}")
            print(f"File ID: {file_id}")
            print(f"Prompt (前200字): {prompt[:200]}...")
            print(f"Temperature: {temperature}, Top_p: {top_p}")
            print(f"{'=' * 80}\n")

        import time
        start_time = time.time()

        try:
            response = requests.post(
                self.CHAT_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=300
            )

            elapsed_time = time.time() - start_time
            response.raise_for_status()

            result = response.json()

            # 检查错误
            if "error" in result:
                error_msg = f"API错误: {result['error'].get('message', 'Unknown error')}"
                raise Exception(error_msg)

            # 提取响应
            if "choices" in result and len(result["choices"]) > 0:
                answer = result["choices"][0]["message"]["content"]
            else:
                raise Exception(f"响应格式异常: {result}")

            if verbose:
                print(f"\n{'=' * 80}")
                print(f"[QwenClient] 收到响应")
                print(f"{'=' * 80}")
                print(f"耗时: {elapsed_time:.2f} 秒")
                print(f"响应长度: {len(answer):,} 字符")
                print(f"响应内容 (前1000字):")
                print(answer[:1000] + ("..." if len(answer) > 1000 else ""))
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

    def send_request(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0,
        top_p: float = 1.0,
        top_k: int = 1,
        seed: int = 42,
        max_tokens: int = 2048,
        repetition_penalty: float = 1.05,
        verbose: bool = True
    ) -> str:
        """
        发送纯文本请求（不使用文件）

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）
            temperature: 温度参数（0=贪婪解码，完全关闭随机性）
            top_p: top_p 参数（0-1）
            top_k: 每次只选概率最高的k个词（1=最高）
            seed: 随机种子（固定值保证可复现）
            max_tokens: 最大生成 token 数
            repetition_penalty: 重复惩罚（1.05轻微防重复）
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

        # 构建请求体（千问推荐参数）
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "seed": seed,
            "max_tokens": max_tokens,
            "repetition_penalty": repetition_penalty
        }

        # 发送请求
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        if verbose:
            print(f"\n{'=' * 80}")
            print(f"[QwenClient] 发送请求（纯文本模式）")
            print(f"{'=' * 80}")
            print(f"Model: {self.model}")
            print(f"Prompt (前200字): {prompt[:200]}...")
            print(f"Params: temperature={temperature}, top_k={top_k}, seed={seed}, max_tokens={max_tokens}")
            print(f"{'=' * 80}\n")

        import time
        start_time = time.time()

        try:
            response = requests.post(
                self.CHAT_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=300
            )

            elapsed_time = time.time() - start_time
            response.raise_for_status()

            result = response.json()

            # 检查错误
            if "error" in result:
                error_msg = f"API错误: {result['error'].get('message', 'Unknown error')}"
                raise Exception(error_msg)

            # 提取响应
            if "choices" in result and len(result["choices"]) > 0:
                answer = result["choices"][0]["message"]["content"]
            else:
                raise Exception(f"响应格式异常: {result}")

            if verbose:
                print(f"\n{'=' * 80}")
                print(f"[QwenClient] 收到响应")
                print(f"{'=' * 80}")
                print(f"耗时: {elapsed_time:.2f} 秒")
                print(f"响应长度: {len(answer):,} 字符")
                print(f"响应内容 (前1000字):")
                print(answer[:1000] + ("..." if len(answer) > 1000 else ""))
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

    def clear_cache(self):
        """清除已上传文件的缓存"""
        self.uploaded_files.clear()
        print("[QwenClient] 文件缓存已清除")


# 全局单例
_global_qwen_client: Optional[QwenClient] = None


def get_qwen_client(
    api_key: Optional[str] = None,
    model: str = "qwen-long"
) -> QwenClient:
    """获取全局通义千问客户端（单例模式）"""
    global _global_qwen_client
    if _global_qwen_client is None:
        _global_qwen_client = QwenClient(
            api_key=api_key,
            model=model
        )
    return _global_qwen_client


def reset_qwen_client():
    """重置全局客户端"""
    global _global_qwen_client
    _global_qwen_client = None


if __name__ == "__main__":
    print("""
QwenClient 模块已加载

使用示例:

from tender_ontology.utils.document_struct.qwen_client import QwenClient

# 方式1：使用环境变量 DASHSCOPE_API_KEY
client = QwenClient()

# 方式2：显式传入 API Key
client = QwenClient(
    api_key="your_api_key",
    model="qwen-long"
)

# 方式3：文件上传模式（推荐，适合大文档）
response = client.send_request_with_file(
    file_path="path/to/document.pdf",
    prompt="请分析这份文档的结构...",
    system_prompt="你是一个专业的文档分析专家"
)

# 方式4：纯文本模式
response = client.send_request(
    prompt="请帮我分析...",
    system_prompt="你是一个专业的文档分析专家"
)

print(response)
    """)