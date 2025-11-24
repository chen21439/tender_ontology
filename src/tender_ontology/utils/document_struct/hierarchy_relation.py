"""
文档层级目录构建工具（关系预测方法）
基于 Detect-Order-Construct 论文思路，先预测标题间关系，再构建层级树
"""
import json
import os
from typing import List, Dict, Any, Optional, Tuple
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

    # 新格式：包含 document_name, items
    if isinstance(data, dict) and "items" in data:
        return data["items"]

    raise ValueError(f"不支持的 JSON 格式，期望包含 'items' 字段")


def extract_heading_candidates(
    lines_data: List[Dict[str, Any]],
    include_all_lines: bool = False
) -> List[Dict[str, Any]]:
    """
    提取标题候选项（纯文本版本）

    Args:
        lines_data: 行数据列表
        include_all_lines: 是否包含所有行（如果为 False，只包含标签为 section_header 的行）

    Returns:
        标题候选列表（只包含 id, text, page，不包含版面特征）
    """
    candidates = []

    for line in lines_data:
        text = line.get("text", "").strip()
        label = line.get("label", "")
        item_id = line.get("id", "")
        page = line.get("page_no", "")

        if not text:
            continue

        # 如果只包含章节，则过滤
        if not include_all_lines and label != "section_header":
            continue

        # 纯文本版本：只保留 id, text, page（不包含版面特征）
        candidate = {
            "id": item_id,
            "text": text,
            "page": page
        }

        candidates.append(candidate)

    return candidates


def extract_line_features(line: Dict[str, Any]) -> Dict[str, Any]:
    """
    提取单行的版面特征

    Args:
        line: 行数据

    Returns:
        特征字典
    """
    # TODO: 实现真实的特征提取
    # 这里需要根据实际的 line 数据结构来提取
    # 目前使用占位逻辑

    text = line.get("text", "")

    # 简单的编号模式识别
    numbering_pattern = None
    has_numbering = False

    if text:
        # 检测常见编号模式
        import re
        patterns = [
            (r'^第[一二三四五六七八九十百]+章', "第X章"),
            (r'^第[一二三四五六七八九十百]+节', "第X节"),
            (r'^\d+\.', "1."),
            (r'^\d+\.\d+', "1.1"),
            (r'^\d+\.\d+\.\d+', "1.1.1"),
            (r'^[一二三四五六七八九十]、', "一、"),
            (r'^（[一二三四五六七八九十]）', "（一）"),
            (r'^\([一二三四五六七八九十]\)', "(一)"),
        ]

        for pattern, pattern_name in patterns:
            if re.match(pattern, text):
                numbering_pattern = pattern_name
                has_numbering = True
                break

    # 简单的字号推断（基于 label 标签）
    label = line.get("label", "")
    if label == "section_header":
        font_size_level = 1  # 中等字号（假设章节标题是中等）
    else:
        font_size_level = 0  # 正文字号

    # 简单的加粗推断（假设章节标题通常加粗）
    is_bold = (label == "section_header")

    # 简单的居中推断（暂不实现）
    is_centered = False

    # 缩进级别（暂不实现）
    indent_level = 0

    # 前置空白（暂不实现）
    spacing_before = "medium"

    return {
        "font_size_level": font_size_level,
        "is_bold": is_bold,
        "is_centered": is_centered,
        "indent_level": indent_level,
        "spacing_before": spacing_before,
        "has_numbering": has_numbering,
        "numbering_pattern": numbering_pattern
    }


def build_candidates_json(candidates: List[Dict[str, Any]]) -> str:
    """
    构建候选列表的 JSON 字符串（用于提示词）

    Args:
        candidates: 候选列表

    Returns:
        格式化的 JSON 字符串
    """
    return json.dumps(candidates, ensure_ascii=False, indent=2)


def build_document_hierarchy_from_relations(
    client,
    lines_data: List[Dict[str, Any]],
    prompt_template: str,
    include_all_lines: bool = False,
    temperature: float = 0.000001,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    基于关系预测构建文档层级目录结构

    Args:
        client: BaiduTextClient 实例
        lines_data: 文档行数据列表
        prompt_template: 提示词模板
        include_all_lines: 是否包含所有行进行分析
        temperature: 温度参数
        verbose: 是否打印详细信息

    Returns:
        层级目录结构
    """
    if verbose:
        print(f"[HierarchyRelation] 开始构建文档层级目录（关系预测方法）")
        print(f"[HierarchyRelation] 总行数: {len(lines_data)}")

    # 提取标题候选项
    candidates = extract_heading_candidates(lines_data, include_all_lines)

    if verbose:
        print(f"[HierarchyRelation] 提取标题候选数: {len(candidates)}")

    # 构建候选列表 JSON
    candidates_json = build_candidates_json(candidates)

    # Token 统计
    if TOKEN_COUNTER_AVAILABLE and verbose:
        token_counter = BatchManager()

        candidates_tokens = token_counter.count_tokens(candidates_json)
        prompt_tokens = token_counter.count_tokens(prompt_template)

        print(f"\n{'='*80}")
        print(f"📊 Token 统计信息")
        print(f"{'='*80}")
        print(f"📄 候选项统计:")
        print(f"   - 候选项数量: {len(candidates)}")
        print(f"   - 候选项 JSON 长度: {len(candidates_json):,} 字符")
        print(f"   - 候选项 JSON tokens: ~{candidates_tokens:,} tokens")
        print(f"\n📤 本次发送内容:")
        print(f"   - 提示词模板 tokens: ~{prompt_tokens:,} tokens")
        print(f"{'='*80}\n")
    elif verbose:
        print(f"[HierarchyRelation] 候选项数量: {len(candidates)}")
        print(f"[HierarchyRelation] 候选项 JSON 长度: {len(candidates_json)} 字符")

    # 构建完整提示词
    prompt = prompt_template.replace(
        "<这里插入标题候选列表JSON>",
        candidates_json
    )

    # 最终 token 统计
    if TOKEN_COUNTER_AVAILABLE and verbose:
        total_tokens = token_counter.count_tokens(prompt)
        system_prompt_tokens = token_counter.count_tokens("你是一个专业的文档结构分析专家。")
        estimated_total = total_tokens + system_prompt_tokens
        print(f"[HierarchyRelation] 总输入 tokens: ~{estimated_total} (prompt: {total_tokens} + system: {system_prompt_tokens})")

    if verbose:
        print(f"[HierarchyRelation] 发送请求到 AI...")

    # 调用文本 API
    try:
        response = _call_text_api(client, prompt, temperature, verbose)

        if verbose:
            print(f"[HierarchyRelation] 收到响应")

        # 解析 JSON 响应
        predictions = _parse_relation_response(response, verbose)

        if verbose:
            print(f"[HierarchyRelation] 解析得到 {len(predictions)} 个标题预测")

        # 构建候选项映射（包含原始文本和页码信息）
        candidates_map = {str(c["id"]): c for c in candidates}

        # 使用 TreeConstructor 构建层级树
        from tender_ontology.utils.document_struct.tree import TreeConstructor

        constructor = TreeConstructor(verbose=verbose)
        hierarchy_tree = constructor.build_tree_from_predictions(
            predictions,
            candidates_map=candidates_map
        )

        # 构建最终结果
        result = {
            "method": "relation_prediction",
            "candidates_count": len(candidates),
            "headings_count": len(predictions),
            "predictions": predictions,
            "hierarchy": hierarchy_tree
        }

        return result

    except Exception as e:
        if verbose:
            print(f"[HierarchyRelation] [ERROR] 失败: {e}")
        raise


def _call_text_api(client, prompt: str, temperature: float, verbose: bool, max_tokens: Optional[int] = None) -> str:
    """
    调用纯文本 API

    Args:
        client: BaiduTextClient 实例
        prompt: 提示词
        temperature: 温度参数
        verbose: 是否打印详细信息
        max_tokens: 最大输出 tokens 数（None 表示不限制，由模型自动决定）

    Returns:
        AI 响应文本
    """
    from tender_ontology.utils.document_struct.baidu_text_client import BaiduTextClient

    # 如果传入的不是文本客户端，创建新的
    if not isinstance(client, BaiduTextClient):
        if verbose:
            print("[HierarchyRelation] 创建文本客户端...")
        client = BaiduTextClient()

    # 调用文本 API
    response = client.send_request(
        prompt=prompt,
        system_prompt="你是一个专业的文档结构分析专家。",
        temperature=temperature,
        max_tokens=max_tokens,
        verbose=verbose
    )

    return response


def _parse_relation_response(response: str, verbose: bool) -> List[Dict[str, Any]]:
    """
    解析关系预测响应

    Args:
        response: AI 响应文本
        verbose: 是否打印详细信息

    Returns:
        预测结果列表
    """
    # 解析 JSON 响应
    if "```json" in response:
        json_str = response.split("```json")[1].split("```")[0].strip()
    elif "[" in response and "]" in response:
        # 尝试提取 JSON 数组
        start = response.find("[")
        end = response.rfind("]") + 1
        json_str = response[start:end]
    else:
        json_str = response.strip()

    try:
        predictions = json.loads(json_str)
        if not isinstance(predictions, list):
            raise ValueError("响应不是 JSON 数组")
        return predictions
    except json.JSONDecodeError as e:
        if verbose:
            print(f"[HierarchyRelation] [JSONDecodeError] {e}")
            print(f"[HierarchyRelation] JSON字符串长度: {len(json_str)}")
            print(f"[HierarchyRelation] 错误位置附近的内容:")
            error_pos = e.pos if hasattr(e, 'pos') else 835
            start = max(0, error_pos - 100)
            end = min(len(json_str), error_pos + 100)
            print(f"...{json_str[start:end]}...")

            # 保存完整响应到文件以便调试
            debug_file = "debug_response.json"
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(response)
            print(f"[HierarchyRelation] 完整响应已保存到: {debug_file}")

        raise ValueError(f"JSON解析失败: {e}")


def process_document_hierarchy_relations(
    json_path: str,
    client = None,
    prompt_template: str = None,
    include_all_lines: bool = False,
    temperature: float = 0.000001,
    verbose: bool = True,
    save_results: bool = True,
    output_dir: str = None
) -> Dict[str, Any]:
    """
    处理文档层级目录构建（关系预测方法，完整 Pipeline）

    Args:
        json_path: 已标注的 JSON 文件路径
        client: AI 客户端实例，如果为 None 则自动创建
        prompt_template: 提示词模板，如果为 None 则使用默认
        include_all_lines: 是否包含所有行进行分析
        temperature: 温度参数
        verbose: 是否打印详细信息
        save_results: 是否保存结果
        output_dir: 输出目录，如果为 None 则保存到 JSON 文件同目录

    Returns:
        层级目录结构
    """
    # 初始化客户端
    if client is None:
        from tender_ontology.utils.document_struct.baidu_text_client import BaiduTextClient
        from tender_ontology.config.model_config import DefaultModels

        # 使用 DOCUMENT_HIERARCHY 专用模型（ERNIE-4.0-Turbo-128K）
        client = BaiduTextClient(model=DefaultModels.DOCUMENT_HIERARCHY)
        if verbose:
            print(f"[HierarchyRelation] 使用文档层级分析专用模型: {DefaultModels.DOCUMENT_HIERARCHY.display_name}")

    # 使用默认提示词
    if prompt_template is None:
        from tender_ontology.prompts.document_struct.document_relation_prediction_prompt import get_relation_prediction_prompt
        prompt_template = get_relation_prediction_prompt()

    if verbose:
        print(f"[HierarchyRelation] ========== 文档层级目录构建（关系预测） ==========")
        print(f"[HierarchyRelation] JSON路径: {json_path}")

    # 检查文件是否存在
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"JSON文件不存在: {json_path}")

    # 加载文档数据
    lines_data = load_tagged_document(json_path)

    if verbose:
        print(f"[HierarchyRelation] 加载 {len(lines_data)} 行数据")

    # 构建层级目录
    try:
        hierarchy_result = build_document_hierarchy_from_relations(
            client=client,
            lines_data=lines_data,
            prompt_template=prompt_template,
            include_all_lines=include_all_lines,
            temperature=temperature,
            verbose=verbose
        )

        # 添加元数据
        result = {
            "source_file": json_path,
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "created_at": datetime.now().isoformat(),
            "method": "relation_prediction",
            "include_all_lines": include_all_lines,
            "result": hierarchy_result
        }

        # 保存结果
        if save_results:
            if output_dir is None:
                output_dir = os.path.dirname(json_path)

            # 从输入文件名提取文档名
            doc_name = Path(json_path).stem
            timestamp = result["timestamp"]
            output_file = os.path.join(output_dir, f"{doc_name}_hierarchy_relation_{timestamp}.json")

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            if verbose:
                print(f"[HierarchyRelation] 结果已保存到: {output_file}")

        if verbose:
            print(f"[HierarchyRelation] ========== 处理完成 ==========")
            summary = hierarchy_result["hierarchy"]["summary"]
            print(f"[HierarchyRelation] 总标题数: {summary.get('total_headings', 0)}")
            print(f"[HierarchyRelation] 根节点数: {summary.get('root_nodes', 0)}")
            print(f"[HierarchyRelation] 层级分布: {summary.get('level_distribution', {})}")

        return result

    except Exception as e:
        if verbose:
            print(f"[HierarchyRelation] [ERROR] 处理失败: {e}")
        raise


if __name__ == "__main__":
    # 切换到项目根目录
    project_root = Path(r"E:\programFile\AIProgram\tender_ontology")
    os.chdir(project_root)

    # 测试示例
    # 输入文件名前缀，自动查找最新的 labeled.json
    doc_name = "城市大数据中心物业管理服务"
    artifact_dir = Path("static") / "artifact" / "docling"

    # 查找所有匹配的 labeled.json 文件
    pattern = f"{doc_name}_*_labeled.json"
    matching_files = list(artifact_dir.glob(pattern))

    if not matching_files:
        print(f"[错误] 未找到匹配的文件: {artifact_dir / pattern}")
        print(f"[调试] 当前工作目录: {os.getcwd()}")
        print(f"[调试] artifact_dir 是否存在: {artifact_dir.exists()}")
        if artifact_dir.exists():
            all_files = list(artifact_dir.glob("*.json"))
            print(f"[调试] 目录中所有 JSON 文件: {[f.name for f in all_files[:5]]}")
        exit(1)

    # 按文件名排序（时间戳在文件名中），取最新的
    json_path = str(sorted(matching_files)[-1])
    print(f"[HierarchyRelation] 找到文件: {json_path}")

    print("""
[HierarchyRelation] 文档层级目录构建工具（关系预测方法）

核心思路：
1. 基于 Detect-Order-Construct 论文
2. LLM 预测标题间的 parent_id 和 left_sibling_id
3. 算法构建层级树并计算 level

使用方法：
    from tender_ontology.utils.document_struct.hierarchy_relation import process_document_hierarchy_relations

    result = process_document_hierarchy_relations(
        json_path="path/to/tagged.json",
        include_all_lines=False,  # 只分析 class=Section 的行
        verbose=True
    )
    """)

    # 调用完整的处理流程
    if os.path.exists(json_path):
        print(f"\n" + "="*80)
        print(f"开始完整处理流程")
        print(f"="*80)

        result = process_document_hierarchy_relations(
            json_path=json_path,
            include_all_lines=False,  # 只分析 section_header
            verbose=True,
            save_results=True
        )

        print(f"\n" + "="*80)
        print(f"处理完成！")
        print(f"="*80)
    else:
        print(f"\n[错误] 文件不存在: {json_path}")