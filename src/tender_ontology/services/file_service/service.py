"""
文件处理服务

统一入口，根据文件类型分发到不同的处理器：
- PDF: 使用 Docling 处理 (background_task.process_pdf_sync)
- DOCX: 使用 Unstructured 处理 (UnstructuredHeadingExtractor)
"""

import threading
from pathlib import Path
from typing import Optional, Dict, Any


class FileService:
    """文件处理服务"""

    # 支持的文件类型
    SUPPORTED_EXTENSIONS = {".pdf", ".docx"}

    def __init__(self):
        """初始化文件服务"""
        self._pdf_handler = None
        self._docx_extractor = None

    @property
    def pdf_handler(self):
        """懒加载 PDF 处理器"""
        if self._pdf_handler is None:
            from tender_ontology.services.docling.background_task import get_background_task_handler
            self._pdf_handler = get_background_task_handler()
        return self._pdf_handler

    @property
    def docx_extractor(self):
        """懒加载 DOCX 提取器"""
        if self._docx_extractor is None:
            from tender_ontology.utils.unstructured.unstructured_heading_extractor import UnstructuredHeadingExtractor
            self._docx_extractor = UnstructuredHeadingExtractor(
                verbose=True,
                inspect_elements=3,
                enable_secondary_validation=True
            )
        return self._docx_extractor

    def is_supported(self, file_path: Path) -> bool:
        """检查文件类型是否支持"""
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def get_file_type(self, file_path: Path) -> Optional[str]:
        """获取文件类型"""
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            return "pdf"
        elif suffix == ".docx":
            return "docx"
        return None

    def process_file(
        self,
        file_path: Path,
        task_id: str,
        db_task_id: Optional[int] = None,
        output_dir: Optional[Path] = None,
        async_mode: bool = True
    ) -> Dict[str, Any]:
        """
        处理文件（统一入口）

        Args:
            file_path: 文件路径
            task_id: 任务 ID
            db_task_id: 数据库任务 ID（用于更新状态）
            output_dir: 输出目录（可选，默认使用文件所在目录）
            async_mode: 是否异步处理（后台线程），默认 True

        Returns:
            处理结果或启动信息
        """
        file_path = Path(file_path)

        if not file_path.exists():
            return {
                "success": False,
                "error": f"文件不存在: {file_path}"
            }

        file_type = self.get_file_type(file_path)
        if file_type is None:
            return {
                "success": False,
                "error": f"不支持的文件类型: {file_path.suffix}"
            }

        if output_dir is None:
            output_dir = file_path.parent

        print(f"[FileService] ========== Start ==========")
        print(f"[FileService] File: {file_path.name}")
        print(f"[FileService] Type: {file_type}")
        print(f"[FileService] Task ID: {task_id}")
        print(f"[FileService] Async: {async_mode}")
        print(f"[FileService] ============================")

        if async_mode:
            # 异步模式：启动后台线程
            thread = threading.Thread(
                target=self._process_file_sync,
                args=(file_path, file_type, task_id, db_task_id, output_dir),
                daemon=False
            )
            thread.start()

            return {
                "success": True,
                "task_id": task_id,
                "file_type": file_type,
                "message": f"{file_type.upper()} 后台处理已启动"
            }
        else:
            # 同步模式：直接处理
            return self._process_file_sync(file_path, file_type, task_id, db_task_id, output_dir)

    def _process_file_sync(
        self,
        file_path: Path,
        file_type: str,
        task_id: str,
        db_task_id: Optional[int],
        output_dir: Path
    ) -> Dict[str, Any]:
        """
        同步处理文件

        Args:
            file_path: 文件路径
            file_type: 文件类型 (pdf/docx)
            task_id: 任务 ID
            db_task_id: 数据库任务 ID
            output_dir: 输出目录

        Returns:
            处理结果
        """
        if file_type == "pdf":
            return self._process_pdf(file_path, task_id, db_task_id, output_dir)
        elif file_type == "docx":
            return self._process_docx(file_path, task_id, db_task_id, output_dir)
        else:
            return {
                "success": False,
                "error": f"未知文件类型: {file_type}"
            }

    def _process_pdf(
        self,
        file_path: Path,
        task_id: str,
        db_task_id: Optional[int],
        output_dir: Path
    ) -> Dict[str, Any]:
        """
        处理 PDF 文件

        使用 Docling 处理器
        """
        print(f"[FileService] 使用 Docling 处理 PDF...")
        return self.pdf_handler.process_pdf_sync(
            pdf_path=file_path,
            task_id=task_id,
            db_task_id=db_task_id,
            output_dir=output_dir
        )

    def _process_docx(
        self,
        file_path: Path,
        task_id: str,
        db_task_id: Optional[int],
        output_dir: Path
    ) -> Dict[str, Any]:
        """
        处理 DOCX 文件

        流程：
        1. 调用 DOCX 转 PDF 服务 (/process)
        2. 调用第二个接口（TODO: 等待提供）
        3. 下载结果 ZIP (/artifact/{taskId})
        4. 使用 UnstructuredHeadingExtractor 提取标题
        """
        print(f"[FileService] 开始处理 DOCX...")

        try:
            # 更新状态为"处理中"
            if db_task_id:
                self._update_task_status(db_task_id, status=3, message="DOCX 解析中...")

            artifacts = {}

            # ========== 并行执行两个任务 ==========
            # 1. 调用 DOCX 转 PDF 服务（下载 ZIP）
            # 2. Unstructured 提取标题
            import concurrent.futures

            print(f"[FileService] 并行启动: DOCX 转 PDF + Unstructured 提取...")

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                # 提交两个任务
                pdf_future = executor.submit(
                    self._call_docx_to_pdf_service,
                    file_path,
                    output_dir
                )
                unstructured_future = executor.submit(
                    self.docx_extractor.extract_full_hierarchy,
                    file_path,
                    8  # max_workers
                )

                # 等待两个任务完成
                pdf_result = pdf_future.result()
                result = unstructured_future.result()

            # 处理 PDF 结果
            id_to_location = {}
            if pdf_result:
                artifacts["docx_pdf"] = pdf_result
                artifacts["pdf_path"] = pdf_result.get("pdf_path", "")
                print(f"[FileService] DOCX 转 PDF 完成: {pdf_result.get('pdf_path', '')}")

                # 解析位置信息
                id_to_location = self._parse_location_files(output_dir)
                print(f"[FileService] 解析位置信息: {len(id_to_location)} 个元素")

            # 处理 Unstructured 结果
            print(f"[FileService] Unstructured 提取完成")

            # 回填位置信息到 fulltext.md
            if id_to_location:
                fulltext_md_path = output_dir / f"{file_path.stem}_unstructured_fulltext.md"
                if fulltext_md_path.exists():
                    self._backfill_location_to_fulltext(fulltext_md_path, id_to_location)
                    print(f"[FileService] 位置信息已回填到 fulltext.md")

            # 构建返回结果
            artifacts.update({
                "section_header_md": str(result.get("section_header_md_path", "")),
                "title_with_id_md": str(result.get("title_with_id_md_path", "")),
                "level12_count": len(result.get("level12_headings", [])),
                "all_headings_count": len(result.get("all_headings", []))
            })

            # ========== Step 3: 构建 agent.json 并调用 extract_onto API ==========
            all_headings = result.get("all_headings", [])
            if all_headings:
                onto_result = self._build_agent_and_call_onto_api(
                    task_id=task_id,
                    output_dir=output_dir,
                    file_stem=file_path.stem,
                    all_headings=all_headings
                )
                if onto_result:
                    artifacts.update(onto_result)

            # 更新状态为"完成"
            if db_task_id:
                self._update_task_status(
                    db_task_id,
                    status=2,
                    message="DOCX 解析完成",
                    artifacts=artifacts
                )

            return {
                "success": True,
                "task_id": task_id,
                "file_type": "docx",
                "total_time": result.get("total_time", 0),
                "stage0_time": result.get("stage0_time", 0),
                "stage1_time": result.get("stage1_time", 0),
                "stage2_time": result.get("stage2_time", 0),
                "artifacts": artifacts
            }

        except Exception as e:
            print(f"[FileService] DOCX 处理失败: {e}")
            import traceback
            traceback.print_exc()

            # 更新状态为"失败"
            if db_task_id:
                self._update_task_status(db_task_id, status=4, message=f"DOCX 解析失败: {str(e)}")

            return {
                "success": False,
                "task_id": task_id,
                "error": str(e)
            }

    def _call_docx_to_pdf_service(
        self,
        docx_path: Path,
        output_dir: Path
    ) -> Optional[Dict[str, Any]]:
        """
        调用 DOCX 转 PDF 服务

        流程：
        1. POST /api/docx-pdf/process - 上传并处理
        2. TODO: 调用第二个接口（等待提供）
        3. GET /api/docx-pdf/artifact/{taskId} - 下载结果 ZIP
        4. 解压 ZIP 并重命名 PDF 为原始 DOCX 文件名

        Args:
            docx_path: DOCX 文件路径
            output_dir: 输出目录

        Returns:
            处理结果或 None
        """
        try:
            from tender_ontology.config.settings import settings
            from tender_ontology.utils.request.http_client import DocxPdfClient

            # 从配置获取服务地址
            base_url = settings.docx_pdf_service_url

            print(f"[FileService] 调用 DOCX 转 PDF 服务: {base_url}")

            client = DocxPdfClient(
                base_url=base_url,
                timeout=120.0,
                verbose=False  # 关闭详细日志
            )

            # Step 1: 上传并处理
            print(f"[FileService] Step 1: 上传 DOCX 到 /process...")
            process_result = client.process(docx_path, include_mcid=True)

            if not process_result.get("success"):
                print(f"[FileService] /process 失败: {process_result.get('message')}")
                return None

            remote_task_id = process_result.get("taskId")
            print(f"[FileService] /process 成功, taskId: {remote_task_id}")

            # Step 2: 等待任务完成
            print(f"[FileService] Step 2: 等待任务完成...")
            wait_result = client.wait_for_completion(remote_task_id)

            if not wait_result.get("success"):
                print(f"[FileService] 任务未完成: {wait_result.get('message')}")
                return None

            # Step 3: 下载结果 ZIP
            print(f"[FileService] Step 3: 下载结果 ZIP...")
            zip_path = output_dir / f"{remote_task_id}.zip"
            client.download_artifact(remote_task_id, zip_path)

            # Step 4: 解压 ZIP 并重命名 PDF
            # 目标 PDF 名称：与原始 DOCX 同名，只是扩展名改为 .pdf
            target_pdf_name = docx_path.stem + ".pdf"
            extracted_files = self._extract_zip(zip_path, output_dir, target_pdf_name)

            return {
                "remote_task_id": remote_task_id,
                "zip_path": str(zip_path),
                "extracted_files": extracted_files,
                "pdf_path": str(output_dir / target_pdf_name)
            }

        except Exception as e:
            print(f"[FileService] DOCX 转 PDF 服务调用失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _extract_zip(
        self,
        zip_path: Path,
        output_dir: Path,
        target_pdf_name: Optional[str] = None
    ) -> list:
        """
        解压 ZIP 文件

        Args:
            zip_path: ZIP 文件路径
            output_dir: 输出目录
            target_pdf_name: 目标 PDF 文件名（如果指定，会将 ZIP 中的 PDF 重命名）

        Returns:
            解压出的文件列表（重命名后的路径）
        """
        import zipfile

        extracted = []
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for name in zf.namelist():
                    # 解压文件
                    zf.extract(name, output_dir)
                    extracted_path = output_dir / name

                    # 如果是 PDF 文件且指定了目标名称，则重命名
                    if target_pdf_name and name.lower().endswith('.pdf'):
                        target_path = output_dir / target_pdf_name
                        # 如果目标路径已存在且不是同一个文件，先删除
                        if target_path.exists() and target_path != extracted_path:
                            target_path.unlink()
                        # 重命名
                        extracted_path.rename(target_path)
                        print(f"[FileService] 解压并重命名: {name} -> {target_pdf_name}")
                        extracted.append(str(target_path))
                    else:
                        print(f"[FileService] 解压: {name}")
                        extracted.append(str(extracted_path))
        except Exception as e:
            print(f"[FileService] 解压失败: {e}")

        return extracted

    def _build_agent_and_call_onto_api(
        self,
        task_id: str,
        output_dir: Path,
        file_stem: str,
        all_headings: list
    ) -> Optional[Dict[str, Any]]:
        """
        使用 LevelTreeConstructor 构建文档树，生成 agent.json 并调用 extract_onto API

        Args:
            task_id: 任务 ID
            output_dir: 输出目录
            file_stem: 文件名（不含扩展名）
            all_headings: Unstructured 提取的标题列表
                格式: [{id, text, level, type?}, ...]

        Returns:
            包含 agent_path 和 ontology_path 的字典，或 None
        """
        import json
        import time
        import requests
        import re
        import glob

        try:
            print(f"[FileService] 开始构建文档树...")

            # 1. 读取 fulltext.md（所有元素，含表格）
            fulltext_path = output_dir / f"{file_stem}_unstructured_fulltext.md"
            if not fulltext_path.exists():
                print(f"[FileService] 警告: {fulltext_path.name} 不存在，跳过树构建")
                return None

            # 解析 fulltext.md 为 items 列表
            fulltext_items = self._parse_fulltext_md(fulltext_path)
            print(f"[FileService] 读取 fulltext: {len(fulltext_items)} 个元素")

            # 1.5 解析 paragraph.txt 和 table.txt 获取 id -> page/bbox 映射
            id_to_location = self._parse_location_files(output_dir)
            print(f"[FileService] 读取位置信息: {len(id_to_location)} 个元素")

            # 2. 转换 all_headings 为 model_headings 格式
            # all_headings: [{id, text, level, type?}, ...]
            # model_headings 需要: [{id, text, level}, ...]
            model_headings = []
            for h in all_headings:
                model_headings.append({
                    "id": h.get("id", ""),
                    "text": h.get("text", ""),
                    "level": h.get("level", 1)
                })
            print(f"[FileService] 标题数: {len(model_headings)}")

            # 3. 构建 id -> level 映射 和 id -> heading 映射
            heading_level_map = {h["id"]: h["level"] for h in model_headings}
            heading_text_map = {h["id"]: h["text"] for h in model_headings}
            heading_ids = set(heading_level_map.keys())

            # 4. 构建 id -> fulltext_index 映射
            id_to_index = {item["id"]: i for i, item in enumerate(fulltext_items)}

            # 5. 按 level 切分，递归构建树（包含段落内容）
            def build_tree_recursive(items_slice, parent_level=0):
                """
                递归构建树，将段落内容挂载到对应的标题下

                逻辑：
                1. 遍历 items_slice，遇到标题时创建节点
                2. 标题和下一个同级/上级标题之间的内容作为该标题的 children
                3. 非标题的段落直接作为叶子节点挂载

                Args:
                    items_slice: fulltext 的切片（按索引范围）
                    parent_level: 父节点的 level

                Returns:
                    children 列表
                """
                if not items_slice:
                    return []

                children = []
                current_heading_idx = None
                current_heading_level = None
                current_children_start = None

                # 收集当前标题之前的非标题内容
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
                                "location": self._get_location_for_id(prev_id, id_to_location),
                                "children": sub_children if sub_children else None
                            })
                        else:
                            # 第一个标题之前的非标题内容，作为独立节点添加
                            for pre_item in pre_heading_items:
                                pre_id = pre_item.get("id", "")
                                children.append({
                                    "pid": pre_id,
                                    "title": "",
                                    "content": pre_item.get("text", ""),
                                    "location": self._get_location_for_id(pre_id, id_to_location)
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
                        "location": self._get_location_for_id(prev_id, id_to_location),
                        "children": sub_children if sub_children else None
                    })
                else:
                    # 整个 slice 没有标题，全部作为叶子节点（段落内容）
                    for item in items_slice:
                        item_id = item.get("id", "")
                        children.append({
                            "pid": item_id,
                            "title": "",
                            "content": item.get("text", ""),
                            "location": self._get_location_for_id(item_id, id_to_location)
                        })

                # 移除空的 children
                for child in children:
                    if "children" in child and child["children"] is None:
                        del child["children"]

                return children

            # 6. 找到所有一级标题的位置，按一级标题切分
            level1_positions = []
            for i, item in enumerate(fulltext_items):
                item_id = item.get("id", "")
                if item_id in heading_ids and heading_level_map.get(item_id) == 1:
                    level1_positions.append(i)

            print(f"[FileService] 一级标题数: {len(level1_positions)}")

            # 7. 构建根节点列表
            structured_data = []

            # 处理第一个一级标题之前的内容（如果有）
            if level1_positions and level1_positions[0] > 0:
                # 文档开头有非标题内容，创建一个虚拟根节点
                pre_items = fulltext_items[:level1_positions[0]]
                for item in pre_items:
                    item_id = item.get("id", "")
                    structured_data.append({
                        "pid": item_id,
                        "title": "",
                        "content": item.get("text", ""),
                        "location": self._get_location_for_id(item_id, id_to_location)
                    })

            # 处理每个一级标题
            for idx, pos in enumerate(level1_positions):
                # 确定范围：当前一级标题到下一个一级标题（或文档末尾）
                end_pos = level1_positions[idx + 1] if idx + 1 < len(level1_positions) else len(fulltext_items)
                section_items = fulltext_items[pos:end_pos]

                if not section_items:
                    continue

                # 当前一级标题
                first_item = section_items[0]
                first_id = first_item.get("id", "")
                first_text = heading_text_map.get(first_id, first_item.get("text", ""))

                # 递归构建子树（从第二个元素开始）
                sub_items = section_items[1:]
                sub_children = build_tree_recursive(sub_items, 1)

                root_node = {
                    "pid": first_id,
                    "title": first_text,
                    "content": first_text,
                    "location": self._get_location_for_id(first_id, id_to_location)
                }
                if sub_children:
                    root_node["children"] = sub_children

                structured_data.append(root_node)

            print(f"[FileService] 树构建完成，根节点数: {len(structured_data)}")

            # 5. 保存 _agent.json
            agent_path = output_dir / f"{file_stem}_agent.json"
            agent_path.write_text(
                json.dumps(structured_data, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            print(f"[FileService] Agent JSON 已保存: {agent_path.name}")

            # 6. 调用 extract_onto API
            from tender_ontology.config.settings import settings

            api_url = settings.tender_extract_api_url
            request_data = {
                "task_id": task_id,
                "pdf_url": "",
                "document_type": "",
                "region": "",
                "structured_data": structured_data
            }

            print(f"[FileService] 调用 extract_onto API...")
            print(f"[FileService] URL: {api_url}")

            start_time = time.time()
            response = requests.post(
                api_url,
                json=request_data,
                headers={"Content-Type": "application/json"},
                timeout=settings.tender_extract_api_timeout
            )
            elapsed_time = time.time() - start_time

            result = {}
            result["agent_path"] = str(agent_path)

            if response.status_code == 200:
                api_result = response.json()
                print(f"[FileService] extract_onto API 调用成功，耗时: {elapsed_time:.2f} 秒")

                # 保存响应到 _ontology.json
                ontology_path = output_dir / f"{file_stem}_ontology.json"
                ontology_path.write_text(
                    json.dumps(api_result, ensure_ascii=False, indent=2),
                    encoding='utf-8'
                )
                print(f"[FileService] Ontology JSON 已保存: {ontology_path.name}")
                result["ontology_path"] = str(ontology_path)
            else:
                print(f"[FileService] extract_onto API 调用失败: HTTP {response.status_code}")
                print(f"[FileService] 响应: {response.text[:500]}")

            return result

        except requests.Timeout:
            print(f"[FileService] extract_onto API 请求超时")
            return None
        except Exception as e:
            print(f"[FileService] 构建文档树或调用 API 失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _backfill_location_to_fulltext(
        self,
        fulltext_path: Path,
        id_to_location: Dict[str, Dict[str, Any]]
    ):
        """
        将位置信息回填到 fulltext.md 文件中

        原格式: # [Title] 文本 {id=P_00001}
        回填后: # [Title] 文本 {id=P_00001, page=1, bbox=90.9,200.5,514.4,210.5}

        Args:
            fulltext_path: fulltext.md 文件路径
            id_to_location: id -> page/bbox 映射
        """
        import re

        content = fulltext_path.read_text(encoding='utf-8')
        lines = content.split('\n')
        updated_lines = []

        # 匹配 {id=xxx} 或 {id=xxx, ...}
        id_pattern = re.compile(r'\{id=([^},]+)([^}]*)\}')

        for line in lines:
            # 查找 {id=xxx} 模式
            match = id_pattern.search(line)
            if match:
                item_id = match.group(1)
                existing_attrs = match.group(2)  # 可能有其他属性

                # 获取位置信息
                loc_info = self._get_raw_location_for_id(item_id, id_to_location)

                if loc_info:
                    page = loc_info.get("page", "")
                    bbox = loc_info.get("bbox", "")

                    # 构建新的属性字符串
                    new_attrs = f"id={item_id}, page={page}, bbox={bbox}"
                    new_tag = "{" + new_attrs + "}"

                    # 替换原来的 {id=xxx...}
                    line = id_pattern.sub(new_tag, line)

            updated_lines.append(line)

        # 写回文件
        fulltext_path.write_text('\n'.join(updated_lines), encoding='utf-8')

    def _get_raw_location_for_id(
        self,
        item_id: str,
        id_to_location: Dict[str, Dict[str, Any]]
    ) -> Optional[Dict[str, str]]:
        """
        根据 id 获取原始位置信息（不转换格式）

        Args:
            item_id: 元素 ID (如 P_00001, t001)
            id_to_location: id -> page/bbox 映射

        Returns:
            {"page": "1", "bbox": "x1,y1,x2,y2"} 或 None
        """
        # 尝试直接匹配
        loc_info = id_to_location.get(item_id)

        # 如果是 P_00001 格式，尝试转换为 p001 格式
        if not loc_info and item_id.startswith("P_"):
            try:
                num = int(item_id.replace("P_", ""))
                alt_id = f"p{num:03d}"
                loc_info = id_to_location.get(alt_id)
            except ValueError:
                pass

        return loc_info

    def _parse_location_files(self, output_dir: Path) -> Dict[str, Dict[str, Any]]:
        """
        解析 paragraph.txt 和 table.txt 获取 id -> page/bbox 映射

        文件格式:
        - paragraph.txt: <p id="p001" type="P" mcid="4" page="1" bbox="x1,y1,x2,y2">文本</p>
        - table.txt: <table id="t001" type="Table" page="1" bbox="x1,y1,x2,y2">...</table>

        Args:
            output_dir: 输出目录

        Returns:
            {id: {"page": "1", "bbox": "x1,y1,x2,y2"}, ...}
        """
        import re

        id_to_location = {}

        # 匹配段落: <p id="p001" ... page="1" bbox="...">
        p_pattern = re.compile(r'<p\s+id="([^"]+)"[^>]*page="([^"]+)"[^>]*bbox="([^"]+)"')
        # 匹配表格: <table id="t001" ... page="1" bbox="...">
        table_pattern = re.compile(r'<table\s+id="([^"]+)"[^>]*page="([^"]+)"[^>]*bbox="([^"]+)"')

        # 解析 paragraph.txt
        paragraph_files = list(output_dir.glob("*_paragraph.txt"))
        for pf in paragraph_files:
            try:
                content = pf.read_text(encoding='utf-8')
                for match in p_pattern.finditer(content):
                    pid, page, bbox = match.groups()
                    id_to_location[pid] = {"page": page, "bbox": bbox}
            except Exception as e:
                print(f"[FileService] 解析 paragraph.txt 失败: {e}")

        # 解析 table.txt (只取表格级别的 id，如 t001)
        table_files = list(output_dir.glob("*_table.txt"))
        for tf in table_files:
            try:
                content = tf.read_text(encoding='utf-8')
                for match in table_pattern.finditer(content):
                    tid, page, bbox = match.groups()
                    id_to_location[tid] = {"page": page, "bbox": bbox}
            except Exception as e:
                print(f"[FileService] 解析 table.txt 失败: {e}")

        return id_to_location

    def _get_location_for_id(self, item_id: str, id_to_location: Dict[str, Dict[str, Any]]) -> list:
        """
        根据 id 获取 location 列表

        Args:
            item_id: 元素 ID (如 P_00001, t001)
            id_to_location: id -> page/bbox 映射

        Returns:
            location 列表: [{"page": 1, "bbox": [x1,y1,x2,y2]}, ...]
        """
        # 尝试直接匹配
        loc_info = id_to_location.get(item_id)

        # 如果是 P_00001 格式，尝试转换为 p001 格式
        if not loc_info and item_id.startswith("P_"):
            # P_00001 -> p1
            try:
                num = int(item_id.replace("P_", ""))
                alt_id = f"p{num:03d}"
                loc_info = id_to_location.get(alt_id)
            except ValueError:
                pass

        if not loc_info:
            return []

        page_str = loc_info.get("page", "")
        bbox_str = loc_info.get("bbox", "")

        # 处理跨页情况: page="1|2" bbox="x1,y1,x2,y2|x3,y3,x4,y4"
        pages = page_str.split("|")
        bboxes = bbox_str.split("|")

        locations = []
        for i, page in enumerate(pages):
            try:
                page_num = int(page)
                bbox_coords = [float(x) for x in bboxes[i].split(",")] if i < len(bboxes) else []
                locations.append({
                    "page": page_num,
                    "bbox": bbox_coords
                })
            except (ValueError, IndexError):
                continue

        return locations

    def _parse_fulltext_md(self, fulltext_path: Path) -> list:
        """
        解析 fulltext.md 文件为 items 列表

        fulltext.md 格式:
        - # [category] 标题文本 {id=P_00001, ...}  -> 标题候选项
        - - [category] 段落文本 {id=P_00002, ...}  -> 普通段落
        - [Table] t001-r000-c000-p000             -> 表格
          <table>...</table>

        Args:
            fulltext_path: fulltext.md 文件路径

        Returns:
            items 列表，每个元素: {"id": "P_00001", "text": "...", "category": "..."}
        """
        import re

        content = fulltext_path.read_text(encoding='utf-8')
        lines = content.split('\n')

        items = []
        id_pattern = re.compile(r'\{id=([^},]+)')
        category_pattern = re.compile(r'\[([^\]]+)\]')

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # 跳过空行
            if not line:
                i += 1
                continue

            # 跳过文件头部的标题（如 "# 文件名 - 全文内容"）
            if line.startswith('# ') and ' - 全文内容' in line:
                i += 1
                continue

            # 跳过注释行
            if line.startswith('>'):
                i += 1
                continue

            # 处理表格
            if line.startswith('[Table]'):
                # 提取表格 ID
                parts = line.split(' ', 1)
                table_id = parts[1].strip() if len(parts) > 1 else ""

                # 收集表格内容（直到下一个非表格行）
                table_content = []
                i += 1
                while i < len(lines):
                    next_line = lines[i]
                    # 如果遇到新的标记行，结束表格
                    if next_line.strip().startswith('#') or next_line.strip().startswith('-') or next_line.strip().startswith('[Table]'):
                        break
                    if next_line.strip():
                        table_content.append(next_line)
                    i += 1

                items.append({
                    "id": table_id,
                    "text": '\n'.join(table_content),
                    "category": "Table"
                })
                continue

            # 处理标题候选项 (# 开头) 和普通段落 (- 开头)
            if line.startswith('#') or line.startswith('-'):
                # 提取 id
                id_match = id_pattern.search(line)
                item_id = id_match.group(1) if id_match else ""

                # 提取 category
                cat_match = category_pattern.search(line)
                category = cat_match.group(1) if cat_match else ""

                # 提取文本
                # 移除 # 或 - 前缀
                if line.startswith('#'):
                    text = re.sub(r'^#+\s*', '', line)
                else:
                    text = re.sub(r'^-\s*', '', line)

                # 移除 [category]
                text = re.sub(r'\[[^\]]+\]\s*', '', text)
                # 移除 {id=..., ...}
                text = re.sub(r'\{[^}]+\}', '', text)
                text = text.strip()

                if item_id:  # 只添加有 id 的条目
                    items.append({
                        "id": item_id,
                        "text": text,
                        "category": category
                    })

            i += 1

        return items

    def _update_task_status(
        self,
        task_id: int,
        status: int,
        message: Optional[str] = None,
        artifacts: Optional[Dict[str, Any]] = None
    ):
        """
        更新数据库/存储中的任务状态

        Args:
            task_id: 数据库任务 ID
            status: 状态码 (1=待审查, 2=完成, 3=处理中, 4=失败)
            message: 状态消息
            artifacts: 生成的文件信息
        """
        try:
            from tender_ontology.utils.db.local_storage import is_local_mode, get_local_storage

            if is_local_mode():
                storage = get_local_storage()
                storage.update_task_status(task_id, status, message)
                print(f"[FileService] Task {task_id} status updated to {status} (local)")
            else:
                from tender_ontology.utils.db.mysql import get_db
                from tender_ontology.utils.db.mysql.models import ComplianceFileTask
                from datetime import datetime

                mysql = get_db()
                with mysql.get_session() as session:
                    task = session.query(ComplianceFileTask).filter(
                        ComplianceFileTask.id == task_id
                    ).first()

                    if task:
                        task.review_status = status
                        task.update_time = datetime.now()
                        session.commit()
                        print(f"[FileService] Task {task_id} status updated to {status} (mysql)")

        except Exception as e:
            print(f"[FileService] Failed to update task status: {e}")
            import traceback
            traceback.print_exc()


# 全局服务实例
_file_service = None


def get_file_service() -> FileService:
    """
    获取全局文件服务实例（单例模式）

    Returns:
        FileService 实例
    """
    global _file_service
    if _file_service is None:
        _file_service = FileService()
    return _file_service


# ============== 命令行入口 ==============

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python -m tender_ontology.services.file_service.service <file_path> [task_id]")
        print("示例:")
        print("  python -m tender_ontology.services.file_service.service static/upload/xxx/test.pdf")
        print("  python -m tender_ontology.services.file_service.service static/upload/xxx/test.docx task123")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    task_id = sys.argv[2] if len(sys.argv) > 2 else file_path.parent.name

    print(f"{'=' * 60}")
    print(f"[FileService] 文件处理测试")
    print(f"{'=' * 60}")
    print(f"文件: {file_path}")
    print(f"任务 ID: {task_id}")

    service = get_file_service()
    result = service.process_file(
        file_path=file_path,
        task_id=task_id,
        async_mode=False  # 命令行测试用同步模式
    )

    print(f"\n{'=' * 60}")
    print(f"[结果]")
    print(f"{'=' * 60}")
    print(f"成功: {result.get('success')}")
    if result.get('success'):
        print(f"耗时: {result.get('total_time', 0):.2f} 秒")
        print(f"Artifacts: {result.get('artifacts', {})}")
    else:
        print(f"错误: {result.get('error')}")
