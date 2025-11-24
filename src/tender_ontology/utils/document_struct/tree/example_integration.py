"""
完整示例：集成 hierarchy_relation 和 tree_construct

展示如何将大模型关系预测与树构建算法结合使用
"""

import json
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from tender_ontology.utils.document_struct.hierarchy_relation import (
    load_tagged_document,
    extract_heading_candidates,
    build_document_hierarchy_from_relations
)
from tender_ontology.utils.document_struct.tree import TreeConstructor


def build_hierarchy_with_tree_algorithm(
    json_path: str,
    verbose: bool = True,
    save_results: bool = True
):
    """
    使用树构建算法构建文档层级

    流程：
    1. 加载已标注的文档数据
    2. 提取标题候选项
    3. 调用大模型预测 parent_id 和 left_sibling_id
    4. 使用树构建算法构建层级树
    5. 打印和保存结果

    Args:
        json_path: 已标注的 JSON 文件路径
        verbose: 是否打印详细信息
        save_results: 是否保存结果
    """
    print("="*80)
    print("文档层级构建 - 基于 Detect-Order-Construct 论文")
    print("="*80)

    # 第一步：加载文档数据
    if verbose:
        print(f"\n[步骤 1/5] 加载文档数据...")
        print(f"  文件路径: {json_path}")

    lines_data = load_tagged_document(json_path)

    if verbose:
        print(f"  总行数: {len(lines_data)}")

    # 第二步：提取标题候选项
    if verbose:
        print(f"\n[步骤 2/5] 提取标题候选项...")

    candidates = extract_heading_candidates(lines_data, include_all_lines=False)
    candidates_map = {str(c["id"]): c for c in candidates}

    if verbose:
        print(f"  候选项数: {len(candidates)}")

    # 第三步：调用大模型预测关系
    if verbose:
        print(f"\n[步骤 3/5] 调用大模型预测关系...")
        print(f"  (这一步会调用千帆 API，可能需要几秒钟)")

    from tender_ontology.utils.document_struct.baidu_text_client import BaiduTextClient
    client = BaiduTextClient()

    hierarchy_result = build_document_hierarchy_from_relations(
        client=client,
        lines_data=lines_data,
        prompt_template=None,  # 使用默认提示词
        include_all_lines=False,
        temperature=0.000001,
        verbose=verbose
    )

    predictions = hierarchy_result["predictions"]

    if verbose:
        print(f"\n  收到 {len(predictions)} 个标题预测")

    # 第四步：使用树构建算法构建层级树
    if verbose:
        print(f"\n[步骤 4/5] 使用树构建算法构建层级树...")

    constructor = TreeConstructor(verbose=verbose)
    tree_result = constructor.build_tree_from_predictions(
        predictions,
        candidates_map=candidates_map
    )

    # 第五步：打印和保存结果
    if verbose:
        print(f"\n[步骤 5/5] 打印树结构...")

    constructor.print_tree(max_depth=4)

    print("\n" + "="*80)
    print("结果摘要")
    print("="*80)
    print(f"总标题数: {tree_result['summary']['total_headings']}")
    print(f"根节点数: {tree_result['summary']['root_nodes']}")
    print(f"层级分布: {tree_result['summary']['level_distribution']}")
    print(f"置信度分布: {tree_result['summary']['confidence_distribution']}")

    # 保存结果
    if save_results:
        output_path = Path(json_path).parent / f"{Path(json_path).stem}_tree_result.json"

        result_to_save = {
            "source_file": json_path,
            "method": "tree_insertion_algorithm",
            "predictions": predictions,
            "tree": tree_result
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result_to_save, 'w', encoding='utf-8', indent=2)

        print(f"\n结果已保存到: {output_path}")

    return {
        "predictions": predictions,
        "tree": tree_result,
        "constructor": constructor
    }


def compare_with_original_method(json_path: str):
    """
    对比原始方法（直接构建树）和树插入算法的结果

    Args:
        json_path: 已标注的 JSON 文件路径
    """
    print("="*80)
    print("对比测试：原始方法 vs 树插入算法")
    print("="*80)

    # 方法 1：原始方法（hierarchy_relation.py 的 construct_hierarchy_tree）
    print("\n[方法 1] 原始方法 (construct_hierarchy_tree)")
    print("-"*80)

    from tender_ontology.utils.document_struct.hierarchy_relation import (
        process_document_hierarchy_relations
    )

    result_original = process_document_hierarchy_relations(
        json_path=json_path,
        include_all_lines=False,
        verbose=True,
        save_results=False
    )

    tree_original = result_original["result"]["hierarchy"]

    print(f"\n原始方法结果:")
    print(f"  总标题数: {tree_original['summary']['total_headings']}")
    print(f"  根节点数: {tree_original['summary']['root_nodes']}")
    print(f"  层级分布: {tree_original['summary']['level_distribution']}")

    # 方法 2：树插入算法
    print("\n" + "="*80)
    print("[方法 2] 树插入算法 (TreeConstructor)")
    print("-"*80)

    result_tree = build_hierarchy_with_tree_algorithm(
        json_path=json_path,
        verbose=True,
        save_results=False
    )

    # 对比
    print("\n" + "="*80)
    print("对比结果")
    print("="*80)

    print(f"\n总标题数:")
    print(f"  原始方法: {tree_original['summary']['total_headings']}")
    print(f"  树算法:   {result_tree['tree']['summary']['total_headings']}")

    print(f"\n根节点数:")
    print(f"  原始方法: {tree_original['summary']['root_nodes']}")
    print(f"  树算法:   {result_tree['tree']['summary']['root_nodes']}")

    print(f"\n层级分布:")
    print(f"  原始方法: {tree_original['summary']['level_distribution']}")
    print(f"  树算法:   {result_tree['tree']['summary']['level_distribution']}")


if __name__ == "__main__":
    # 使用说明
    print("""
使用示例
========

1. 基础用法：
   python example_integration.py

2. 自定义文件路径：
   修改下面的 json_path 变量

3. 对比测试：
   取消注释 compare_with_original_method() 调用
    """)

    # 示例文件路径（需要根据实际情况修改）
    json_path = "static/artifact/docling/深圳市大数据服务中心_20251123_172655_labeled.json"

    # 检查文件是否存在
    if not Path(json_path).exists():
        print(f"\n[错误] 文件不存在: {json_path}")
        print(f"\n请修改 json_path 变量为实际的文件路径")
        print(f"示例: json_path = 'path/to/your/labeled.json'")
        sys.exit(1)

    # 运行完整流程
    result = build_hierarchy_with_tree_algorithm(
        json_path=json_path,
        verbose=True,
        save_results=True
    )

    # 如果需要对比测试，取消下面的注释
    # compare_with_original_method(json_path)

    print("\n" + "="*80)
    print("完成！")
    print("="*80)