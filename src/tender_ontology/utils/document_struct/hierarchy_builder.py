"""
文档层级目录构建工具
基于已标注的文档数据，构建文档的层级目录结构
"""
import json
import os
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

# 导入 token 计算工具
try:
    import sys
    import importlib.util

    # 直接加载 batch_manager 模块,避免导入整个 request 包
    batch_manager_path = Path(__file__).parent.parent / "request" / "batch_manager.py"
    spec = importlib.util.spec_from_file_location("batch_manager", batch_manager_path)
    batch_manager_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(batch_manager_module)
    BatchManager = batch_manager_module.BatchManager
    TOKEN_COUNTER_AVAILABLE = True
except Exception as e:
    TOKEN_COUNTER_AVAILABLE = False
    _import_error = str(e)


def load_tagged_document(json_path: str) -> List[Dict[str, Any]]:
    """
    加载已标注的文档数据

    Args:
        json_path: JSON 文件路径

    Returns:
        文档行数据列表
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def extract_text_content(lines_data: List[Dict[str, Any]], include_sections_only: bool = False) -> str:
    """
    从标注数据中提取纯文本内容

    Args:
        lines_data: 行数据列表
        include_sections_only: 是否只包含章节标题（class=Section）

    Returns:
        提取的纯文本内容
    """
    text_lines = []

    for line in lines_data:
        text = line.get("text", "").strip()
        class_label = line.get("class", "")
        line_id = line.get("line_id", "")
        page = line.get("page", "")

        if not text:
            continue

        if include_sections_only:
            # 只包含章节标题
            if class_label == "Section":
                text_lines.append(f"[Line {line_id}, Page {page}] {text}")
        else:
            # 包含所有内容
            text_lines.append(f"[Line {line_id}, Page {page}, Class: {class_label}] {text}")

    return "\n".join(text_lines)


def build_document_hierarchy(
    client,
    lines_data: List[Dict[str, Any]],
    prompt_template: str,
    include_sections_only: bool = True,
    temperature: float = 0.000001,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    构建文档层级目录结构

    Args:
        client: BaiduImageClientBearer 实例
        lines_data: 文档行数据列表
        prompt_template: 提示词模板
        include_sections_only: 是否只分析章节标题
        temperature: 温度参数
        verbose: 是否打印详细信息

    Returns:
        层级目录结构
    """
    if verbose:
        print(f"[HierarchyBuilder] 开始构建文档层级目录")
        print(f"[HierarchyBuilder] 总行数: {len(lines_data)}")

    # 提取纯文本内容
    text_content = extract_text_content(lines_data, include_sections_only)

    # 同时提取完整文档用于统计
    full_text_content = extract_text_content(lines_data, include_sections_only=False)

    # Token 统计
    if TOKEN_COUNTER_AVAILABLE and verbose:
        token_counter = BatchManager()

        # 统计将要发送的内容
        text_tokens = token_counter.count_tokens(text_content)
        prompt_tokens = token_counter.count_tokens(prompt_template)

        # 统计完整文档
        full_text_tokens = token_counter.count_tokens(full_text_content)

        print(f"\n{'='*80}")
        print(f"📊 Token 统计信息")
        print(f"{'='*80}")
        print(f"📄 完整文档统计:")
        print(f"   - 总行数: {len(lines_data)}")
        print(f"   - 完整文本长度: {len(full_text_content):,} 字符")
        print(f"   - 完整文本 tokens: ~{full_text_tokens:,} tokens")
        print(f"\n📤 本次发送内容:")
        print(f"   - 只包含章节: {'是' if include_sections_only else '否'}")
        print(f"   - 发送文本长度: {len(text_content):,} 字符")
        print(f"   - 发送文本 tokens: ~{text_tokens:,} tokens")
        print(f"   - 提示词模板 tokens: ~{prompt_tokens:,} tokens")

        if include_sections_only:
            sections_count = sum(1 for line in lines_data if line.get("class") == "Section")
            print(f"   - 章节标题数量: {sections_count}")
            print(f"   - 压缩比: {full_text_tokens/text_tokens:.1f}x (完整文档 vs 仅章节)")
        print(f"{'='*80}\n")
    elif verbose:
        print(f"[HierarchyBuilder] 提取文本长度: {len(text_content)} 字符")
        print(f"[HierarchyBuilder] 完整文档长度: {len(full_text_content)} 字符")
        print(f"[HierarchyBuilder] 只包含章节: {include_sections_only}")
        print(f"[HierarchyBuilder] [提示] 安装 tiktoken 以获取精确 token 统计: pip install tiktoken")

    # 构建完整提示词
    prompt = prompt_template.replace(
        "<这里插入文档纯文本内容>",
        text_content
    )

    # 最终 token 统计
    if TOKEN_COUNTER_AVAILABLE and verbose:
        total_tokens = token_counter.count_tokens(prompt)
        system_prompt_tokens = token_counter.count_tokens("你是一个专业的文档结构分析专家，擅长识别文档中的章节标题并构建层级目录。")
        estimated_total = total_tokens + system_prompt_tokens
        print(f"[HierarchyBuilder] 总输入 tokens: ~{estimated_total} (prompt: {total_tokens} + system: {system_prompt_tokens})")

    if verbose:
        print(f"[HierarchyBuilder] 发送请求到 AI...")

    # 调用 AI API（纯文本，不需要图片）
    # 注意：这里使用文本 API，不是图像 API
    # 如果使用百度千帆，需要切换到纯文本模型
    try:
        # 由于 BaiduImageClientBearer 是图像客户端，这里需要使用纯文本客户端
        # 暂时使用一个占位实现
        response = _call_text_api(client, prompt, temperature, verbose)

        if verbose:
            print(f"[HierarchyBuilder] 收到响应")

        # 解析 JSON 响应
        result = _parse_hierarchy_response(response, verbose)

        return result

    except Exception as e:
        if verbose:
            print(f"[HierarchyBuilder] [ERROR] 失败: {e}")
        raise


def _call_text_api(client, prompt: str, temperature: float, verbose: bool) -> str:
    """
    调用纯文本 API

    Args:
        client: BaiduTextClient 实例
        prompt: 提示词
        temperature: 温度参数
        verbose: 是否打印详细信息

    Returns:
        AI 响应文本
    """
    # 使用百度千帆文本客户端
    from tender_ontology.utils.document_struct.baidu_text_client import BaiduTextClient

    # 如果传入的是图像客户端，创建新的文本客户端
    if not isinstance(client, BaiduTextClient):
        if verbose:
            print("[HierarchyBuilder] 创建文本客户端...")
        client = BaiduTextClient()

    # 调用文本 API
    response = client.send_request(
        prompt=prompt,
        system_prompt="你是一个专业的文档结构分析专家，擅长识别文档中的章节标题并构建层级目录。",
        temperature=temperature,
        verbose=verbose
    )

    return response


def _parse_hierarchy_response(response: str, verbose: bool) -> Dict[str, Any]:
    """
    解析层级分析响应

    Args:
        response: AI 响应文本
        verbose: 是否打印详细信息

    Returns:
        解析后的层级结构
    """
    # 解析 JSON 响应
    if "```json" in response:
        json_str = response.split("```json")[1].split("```")[0].strip()
    elif "{" in response and "}" in response:
        # 尝试提取 JSON 对象
        start = response.find("{")
        end = response.rfind("}") + 1
        json_str = response[start:end]
    else:
        json_str = response.strip()

    try:
        result = json.loads(json_str)
        return result
    except json.JSONDecodeError as e:
        if verbose:
            print(f"[HierarchyBuilder] [JSONDecodeError] {e}")
        raise ValueError(f"JSON解析失败: {e}")


def process_document_hierarchy(
    json_path: str,
    client = None,
    prompt_template: str = None,
    include_sections_only: bool = True,
    temperature: float = 0.000001,
    verbose: bool = True,
    save_results: bool = True,
    output_dir: str = None
) -> Dict[str, Any]:
    """
    处理文档层级目录构建（完整 Pipeline）

    Args:
        json_path: 已标注的 JSON 文件路径
        client: AI 客户端实例，如果为 None 则自动创建
        prompt_template: 提示词模板，如果为 None 则使用默认
        include_sections_only: 是否只分析章节标题
        temperature: 温度参数
        verbose: 是否打印详细信息
        save_results: 是否保存结果
        output_dir: 输出目录，如果为 None 则保存到 JSON 文件同目录

    Returns:
        层级目录结构
    """
    # 初始化客户端
    if client is None:
        # TODO: 这里应该使用纯文本客户端，而不是图像客户端
        from tender_ontology.utils.document_struct.baidu_client_bearer import BaiduImageClientBearer
        client = BaiduImageClientBearer()
        if verbose:
            print("[HierarchyBuilder] [WARNING] 使用图像客户端，建议改用纯文本客户端")

    # 使用默认提示词
    if prompt_template is None:
        from tender_ontology.prompts.document_struct.document_hierarchy_prompt import DOCUMENT_HIERARCHY_PROMPT
        prompt_template = DOCUMENT_HIERARCHY_PROMPT

    if verbose:
        print(f"[HierarchyBuilder] ========== 文档层级目录构建 ==========")
        print(f"[HierarchyBuilder] JSON路径: {json_path}")

    # 检查文件是否存在
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"JSON文件不存在: {json_path}")

    # 加载文档数据
    lines_data = load_tagged_document(json_path)

    if verbose:
        print(f"[HierarchyBuilder] 加载 {len(lines_data)} 行数据")

    # 构建层级目录
    try:
        hierarchy_result = build_document_hierarchy(
            client=client,
            lines_data=lines_data,
            prompt_template=prompt_template,
            include_sections_only=include_sections_only,
            temperature=temperature,
            verbose=verbose
        )

        # 添加元数据
        result = {
            "source_file": json_path,
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "created_at": datetime.now().isoformat(),
            "include_sections_only": include_sections_only,
            "hierarchy": hierarchy_result
        }

        # 保存结果
        if save_results:
            if output_dir is None:
                output_dir = os.path.dirname(json_path)

            # 从输入文件名提取文档名
            doc_name = Path(json_path).stem
            timestamp = result["timestamp"]
            output_file = os.path.join(output_dir, f"{doc_name}_hierarchy_{timestamp}.json")

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            if verbose:
                print(f"[HierarchyBuilder] 结果已保存到: {output_file}")

        if verbose:
            print(f"[HierarchyBuilder] ========== 处理完成 ==========")
            if "summary" in hierarchy_result:
                summary = hierarchy_result["summary"]
                print(f"[HierarchyBuilder] 总标题数: {summary.get('total_headers', 0)}")
                print(f"[HierarchyBuilder] 层级分布: {summary.get('level_distribution', {})}")

        return result

    except Exception as e:
        if verbose:
            print(f"[HierarchyBuilder] [ERROR] 处理失败: {e}")
        raise


if __name__ == "__main__":
    # 测试示例
    json_path = "static/artifact/docling/城市大数据中心物业管理服务_tagged_20251123_175828.json"

    print("""
[HierarchyBuilder] 文档层级目录构建工具

注意事项：
1. 本工具需要使用纯文本 API，当前使用图像客户端作为占位
2. 需要实现 _call_text_api 函数来调用实际的文本模型
3. 建议使用百度千帆的 ERNIE-Bot-4 或其他纯文本模型

使用方法：
    from tender_ontology.utils.document_struct.hierarchy_builder import process_document_hierarchy

    result = process_document_hierarchy(
        json_path="path/to/tagged.json",
        include_sections_only=True,  # 只分析章节标题
        verbose=True
    )
    """)

    # 如果文件存在，尝试加载并提取文本（用于测试）
    if os.path.exists(json_path):
        print(f"\n[测试] 加载文件: {json_path}")
        lines_data = load_tagged_document(json_path)
        print(f"[测试] 总行数: {len(lines_data)}")

        # 提取章节标题
        text_content = extract_text_content(lines_data, include_sections_only=True)
        print(f"[测试] 章节文本长度: {len(text_content)} 字符")
        print(f"[测试] 前500字符预览:\n{text_content[:500]}")
    else:
        print(f"\n[测试] 文件不存在: {json_path}")