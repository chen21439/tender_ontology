"""
百度文心一言图像理解客户端（Bearer 鉴权）
使用新一代 API Key 鉴权机制（bce-v3/ALTAK...）

鉴权方式：
- Header: Authorization: Bearer {API_Key}
- 不需要 Secret Key
- 不需要换 access_token
"""
import requests
import base64
import json
from typing import Optional, Dict, Any


class BaiduImageClientBearer:
    """百度图像理解客户端（Bearer 鉴权）"""

    # 默认配置
    DEFAULT_API_KEY = "bce-v3/ALTAK-JkjnSArfweuMYH0Rr0RIN/45271747bda2067bcc0c855c7a6b6f61edd5b51f"
    DEFAULT_MODEL = "qianfan-vl-8b"  # 默认模型（百度千帆自研视觉模型）

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL
    ):
        """
        初始化百度客户端（Bearer 鉴权，V2 接口）

        Args:
            api_key: 百度 API Key（bce-v3/ALTAK...格式），默认使用项目配置
            model: 模型名称，默认 qwen2.5-vl-7b-instruct
        """
        self.api_key = api_key or self.DEFAULT_API_KEY
        self.model = model
        # V2 接口固定 URL
        self.base_url = "https://qianfan.baidubce.com/v2/chat/completions"

        print(f"[BaiduImageClientBearer] 初始化完成（V2 接口）")
        print(f"  - Model: {model}")
        print(f"  - API Key: {self.api_key[:20]}...{self.api_key[-10:]}")

    def encode_image_to_base64(self, image_path: str) -> str:
        """
        将图片编码为 base64（带 data URI 前缀）

        Args:
            image_path: 图片文件路径

        Returns:
            data:image/jpeg;base64,xxx 格式
        """
        with open(image_path, 'rb') as f:
            image_data = f.read()
            b64_str = base64.b64encode(image_data).decode('utf-8')
            return f"data:image/jpeg;base64,{b64_str}"

    def send_request(
        self,
        prompt: str,
        image_path: str,
        temperature: float = 0.000001,
        top_p: float = 1.0,
        verbose: bool = True
    ) -> str:
        """
        发送图像理解请求（Bearer 鉴权）

        Args:
            prompt: 用户提示词
            image_path: 图片文件路径
            temperature: 温度参数（0.000001-1.0）
            top_p: top_p参数（0-1.0）
            verbose: 是否打印详细信息

        Returns:
            AI响应文本
        """
        # 1. 编码图片
        if verbose:
            print(f"[BaiduImageClientBearer] 读取图片: {image_path}")
        image_base64 = self.encode_image_to_base64(image_path)

        # 2. V2 接口固定 URL
        url = self.base_url

        # 3. 组装 messages（V2 格式）
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_base64
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ]

        # 4. 构建请求体（V2 格式：包含 model 字段）
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p
        }

        # 5. 设置 Header（重点：使用 Bearer 鉴权）
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'  # 新一代鉴权方式
        }

        if verbose:
            print(f"\n{'=' * 80}")
            print(f"[BaiduImageClientBearer] 发送请求")
            print(f"{'=' * 80}")
            print(f"URL: {url}")
            print(f"Prompt (前200字): {prompt[:200]}...")
            print(f"Temperature: {temperature}, Top_p: {top_p}")
            print(f"{'=' * 80}\n")

        # 6. 发送 POST 请求
        try:
            response = requests.post(
                url,
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

            # V2 接口：提取 choices[0].message.content
            if "choices" in result and len(result["choices"]) > 0:
                answer = result["choices"][0]["message"]["content"]
            else:
                answer = result.get("result", "")

            if verbose:
                print(f"\n{'=' * 80}")
                print(f"[BaiduImageClientBearer] 收到响应")
                print(f"{'=' * 80}")
                print(answer[:500] + ("..." if len(answer) > 500 else ""))
                print(f"{'=' * 80}\n")

            return answer

        except requests.exceptions.HTTPError as e:
            # 打印详细的错误信息
            print(f"\n[错误] HTTP 请求失败:")
            print(f"  - Status Code: {response.status_code}")
            print(f"  - Response: {response.text}")
            raise Exception(f"HTTP错误 {response.status_code}: {response.text}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"请求失败: {e}")
        except Exception as e:
            raise Exception(f"处理响应失败: {e}")

    def send_request_multi_images(
        self,
        prompt: str,
        image_paths: list,
        temperature: float = 0.000001,
        top_p: float = 1.0,
        verbose: bool = True
    ) -> str:
        """
        发送多图像理解请求

        Args:
            prompt: 用户提示词
            image_paths: 图片文件路径列表
            temperature: 温度参数
            top_p: top_p参数
            verbose: 是否打印详细信息

        Returns:
            AI响应文本
        """
        # 1. 编码所有图片
        if verbose:
            print(f"[BaiduImageClientBearer] 读取 {len(image_paths)} 张图片...")

        image_contents = []
        for i, image_path in enumerate(image_paths, 1):
            if verbose:
                print(f"  [{i}/{len(image_paths)}] {image_path}")
            image_base64 = self.encode_image_to_base64(image_path)
            image_contents.append({
                "type": "image_url",
                "image_url": {
                    "url": image_base64
                }
            })

        # 2. V2 接口固定 URL
        url = self.base_url

        # 3. 组装 messages（V2 格式：先所有图片，后文本）
        content = image_contents + [
            {
                "type": "text",
                "text": prompt
            }
        ]

        messages = [
            {
                "role": "user",
                "content": content
            }
        ]

        # 4. 构建请求体（V2 格式：包含 model 字段）
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p
        }

        # 5. 设置 Header（重点：使用 Bearer 鉴权）
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        if verbose:
            print(f"\n{'=' * 80}")
            print(f"[BaiduImageClientBearer] 发送请求（多图）")
            print(f"{'=' * 80}")
            print(f"URL: {url}")
            print(f"图片数量: {len(image_paths)}")
            print(f"Prompt (前200字): {prompt[:200]}...")
            print(f"Temperature: {temperature}, Top_p: {top_p}")
            print(f"{'=' * 80}\n")

        # 6. 发送 POST 请求
        try:
            response = requests.post(
                url,
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

            # V2 接口：提取 choices[0].message.content
            if "choices" in result and len(result["choices"]) > 0:
                answer = result["choices"][0]["message"]["content"]
            else:
                answer = result.get("result", "")

            if verbose:
                print(f"\n{'=' * 80}")
                print(f"[BaiduImageClientBearer] 收到响应")
                print(f"{'=' * 80}")
                print(answer[:500] + ("..." if len(answer) > 500 else ""))
                print(f"{'=' * 80}\n")

            return answer

        except requests.exceptions.HTTPError as e:
            # 打印详细的错误信息
            print(f"\n[错误] HTTP 请求失败:")
            print(f"  - Status Code: {response.status_code}")
            print(f"  - Response: {response.text}")
            raise Exception(f"HTTP错误 {response.status_code}: {response.text}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"请求失败: {e}")
        except Exception as e:
            raise Exception(f"处理响应失败: {e}")

    def send_request_with_json(
        self,
        prompt_template: str,
        image_path: str,
        json_data: Dict[str, Any],
        temperature: float = 0.000001,
        top_p: float = 1.0,
        verbose: bool = True
    ) -> str:
        """
        发送图像理解请求（包含JSON上下文）

        Args:
            prompt_template: 提示词模板（可以使用 {json_data} 占位符）
            image_path: 图片文件路径
            json_data: JSON数据（会被序列化后插入到prompt中）
            temperature: 温度参数
            top_p: top_p参数
            verbose: 是否打印详细信息

        Returns:
            AI响应文本
        """
        # 将JSON数据格式化为字符串
        json_str = json.dumps(json_data, ensure_ascii=False, indent=2)

        # 替换prompt中的占位符
        full_prompt = prompt_template.replace("{json_data}", json_str)

        return self.send_request(
            prompt=full_prompt,
            image_path=image_path,
            temperature=temperature,
            top_p=top_p,
            verbose=verbose
        )


# 全局单例
_global_baidu_client_bearer: Optional[BaiduImageClientBearer] = None


def get_baidu_client_bearer(
    api_key: Optional[str] = None,
    model: str = BaiduImageClientBearer.DEFAULT_MODEL
) -> BaiduImageClientBearer:
    """获取全局百度客户端（Bearer 鉴权，单例模式）"""
    global _global_baidu_client_bearer
    if _global_baidu_client_bearer is None:
        _global_baidu_client_bearer = BaiduImageClientBearer(
            api_key=api_key,
            model=model
        )
    return _global_baidu_client_bearer


def reset_baidu_client_bearer():
    """重置全局客户端"""
    global _global_baidu_client_bearer
    _global_baidu_client_bearer = None


if __name__ == "__main__":
    print("""
BaiduImageClientBearer 模块已加载（Bearer 鉴权）

特点：
- 使用新一代 API Key 鉴权（bce-v3/ALTAK...）
- 不需要 Secret Key
- 不需要换 access_token
- Header: Authorization: Bearer {API_Key}

使用示例:

from tender_ontology.utils.document_struct.baidu_client_bearer import BaiduImageClientBearer

# 方式1：使用默认配置（已内置 API Key）
client = BaiduImageClientBearer()

# 方式2：自定义 API Key
client = BaiduImageClientBearer(
    api_key="your_api_key",
    api_name="qianfan-vl-8b"
)

# 发送请求
response = client.send_request(
    prompt="请描述这张图片",
    image_path="path/to/image.jpg"
)

print(response)
    """)
