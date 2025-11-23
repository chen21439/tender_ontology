"""
文档层级目录构建示例（关系预测方法）
使用 Detect-Order-Construct 论文思路
"""
import os
from pathlib import Path

# 自动切换到项目根目录
PROJECT_ROOT = Path(__file__).parent.parent
os.chdir(PROJECT_ROOT)

from tender_ontology.utils.document_struct.hierarchy_relation import (
    process_document_hierarchy_relations,
    extract_heading_candidates,
    load_tagged_document
)


def example_basic_usage():
    """示例1：基本使用"""
    print("\n" + "="*80)
    print("示例1：基本使用（关系预测方法）")
    print("="*80)

    json_path = "static/artifact/docling/城市大数据中心物业管理服务_tagged_20251123_175828.json"

    # 检查文件是否存在
    if not os.path.exists(json_path):
        print(f"[错误] 文件不存在: {json_path}")
        return

    # 调用处理函数
    result = process_document_hierarchy_relations(
        json_path=json_path,
        include_all_lines=False,  # 只分析 class=Section 的行
        temperature=0.000001,
        verbose=True,
        save_results=True
    )

    print(f"\n处理完成！")
    print(f"总标题数: {result['result']['hierarchy']['summary']['total_headings']}")
    print(f"根节点数: {result['result']['hierarchy']['summary']['root_nodes']}")
    print(f"层级分布: {result['result']['hierarchy']['summary']['level_distribution']}")


def example_extract_candidates():
    """示例2：提取标题候选项"""
    print("\n" + "="*80)
    print("示例2：提取标题候选项")
    print("="*80)

    json_path = "static/artifact/docling/城市大数据中心物业管理服务_tagged_20251123_175828.json"

    if not os.path.exists(json_path):
        print(f"[错误] 文件不存在: {json_path}")
        return

    # 加载文档
    lines_data = load_tagged_document(json_path)
    print(f"总行数: {len(lines_data)}")

    # 提取候选项
    candidates = extract_heading_candidates(lines_data, include_all_lines=False)
    print(f"候选项数量: {len(candidates)}")

    # 显示前5个
    print(f"\n前5个候选项:")
    for i, candidate in enumerate(candidates[:5]):
        print(f"\n候选项 {i+1}:")
        print(f"  ID: {candidate['id']}")
        print(f"  Text: {candidate['text']}")
        print(f"  Page: {candidate['page']}")
        print(f"  Features: {candidate['features']}")


def example_custom_client():
    """示例3：自定义客户端"""
    print("\n" + "="*80)
    print("示例3：自定义客户端")
    print("="*80)

    from tender_ontology.utils.document_struct.baidu_text_client import BaiduTextClient

    # 创建自定义客户端
    client = BaiduTextClient(
        model="ernie-4.0-turbo-8k"
    )

    json_path = "static/artifact/docling/城市大数据中心物业管理服务_tagged_20251123_175828.json"

    if not os.path.exists(json_path):
        print(f"[错误] 文件不存在: {json_path}")
        return

    # 使用自定义客户端
    result = process_document_hierarchy_relations(
        json_path=json_path,
        client=client,
        include_all_lines=False,
        temperature=0.1,
        verbose=True,
        save_results=True
    )

    print(f"\n处理完成！")


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║              文档层级目录构建示例（关系预测方法）                                    ║
║                                                                            ║
║  方法说明：                                                                  ║
║  1. LLM 预测标题间的 parent_id 和 left_sibling_id                           ║
║  2. 算法根据关系构建层级树                                                     ║
║  3. 自动计算每个节点的 level                                                  ║
║                                                                            ║
║  对比直接方法：                                                               ║
║  - 直接方法：LLM 直接预测 H1/H2/H3                                            ║
║  - 关系方法：LLM 预测关系 → 算法构建树（更准确）                                 ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
    """)

    # 运行示例1
    example_basic_usage()

    # 如果需要运行其他示例，取消注释：
    # example_extract_candidates()
    # example_custom_client()