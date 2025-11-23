"""
文档层级分析服务

使用大模型 API 对文档进行语义层级分析，构建目录树
"""

import json
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional

from tender_ontology.config.docling_settings import docling_settings


class HierarchyAnalyzer:
    """文档层级分析服务"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        初始化层级分析器

        Args:
            api_key: LLM API 密钥
            api_base: API 基础 URL
            model: 模型名称
        """
        self.api_key = api_key or docling_settings.llm_api_key
        self.api_base = api_base or docling_settings.llm_api_base
        self.model = model or docling_settings.llm_model

        if not self.api_key:
            raise ValueError("需要提供 LLM API 密钥")

        # 加载提示词
        self.prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        """加载提示词模板"""
        prompt_path = Path(__file__).parent.parent.parent / "prompts" / "hierarchy_construction.txt"

        if prompt_path.exists():
            return prompt_path.read_text(encoding='utf-8')
        else:
            # 如果文件不存在，使用默认提示词
            return self._get_default_prompt()

    def _get_default_prompt(self) -> str:
        """获取默认提示词"""
        return """你是文档结构分析专家。任务：基于版面识别结果，为文档标题构建层级目录。

## 输入数据
JSON数组，每个元素包含：
- id: 元素编号
- label: 类型（section_header/text/list_item/table）
- text: 文本内容
- page_no: 页码

## 层级判断规则（优先级递减）

1. **编号规则**
   - H1: 第X章、第X部分、第X册
   - H2: 第X节、X.、（X）、X、
   - H3: X.X、X)、①②③
   - H4: X.X.X、(X)、a)b)c)

2. **语义重要性**
   - 全局概念 → 高层级
   - 具体细节 → 低层级

3. **位置规律**
   - 章节开头通常是高层级
   - 相似格式的标题通常同级

## 输出要求

仅输出JSON，包含三部分：

```json
{
  "annotated_items": [
    {
      "id": 0,
      "text": "第一章 招标公告",
      "level": 1,
      "reasoning": "主章节，使用'第一章'格式"
    }
  ],
  "toc": {
    "children": [
      {
        "id": 0,
        "level": 1,
        "text": "第一章 招标公告",
        "page": 1,
        "children": [...]
      }
    ]
  },
  "summary": {
    "total": 34,
    "distribution": {"H1": 3, "H2": 12, "H3": 15, "H4": 4},
    "confidence": "high",
    "notes": ["结构清晰，编号规范"]
  }
}
```

## 注意事项
1. 只处理 label="section_header" 的元素
2. 保持层级连续（避免H1→H3）
3. 编号格式优先于语义判断
4. 每个文档至少一个H1

---

请分析以下数据："""

    def analyze(
        self,
        labeled_data: Dict[str, Any],
        temperature: float = 0.1,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        分析文档层级结构

        Args:
            labeled_data: labeled.json 格式的数据
            temperature: 采样温度（0-1，越低越确定）
            max_retries: 最大重试次数

        Returns:
            包含层级标注和目录树的JSON

        Raises:
            RuntimeError: 分析失败
        """
        # 提取 section_header 元素
        items = labeled_data.get("items", [])
        headers = [
            {
                "id": item.get("id"),
                "label": item.get("label"),
                "text": item.get("text"),
                "page_no": item.get("page_no")
            }
            for item in items
            if item.get("label") == "section_header"
        ]

        if not headers:
            return {
                "annotated_items": [],
                "toc": {"children": []},
                "summary": {
                    "total": 0,
                    "distribution": {},
                    "confidence": "low",
                    "notes": ["未找到任何标题元素"]
                }
            }

        print(f"🔍 正在分析 {len(headers)} 个标题元素...")

        # 构建用户消息
        user_message = json.dumps(headers, ensure_ascii=False, indent=2)

        # 调用 LLM API
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    f"{self.api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": self.prompt},
                            {"role": "user", "content": user_message}
                        ],
                        "temperature": temperature,
                        "response_format": {"type": "json_object"}  # 强制返回 JSON
                    },
                    timeout=60
                )

                if response.status_code != 200:
                    raise RuntimeError(
                        f"API 请求失败 (状态码 {response.status_code}): {response.text}"
                    )

                result = response.json()
                content = result["choices"][0]["message"]["content"]

                # 解析返回的 JSON
                hierarchy_result = json.loads(content)

                print(f"✅ 层级分析完成!")
                print(f"   - 总标题数: {hierarchy_result.get('summary', {}).get('total', 0)}")
                print(f"   - 置信度: {hierarchy_result.get('summary', {}).get('confidence', 'unknown')}")

                return hierarchy_result

            except requests.exceptions.Timeout:
                print(f"⚠️  API 请求超时 (尝试 {attempt + 1}/{max_retries})")
                if attempt == max_retries - 1:
                    raise RuntimeError("API 请求超时，请稍后重试")

            except json.JSONDecodeError as e:
                print(f"⚠️  JSON 解析失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise RuntimeError(f"无法解析 LLM 返回的 JSON: {e}")

            except Exception as e:
                print(f"⚠️  分析失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise RuntimeError(f"层级分析失败: {e}")

        raise RuntimeError("层级分析失败：超过最大重试次数")

    def analyze_and_save(
        self,
        labeled_data: Dict[str, Any],
        output_path: Path
    ) -> Dict[str, Any]:
        """
        分析并保存结果

        Args:
            labeled_data: labeled.json 格式的数据
            output_path: 输出文件路径

        Returns:
            层级分析结果
        """
        result = self.analyze(labeled_data)

        # 保存结果
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

        print(f"💾 层级分析结果已保存: {output_path}")

        return result