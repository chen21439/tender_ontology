"""
文档层级目录构建工具（关系预测方法）
基于 Detect-Order-Construct 论文思路，先预测标题间关系，再构建层级树
"""
import json
import os
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime
from collections import defaultdict

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

    # 如果是新格式（包含 document_name, items），提取 items
    if isinstance(data, dict) and "items" in data:
        return data["items"]

    # 否则假设是旧格式（直接是数组）
    return data


def extract_heading_candidates(
    lines_data: List[Dict[str, Any]],
    include_all_lines: bool = False
) -> List[Dict[str, Any]]:
    """
    提取标题候选项及其特征

    Args:
        lines_data: 行数据列表
        include_all_lines: 是否包含所有行（如果为 False，只包含标签为 section_header 的行）

    Returns:
        标题候选列表，包含特征信息
    """
    candidates = []

    for line in lines_data:
        text = line.get("text", "").strip()

        # 兼容新旧格式
        # 新格式：label, id, page_no
        # 旧格式：class, line_id, page
        label = line.get("label", line.get("class", ""))
        item_id = line.get("id", line.get("line_id", ""))
        page = line.get("page_no", line.get("page", ""))

        if not text:
            continue

        # 如果只包含章节，则过滤
        # 新格式用 section_header，旧格式用 Section
        if not include_all_lines:
            if label not in ["section_header", "Section"]:
                continue

        # 提取特征（这里使用占位值，实际应该从文档中提取）
        # TODO: 实现真实的特征提取逻辑
        features = extract_line_features(line)

        candidate = {
            "id": item_id,
            "text": text,
            "page": page,
            "features": features
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

    # 简单的字号推断（基于 class 标签）
    class_label = line.get("class", "")
    if class_label == "Section":
        font_size_level = 1  # 中等字号（假设章节标题是中等）
    else:
        font_size_level = 0  # 正文字号

    # 简单的加粗推断（假设章节标题通常加粗）
    is_bold = (class_label == "Section")

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

        # 构建层级树
        hierarchy_tree = construct_hierarchy_tree(predictions, verbose)

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
            print(f"[HierarchyRelation] 原始响应前500字符: {response[:500]}")
        raise ValueError(f"JSON解析失败: {e}")


def construct_hierarchy_tree(
    predictions: List[Dict[str, Any]],
    verbose: bool = True
) -> Dict[str, Any]:
    """
    基于预测的关系构建层级树

    Args:
        predictions: 预测结果列表，每个元素包含 id, parent_id, left_sibling_id
        verbose: 是否打印详细信息

    Returns:
        层级树结构
    """
    if verbose:
        print(f"[HierarchyRelation] 开始构建层级树...")

    # 建立 id -> node 的映射
    nodes_map = {}
    for pred in predictions:
        node_id = pred["id"]
        nodes_map[node_id] = {
            "id": node_id,
            "heading_type": pred.get("heading_type", "section"),
            "parent_id": pred.get("parent_id"),
            "left_sibling_id": pred.get("left_sibling_id"),
            "confidence": pred.get("confidence", "medium"),
            "reasoning": pred.get("reasoning", ""),
            "children": [],
            "level": None  # 待计算
        }

    # 构建父子关系
    root_nodes = []
    for node_id, node in nodes_map.items():
        parent_id = node["parent_id"]

        # 如果 parent_id 指向自己，说明是顶层节点
        if parent_id == node_id:
            root_nodes.append(node)
        else:
            # 否则添加到父节点的 children
            if parent_id in nodes_map:
                nodes_map[parent_id]["children"].append(node)
            else:
                if verbose:
                    print(f"[HierarchyRelation] [WARNING] 节点 {node_id} 的 parent_id={parent_id} 不存在，视为根节点")
                root_nodes.append(node)

    # 计算每个节点的层级
    def calculate_level(node: Dict[str, Any], current_level: int = 1):
        node["level"] = current_level
        for child in node["children"]:
            calculate_level(child, current_level + 1)

    for root in root_nodes:
        calculate_level(root, level=1)

    # 统计层级分布
    level_distribution = defaultdict(int)
    for node in nodes_map.values():
        level = node.get("level", 0)
        level_distribution[f"level_{level}"] = level_distribution.get(f"level_{level}", 0) + 1

    if verbose:
        print(f"[HierarchyRelation] 构建完成，共 {len(root_nodes)} 个根节点")
        print(f"[HierarchyRelation] 层级分布: {dict(level_distribution)}")

    # 构建树结构（序列化为列表）
    def serialize_tree(node: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": node["id"],
            "heading_type": node["heading_type"],
            "level": node["level"],
            "confidence": node["confidence"],
            "children": [serialize_tree(child) for child in node["children"]]
        }

    tree_structure = [serialize_tree(root) for root in root_nodes]

    return {
        "tree": tree_structure,
        "summary": {
            "total_headings": len(nodes_map),
            "root_nodes": len(root_nodes),
            "level_distribution": dict(level_distribution)
        }
    }


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
        client = BaiduTextClient()
        if verbose:
            print("[HierarchyRelation] 使用默认文本客户端")

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
    # 测试示例
    # 输入文件名前缀，自动查找最新的 labeled.json
    doc_name = "深圳市大数据服务中心"
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

    # 如果文件存在，尝试提取候选项（用于测试）
    if os.path.exists(json_path):
        print(f"\n[测试] 加载文件: {json_path}")
        lines_data = load_tagged_document(json_path)
        print(f"[测试] 总行数: {len(lines_data)}")

        # 提取候选项
        candidates = extract_heading_candidates(lines_data, include_all_lines=False)
        print(f"[测试] 候选项数: {len(candidates)}")

        # 显示前3个候选项
        print(f"[测试] 前3个候选项:")
        for i, candidate in enumerate(candidates[:3]):
            print(f"  [{i+1}] ID={candidate['id']}, Text={candidate['text'][:30]}, Features={candidate['features']}")
    else:
        print(f"\n[测试] 文件不存在: {json_path}")