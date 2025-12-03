"""
测试树构建逻辑（不调用 Onto API）
"""
import json
from pathlib import Path

# 读取已有的文件
task_dir = Path(r"E:\programFile\AIProgram\tender_ontology\static\upload\25120110583313478093")
file_stem = "深圳理工大学家具采购"

fulltext_path = task_dir / f"{file_stem}_unstructured_fulltext.json"
headings_path = task_dir / f"{file_stem}_unstructured_headings.json"

fulltext_items = json.loads(fulltext_path.read_text(encoding='utf-8'))
all_headings = json.loads(headings_path.read_text(encoding='utf-8'))

print(f"[测试] fulltext 元素数: {len(fulltext_items)}")
print(f"[测试] headings 数: {len(all_headings)}")

# ========== 树构建逻辑（从 FileService 复制）==========

# 构建 id -> level 映射 和 id -> heading 映射
heading_level_map = {h["id"]: h["level"] for h in all_headings}
heading_text_map = {h["id"]: h["text"] for h in all_headings}
heading_ids = set(heading_level_map.keys())

print(f"[测试] heading_ids 数: {len(heading_ids)}")

# 检查 ID 匹配情况
fulltext_ids = {item["id"] for item in fulltext_items}
matched_ids = heading_ids & fulltext_ids
unmatched_ids = heading_ids - fulltext_ids

print(f"[测试] fulltext IDs 数: {len(fulltext_ids)}")
print(f"[测试] 匹配的 heading IDs: {len(matched_ids)}")
print(f"[测试] 未匹配的 heading IDs: {len(unmatched_ids)}")

if unmatched_ids:
    print(f"\n[警告] 以下 heading IDs 在 fulltext 中不存在:")
    for uid in list(unmatched_ids)[:10]:
        text = heading_text_map.get(uid, "")
        print(f"  - {uid}: {text[:30]}...")

# 递归构建树（包含段落内容）
def build_tree_recursive(items_slice, parent_level=0):
    """
    递归构建树，将段落内容挂载到对应的标题下

    逻辑：
    1. 遍历 items_slice，遇到标题时创建节点
    2. 标题和下一个同级/上级标题之间的内容作为该标题的 children
    3. 非标题的段落直接作为叶子节点挂载
    """
    if not items_slice:
        return []

    children = []
    current_heading_idx = None
    current_heading_level = None
    current_children_start = None

    # 收集当前标题之前的非标题内容（挂载到第一个标题前的内容）
    pre_heading_items = []

    for i, item in enumerate(items_slice):
        item_id = item.get("id", "")
        is_heading = item_id in heading_ids
        item_level = heading_level_map.get(item_id, 999)

        # 遇到新的标题（level <= parent_level + 1），说明需要处理
        if is_heading and item_level <= parent_level + 1:
            # 保存之前的标题及其子内容
            if current_heading_idx is not None:
                prev_item = items_slice[current_heading_idx]
                prev_id = prev_item.get("id", "")
                prev_text = heading_text_map.get(prev_id, prev_item.get("text", ""))

                # 递归构建子树（包含标题之间的所有内容）
                sub_items = items_slice[current_children_start:i]
                sub_children = build_tree_recursive(sub_items, current_heading_level)

                children.append({
                    "pid": prev_id,
                    "title": prev_text,
                    "content": prev_text,
                    "location": [],
                    "children": sub_children if sub_children else None
                })
            else:
                # 第一个标题之前的非标题内容，作为独立节点添加
                for pre_item in pre_heading_items:
                    children.append({
                        "pid": pre_item.get("id", ""),
                        "title": "",
                        "content": pre_item.get("text", ""),
                        "location": []
                    })
                pre_heading_items = []

            # 更新当前标题
            current_heading_idx = i
            current_heading_level = item_level
            current_children_start = i + 1
        elif current_heading_idx is None:
            # 还没遇到第一个标题，收集非标题内容
            pre_heading_items.append(item)

    # 处理最后一个标题
    if current_heading_idx is not None:
        prev_item = items_slice[current_heading_idx]
        prev_id = prev_item.get("id", "")
        prev_text = heading_text_map.get(prev_id, prev_item.get("text", ""))

        sub_items = items_slice[current_children_start:]
        sub_children = build_tree_recursive(sub_items, current_heading_level)

        children.append({
            "pid": prev_id,
            "title": prev_text,
            "content": prev_text,
            "location": [],
            "children": sub_children if sub_children else None
        })
    else:
        # 整个 slice 没有标题，全部作为叶子节点（段落内容）
        for item in items_slice:
            children.append({
                "pid": item.get("id", ""),
                "title": "",
                "content": item.get("text", ""),
                "location": []
            })

    # 移除空的 children
    for child in children:
        if "children" in child and child["children"] is None:
            del child["children"]

    return children


# 找到所有一级标题的位置
level1_positions = []
for i, item in enumerate(fulltext_items):
    item_id = item.get("id", "")
    if item_id in heading_ids and heading_level_map.get(item_id) == 1:
        level1_positions.append(i)

print(f"\n[测试] 一级标题位置: {level1_positions[:10]}...")

# 构建根节点列表
structured_data = []

# 处理第一个一级标题之前的内容
if level1_positions and level1_positions[0] > 0:
    pre_items = fulltext_items[:level1_positions[0]]
    for item in pre_items:
        structured_data.append({
            "pid": item.get("id", ""),
            "title": "",
            "content": item.get("text", "")[:100],
            "location": []
        })

# 处理每个一级标题
for idx, pos in enumerate(level1_positions):
    end_pos = level1_positions[idx + 1] if idx + 1 < len(level1_positions) else len(fulltext_items)
    section_items = fulltext_items[pos:end_pos]

    if not section_items:
        continue

    first_item = section_items[0]
    first_id = first_item.get("id", "")
    first_text = heading_text_map.get(first_id, first_item.get("text", ""))

    # 递归构建子树
    sub_items = section_items[1:]
    sub_children = build_tree_recursive(sub_items, 1)

    root_node = {
        "pid": first_id,
        "title": first_text,
        "content": first_text,
        "location": []
    }
    if sub_children:
        root_node["children"] = sub_children

    structured_data.append(root_node)

print(f"\n[测试] 树构建完成，根节点数: {len(structured_data)}")

# 统计有 children 的节点
def count_nodes_with_children(nodes, depth=0):
    """统计有 children 的节点"""
    count = 0
    for node in nodes:
        if "children" in node and node["children"]:
            count += 1
            count += count_nodes_with_children(node["children"], depth + 1)
    return count

nodes_with_children = count_nodes_with_children(structured_data)
print(f"[测试] 有子节点的节点数: {nodes_with_children}")

# 打印前几个有 children 的根节点
print(f"\n[测试] 有子节点的根节点示例:")
for node in structured_data:
    if "children" in node:
        print(f"  - {node['title'][:40]}... (pid={node['pid']}, children={len(node['children'])})")
        for child in node["children"][:3]:
            child_count = len(child.get("children", [])) if "children" in child else 0
            print(f"      - {child['title'][:30]}... (children={child_count})")

# 保存结果
output_path = task_dir / f"{file_stem}_agent_test.json"
output_path.write_text(json.dumps(structured_data, ensure_ascii=False, indent=2), encoding='utf-8')
print(f"\n[测试] 结果已保存: {output_path}")
