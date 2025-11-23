"""
文档行级标签分类
Pipeline 的一部分，用于对文档的每一行进行语义分类
"""
import json
import os
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


def load_lines_for_page(json_path: str, page_number: int) -> List[Dict[str, Any]]:
    """
    从 JSON 文件中加载指定页面的行数据

    Args:
        json_path: JSON 文件路径
        page_number: 页码

    Returns:
        该页的行数据列表
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        all_lines = json.load(f)

    # 过滤出指定页面的行
    page_lines = [line for line in all_lines if line.get('page') == page_number]

    return page_lines


def tag_document_batch(
    client,
    image_paths: List[str],
    lines_data: List[Dict[str, Any]],
    prompt_template: str,
    temperature: float = 0.000001,
    verbose: bool = False,
    save_response: bool = False
) -> List[Dict[str, str]]:
    """
    对多页文档进行行级标签分类（批量处理）

    Args:
        client: BaiduImageClientBearer 实例
        image_paths: 图片文件路径列表（按页码顺序）
        lines_data: 多页的行数据列表（包含所有页的行）
        prompt_template: 提示词模板（包含占位符）
        temperature: 温度参数
        verbose: 是否打印详细信息

    Returns:
        标签分类结果 [{"line_id": xxx, "label": "xxx"}, ...]
    """
    # 构建提示词（替换占位符）
    lines_json_str = json.dumps(lines_data, ensure_ascii=False, indent=2)

    # 构建多页描述
    page_descriptions = []
    for idx, img_path in enumerate(image_paths):
        page_num = lines_data[0].get('page', 0) + idx if lines_data else idx
        page_descriptions.append(f"第 {page_num} 页图片")

    multi_page_desc = "\n".join([f"{i+1}. {desc}" for i, desc in enumerate(page_descriptions)])
    multi_page_desc += f"\n\n对应的所有行数据 JSON（包含 {len(image_paths)} 页）：\n{lines_json_str}"

    prompt = prompt_template.replace(
        "<这里放入多页图片和行数据>",
        multi_page_desc
    )

    # 调用 API（多图片）
    response = client.send_request_multi_images(
        prompt=prompt,
        image_paths=image_paths,
        temperature=temperature,
        verbose=verbose
    )

    # 保存原始响应用于调试
    if save_response or verbose:
        response_preview = response[:500] + "..." if len(response) > 500 else response
        if verbose:
            print(f"[API响应预览] {response_preview}")

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
        result = json.loads(json_str)
        return result
    except json.JSONDecodeError as e:
        # JSON 解析失败，尝试修复常见问题
        if verbose:
            print(f"[JSONDecodeError] 原始错误: {e}")
            print(f"[JSONDecodeError] 尝试修复...")

        # 尝试修复：移除多余的逗号、修复引号等
        import re

        # 1. 移除尾部多余的逗号（如 "label": "Title", } 改为 "label": "Title" }）
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)

        # 2. 尝试重新解析
        try:
            result = json.loads(json_str)
            if verbose:
                print(f"[JSONDecodeError] 修复成功")
            return result
        except json.JSONDecodeError as e2:
            # 修复失败，抛出详细错误信息
            error_msg = f"JSON解析失败: {e2}\n错误位置附近的内容:\n{json_str[max(0, e2.pos-100):min(len(json_str), e2.pos+100)]}"
            if verbose:
                print(f"[JSONDecodeError] {error_msg}")
            raise ValueError(error_msg)


def tag_document_pages(
    client,
    doc_name: str,
    page_numbers: List[int],
    image_dir: str,
    json_path: str,
    prompt_template: str,
    temperature: float = 0.000001,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    对多页文档进行行级标签分类（批量处理，一次传递所有页）

    Args:
        client: BaiduImageClientBearer 实例
        doc_name: 文档名称
        page_numbers: 要处理的页码列表（会一次性全部处理）
        image_dir: 图片目录
        json_path: JSON 文件路径
        prompt_template: 提示词模板
        temperature: 温度参数
        verbose: 是否打印详细信息

    Returns:
        {
            "doc_name": "...",
            "batch_result": {
                "pages": [0, 1, 2, ...],
                "total_lines": 100,
                "results": [{"line_id": xxx, "label": "xxx"}, ...],
                "success": True
            }
        }
    """
    if verbose:
        print(f"[LineTagger] 开始批量处理文档: {doc_name}")
        print(f"[LineTagger] 批量处理 {len(page_numbers)} 页: {page_numbers}")

    # 准备所有图片路径
    image_paths = []
    all_lines_data = []

    for page_num in page_numbers:
        image_path = os.path.join(image_dir, f"{doc_name}_{page_num}.jpg")

        if not os.path.exists(image_path):
            if verbose:
                print(f"[LineTagger] [ERROR] 图片不存在: {image_path}")
            return {
                "doc_name": doc_name,
                "batch_result": {
                    "pages": page_numbers,
                    "error": f"图片不存在: {image_path}",
                    "success": False
                }
            }

        image_paths.append(image_path)

        # 加载该页的行数据
        page_lines = load_lines_for_page(json_path, page_num)
        all_lines_data.extend(page_lines)

    if verbose:
        print(f"[LineTagger] 总共 {len(all_lines_data)} 行需要标注")

    try:
        # 批量调用标签分类
        tagged_results = tag_document_batch(
            client=client,
            image_paths=image_paths,
            lines_data=all_lines_data,
            prompt_template=prompt_template,
            temperature=temperature,
            verbose=False
        )

        if verbose:
            print(f"[LineTagger] [OK] 成功标注 {len(tagged_results)} 行")

        return {
            "doc_name": doc_name,
            "batch_result": {
                "pages": page_numbers,
                "total_lines": len(all_lines_data),
                "results": tagged_results,
                "success": True
            }
        }

    except Exception as e:
        if verbose:
            print(f"[LineTagger] [ERROR] 失败: {e}")

        return {
            "doc_name": doc_name,
            "batch_result": {
                "pages": page_numbers,
                "error": str(e),
                "success": False
            }
        }


def process_document_by_name(
    doc_name: str,
    batch_size: int = 5,
    max_pages: int = -1,
    base_dir: str = "//wsl.localhost/Ubuntu-22.04/root/code/layoutlmft/data/output",
    client = None,
    prompt_template: str = None,
    temperature: float = 0.000001,
    verbose: bool = True,
    save_results: bool = True,
    output_dir: str = ".",
    parallel: bool = True,
    max_workers: int = 5
) -> Dict[str, Any]:
    """
    根据文件名自动处理文档（Pipeline 完整入口）

    Args:
        doc_name: 文档名称（不含扩展名）
        batch_size: 每批处理的图片数量，默认5张
        max_pages: 最大处理页数，-1表示全量处理，正整数表示处理到该页数或图片最大数停止
        base_dir: 基础目录，默认 WSL 路径
        client: BaiduImageClientBearer 实例，如果为 None 则自动创建
        prompt_template: 提示词模板，如果为 None 则使用默认
        temperature: 温度参数
        verbose: 是否打印详细信息
        save_results: 是否保存结果到文件
        output_dir: 输出目录
        parallel: 是否并行处理多个批次，默认 True
        max_workers: 最大并发数，默认 5

    Returns:
        完整的标注结果字典
    """
    # 初始化客户端
    if client is None:
        from tender_ontology.utils.document_struct.baidu_client_bearer import BaiduImageClientBearer
        client = BaiduImageClientBearer()

    # 使用默认提示词
    if prompt_template is None:
        from tender_ontology.prompts.document_struct.document_layout_analysis_prompt import DOCUMENT_LAYOUT_ANALYSIS_PROMPT
        prompt_template = DOCUMENT_LAYOUT_ANALYSIS_PROMPT

    # 构建路径
    test_dir = os.path.join(base_dir, "test")
    json_path = os.path.join(test_dir, f"{doc_name}.json")
    image_dir = os.path.join(base_dir, "images", doc_name)

    if verbose:
        print(f"[Pipeline] 文档名称: {doc_name}")
        print(f"[Pipeline] JSON路径: {json_path}")
        print(f"[Pipeline] 图片目录: {image_dir}")

    # 检查文件是否存在
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"JSON文件不存在: {json_path}")

    if not os.path.exists(image_dir):
        raise FileNotFoundError(f"图片目录不存在: {image_dir}")

    # 获取所有页码（通过扫描图片目录）
    image_files = sorted(Path(image_dir).glob(f"{doc_name}_*.jpg"))
    page_numbers = []
    for img_file in image_files:
        # 从文件名提取页码：fileName_pageNumber.jpg
        filename = img_file.stem  # 去掉扩展名
        if "_" in filename:
            page_num_str = filename.split("_")[-1]
            try:
                page_num = int(page_num_str)
                page_numbers.append(page_num)
            except ValueError:
                continue

    page_numbers.sort()

    # 根据 max_pages 限制处理页数
    if max_pages > 0:
        page_numbers = page_numbers[:max_pages]

    if verbose:
        print(f"[Pipeline] 找到 {len(page_numbers)} 页: {page_numbers[:10]}{'...' if len(page_numbers) > 10 else ''}")
        if max_pages > 0:
            print(f"[Pipeline] 最大处理页数: {max_pages}")
        print(f"[Pipeline] 批次大小: {batch_size} 页/批")
        if parallel:
            print(f"[Pipeline] 并行模式: 最大 {max_workers} 个并发")

    # 分批处理
    total_batches = (len(page_numbers) + batch_size - 1) // batch_size
    all_results = {
        "doc_name": doc_name,
        "batches": [],
        "summary": {
            "total_pages": len(page_numbers),
            "success_batches": 0,
            "total_lines": 0,
            "total_batches": total_batches
        }
    }

    # 准备所有批次
    batch_tasks = []
    for batch_idx in range(total_batches):
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, len(page_numbers))
        batch_pages = page_numbers[start_idx:end_idx]
        batch_tasks.append((batch_idx + 1, batch_pages))

    if parallel and total_batches > 1:
        # 并行处理
        _print_lock = threading.Lock()
        batch_results_dict = {}

        def process_one_batch(batch_info):
            batch_idx, batch_pages = batch_info
            try:
                with _print_lock:
                    if verbose:
                        print(f"\n[Pipeline] [批次 {batch_idx}/{total_batches}] 开始处理第 {batch_pages[0]} - {batch_pages[-1]} 页")

                batch_result = tag_document_pages(
                    client=client,
                    doc_name=doc_name,
                    page_numbers=batch_pages,
                    image_dir=image_dir,
                    json_path=json_path,
                    prompt_template=prompt_template,
                    temperature=temperature,
                    verbose=False  # 并发时关闭详细输出
                )

                with _print_lock:
                    if verbose:
                        success = batch_result["batch_result"].get("success", False)
                        status = "成功" if success else "失败"
                        print(f"[Pipeline] [批次 {batch_idx}/{total_batches}] {status}")

                return (batch_idx, batch_result)
            except Exception as e:
                with _print_lock:
                    if verbose:
                        print(f"[Pipeline] [批次 {batch_idx}/{total_batches}] 失败: {e}")
                return (batch_idx, None)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_one_batch, task): task for task in batch_tasks}

            for future in as_completed(futures):
                batch_idx, batch_result = future.result()
                if batch_result:
                    batch_results_dict[batch_idx] = batch_result

        # 按顺序合并结果
        for batch_idx in range(1, total_batches + 1):
            if batch_idx in batch_results_dict:
                batch_result = batch_results_dict[batch_idx]
                all_results["batches"].append(batch_result["batch_result"])
                if batch_result["batch_result"].get("success", False):
                    all_results["summary"]["success_batches"] += 1
                    all_results["summary"]["total_lines"] += batch_result["batch_result"].get("total_lines", 0)

    else:
        # 串行处理
        for batch_idx, batch_pages in batch_tasks:
            if verbose:
                print(f"\n[Pipeline] ========== 批次 {batch_idx}/{total_batches} ==========")
                print(f"[Pipeline] 处理第 {batch_pages[0]} - {batch_pages[-1]} 页")

            # 处理这一批
            batch_results = tag_document_pages(
                client=client,
                doc_name=doc_name,
                page_numbers=batch_pages,
                image_dir=image_dir,
                json_path=json_path,
                prompt_template=prompt_template,
                temperature=temperature,
                verbose=verbose
            )

            # 合并结果
            all_results["batches"].append(batch_results["batch_result"])

            if batch_results["batch_result"].get("success", False):
                all_results["summary"]["success_batches"] += 1
                all_results["summary"]["total_lines"] += batch_results["batch_result"].get("total_lines", 0)

    # 保存结果到 test 目录（带时间戳）
    if save_results:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = os.path.join(test_dir, f"{doc_name}_tagged_results_{timestamp}.json")

        # 添加时间戳到结果中
        all_results["timestamp"] = timestamp
        all_results["created_at"] = datetime.now().isoformat()

        # 写入结果
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)

        if verbose:
            print(f"\n[Pipeline] 结果已保存到: {output_file}")

        # 回写 class 字段到原始 JSON
        try:
            # 读取原始 JSON
            with open(json_path, 'r', encoding='utf-8') as f:
                original_data = json.load(f)

            # 构建 line_id -> label 映射
            line_id_to_label = {}
            for batch in all_results["batches"]:
                if batch.get("success", False):
                    for result in batch.get("results", []):
                        line_id = result.get("line_id")
                        label = result.get("label")
                        if line_id is not None and label:
                            line_id_to_label[line_id] = label

            # 回写 class 字段
            updated_count = 0
            for line in original_data:
                line_id = line.get("line_id")
                if line_id in line_id_to_label:
                    line["class"] = line_id_to_label[line_id]
                    updated_count += 1

            # 保存回写后的 JSON
            tagged_output_file = os.path.join(test_dir, f"{doc_name}_tagged_{timestamp}.json")
            with open(tagged_output_file, 'w', encoding='utf-8') as f:
                json.dump(original_data, f, ensure_ascii=False, indent=2)

            if verbose:
                print(f"[Pipeline] 已回写 {updated_count} 行的 class 字段")
                print(f"[Pipeline] 回写结果已保存到: {tagged_output_file}")

        except Exception as e:
            if verbose:
                print(f"[Pipeline] [WARNING] 回写 class 字段失败: {e}")

    if verbose:
        print(f"\n[Pipeline] ========== 处理完成 ==========")
        print(f"[Pipeline] 总页数: {all_results['summary']['total_pages']}")
        print(f"[Pipeline] 成功批次: {all_results['summary']['success_batches']}/{all_results['summary']['total_batches']}")
        print(f"[Pipeline] 总行数: {all_results['summary']['total_lines']}")

    return all_results


if __name__ == "__main__":
    # 测试完整 pipeline
    doc_name = "城市大数据中心物业管理服务"

    # 方式1：处理前3页（快速测试）
    results = process_document_by_name(
        doc_name=doc_name,
        batch_size=3,
        max_pages=10,
        verbose=True
    )

    # 方式2：处理所有页，每批5页
    # results = process_document_by_name(
    #     doc_name=doc_name,
    #     batch_size=5,
    #     max_pages=-1,
    #     verbose=True
    # )
