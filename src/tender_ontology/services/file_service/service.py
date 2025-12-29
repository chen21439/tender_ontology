"""
文件处理服务

统一入口，根据文件类型分发到不同的处理器：
- PDF: 使用 Docling 处理 (background_task.process_pdf_sync)
- DOCX: 使用 Unstructured 处理 (UnstructuredHeadingExtractor)
"""

import multiprocessing
from pathlib import Path
from typing import Optional, Dict, Any

from tender_ontology.config.logging_config import logger
from tender_ontology.utils.text import TextMatcher, TableMatcher, normalize_text


class FileService:
    """文件处理服务"""

    # 支持的文件类型
    SUPPORTED_EXTENSIONS = {".pdf", ".docx"}

    def __init__(self, enable_docx_stage2: bool = False):
        """
        初始化文件服务

        Args:
            enable_docx_stage2: 是否启用 DOCX 二阶段并发处理和树构建（默认关闭）
                               关闭后：只使用一阶段 level12_headings，不构建树
                               开启后：执行二阶段章节并发处理 + 树构建
        """
        self._pdf_handler = None
        self._docx_extractor = None
        self.enable_docx_stage2 = enable_docx_stage2

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
                enable_secondary_validation=True,
                enable_stage2=self.enable_docx_stage2
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

        logger.info(f"[FileService] ========== Start ==========")
        logger.info(f"[FileService] File: {file_path.name}")
        logger.info(f"[FileService] Type: {file_type}")
        logger.info(f"[FileService] Task ID: {task_id}")
        logger.info(f"[FileService] Async: {async_mode}")
        logger.info(f"[FileService] ============================")

        if async_mode:
            # 异步模式：启动独立子进程（不受主进程热更新影响）
            process = multiprocessing.Process(
                target=_process_file_in_subprocess,
                args=(file_path, file_type, task_id, db_task_id, output_dir),
                daemon=False
            )
            process.start()

            return {
                "success": True,
                "task_id": task_id,
                "file_type": file_type,
                "message": f"{file_type.upper()} 后台处理已启动 (PID: {process.pid})"
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
        logger.info(f"[FileService] 使用 Docling 处理 PDF...")
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
        2. 轮询等待完成
        3. 下载结果 ZIP (/artifact/{taskId})
        4. 调用 predict API 进行推理
        """
        logger.info(f"[FileService] 开始处理 DOCX...")

        try:
            # 更新状态为"处理中"
            if db_task_id:
                self._update_task_status(db_task_id, status=3, message="DOCX 解析中...")

            artifacts = {}

            # ========== Step 1: 调用 DOCX 转 PDF 服务（下载 ZIP） ==========
            logger.info(f"[FileService] Step 1: 调用 DOCX 转 PDF 服务...")
            pdf_result = self._call_docx_to_pdf_service(file_path, output_dir)

            # 处理 PDF 结果
            if pdf_result:
                artifacts["docx_pdf"] = pdf_result
                artifacts["pdf_path"] = pdf_result.get("pdf_path", "")
                logger.info(f"[FileService] DOCX 转 PDF 完成: {pdf_result.get('pdf_path', '')}")

            # ========== Step 2: 调用 predict API (infer_api) ==========
            logger.info(f"[FileService] Step 2: 调用 predict API...")
            predict_result = self._call_predict_service(
                document_name=file_path.stem,
                task_id=task_id
            )

            structured_data = None
            onto_data = None
            if predict_result:
                artifacts["predict"] = predict_result
                structured_data = predict_result.get("structured_data")
                onto_data = predict_result.get("onto_data")  # extract_onto 格式
                logger.info(f"[FileService] predict API 调用完成")

                # 保存树结构到 _tree.json
                if structured_data:
                    import json
                    tree_path = output_dir / f"{file_path.stem}_tree.json"
                    tree_path.write_text(
                        json.dumps(structured_data, ensure_ascii=False, indent=2),
                        encoding='utf-8'
                    )
                    artifacts["tree_path"] = str(tree_path)
                    logger.info(f"[FileService] 树结构已保存: {tree_path.name}")

                # 保存 onto 格式数据到 _agent.json
                if onto_data:
                    import json
                    agent_path = output_dir / f"{file_path.stem}_agent.json"
                    agent_path.write_text(
                        json.dumps(onto_data, ensure_ascii=False, indent=2),
                        encoding='utf-8'
                    )
                    artifacts["agent_path"] = str(agent_path)
                    logger.info(f"[FileService] Agent JSON 已保存: {agent_path.name}")

            # ========== predict 完成后标记任务为完成 ==========
            if db_task_id:
                self._update_task_status(
                    db_task_id,
                    status=2,
                    message="DOCX 解析完成",
                    artifacts=artifacts
                )
                logger.info(f"[FileService] 任务状态已更新为完成")

            # ========== Step 3: 调用 extract_onto API（可选，任务已完成） ==========
            # 使用 onto_data（extract_onto 格式），如果没有则使用 structured_data
            extract_data = onto_data or structured_data
            if extract_data:
                logger.info(f"[FileService] Step 3: 调用 extract_onto API...")
                onto_result = self._call_extract_onto_api(
                    task_id=task_id,
                    structured_data=extract_data,
                    output_dir=output_dir,
                    file_stem=file_path.stem
                )
                if onto_result:
                    artifacts["ontology_path"] = onto_result.get("ontology_path")
                    logger.info(f"[FileService] extract_onto API 调用完成")
            else:
                logger.info(f"[FileService] Step 3: 跳过 extract_onto（无数据）")

            # ========== 以下为 Unstructured 路线代码（暂时注释） ==========
            # import concurrent.futures
            # logger.info(f"[FileService] 并行启动: DOCX 转 PDF + Unstructured 提取...")
            # with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            #     pdf_future = executor.submit(
            #         self._call_docx_to_pdf_service,
            #         file_path,
            #         output_dir
            #     )
            #     unstructured_future = executor.submit(
            #         self.docx_extractor.extract_full_hierarchy,
            #         file_path,
            #         8  # max_workers
            #     )
            #     pdf_result = pdf_future.result()
            #     result = unstructured_future.result()
            #
            # # 解析位置信息
            # id_to_location = self._parse_location_files(output_dir)
            # logger.info(f"[FileService] 解析位置信息: {len(id_to_location)} 个元素")
            #
            # # 从 PDF 提取页面高度（用于坐标系转换）
            # pdf_path = Path(pdf_result.get("pdf_path", ""))
            # if pdf_path.exists():
            #     page_heights = self._extract_page_heights_from_pdf(pdf_path)
            #
            # logger.info(f"[FileService] Unstructured 提取完成")
            # artifacts.update({
            #     "section_header_md": str(result.get("section_header_md_path", "")),
            #     "title_with_id_md": str(result.get("title_with_id_md_path", "")),
            #     "level12_count": len(result.get("level12_headings", [])),
            #     "all_headings_count": len(result.get("all_headings", []))
            # })
            #
            # # 构建 agent.json 并调用 extract_onto API
            # all_headings = result.get("all_headings", [])
            # if all_headings:
            #     onto_result = self._build_agent_and_call_onto_api(
            #         task_id=task_id,
            #         output_dir=output_dir,
            #         file_stem=file_path.stem,
            #         all_headings=all_headings,
            #         page_heights=page_heights
            #     )
            #     if onto_result:
            #         artifacts.update(onto_result)
            # ========== Unstructured 路线代码结束 ==========

            return {
                "success": True,
                "task_id": task_id,
                "file_type": "docx",
                "artifacts": artifacts
            }

        except Exception as e:
            logger.error(f"[FileService] DOCX 处理失败: {e}")
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

            logger.info(f"[FileService] 调用 DOCX 转 PDF 服务: {base_url}")

            client = DocxPdfClient(
                base_url=base_url,
                timeout=120.0,
                verbose=False  # 关闭详细日志
            )

            # Step 1: 上传并处理
            logger.info(f"[FileService] Step 1: 上传 DOCX 到 /process...")
            process_result = client.process(docx_path, include_mcid=True)

            if not process_result.get("success"):
                logger.info(f"[FileService] /process 失败: {process_result.get('message')}")
                return None

            remote_task_id = process_result.get("taskId")
            logger.info(f"[FileService] /process 成功, taskId: {remote_task_id}")

            # Step 2: 等待任务完成
            logger.info(f"[FileService] Step 2: 等待任务完成...")
            wait_result = client.wait_for_completion(remote_task_id)

            if not wait_result.get("success"):
                logger.info(f"[FileService] 任务未完成: {wait_result.get('message')}")
                return None

            # Step 3: 下载结果 ZIP
            logger.info(f"[FileService] Step 3: 下载结果 ZIP...")
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
            logger.info(f"[FileService] DOCX 转 PDF 服务调用失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _call_predict_service(
        self,
        document_name: str,
        task_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        调用 predict API 进行推理

        Args:
            document_name: 文档名称（不含扩展名）
            task_id: 任务 ID

        Returns:
            API 响应结果，包含:
            - data: 原始响应数据
            - structured_data: 树结构
            - onto_data: extract_onto 格式数据
        """
        try:
            from tender_ontology.services.infer_service import PredictClient

            client = PredictClient(verbose=True)
            result = client.predict(
                document_name=document_name,
                task_id=task_id,
                build_tree=True,
                convert_to_onto=True
            )

            if result.get("success"):
                logger.info(f"[FileService] predict API 调用成功")
                # 返回完整结果（包含 structured_data 和 onto_data）
                return {
                    "data": result.get("data"),
                    "structured_data": result.get("structured_data"),
                    "onto_data": result.get("onto_data")
                }
            else:
                logger.info(f"[FileService] predict API 调用失败: {result.get('error')}")
                return None

        except Exception as e:
            logger.info(f"[FileService] predict 服务调用失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _call_extract_onto_api(
        self,
        task_id: str,
        structured_data: list,
        output_dir: Path,
        file_stem: str
    ) -> Optional[Dict[str, Any]]:
        """
        调用 extract_onto API 进行本体提取

        Args:
            task_id: 任务 ID
            structured_data: 结构化数据（文档树）
            output_dir: 输出目录
            file_stem: 文件名（不含扩展名）

        Returns:
            包含 ontology_path 的字典，或 None
        """
        import json
        import time
        import requests

        try:
            from tender_ontology.config.settings import settings

            api_url = settings.tender_extract_api_url
            request_data = {
                "task_id": task_id,
                "pdf_url": "",
                "document_type": "",
                "region": "",
                "structured_data": structured_data
            }

            logger.info(f"[FileService] 调用 extract_onto API...")
            logger.info(f"[FileService] URL: {api_url}")

            start_time = time.time()
            response = requests.post(
                api_url,
                json=request_data,
                headers={"Content-Type": "application/json"},
                timeout=settings.tender_extract_api_timeout
            )
            elapsed_time = time.time() - start_time

            if response.status_code == 200:
                api_result = response.json()
                logger.info(f"[FileService] extract_onto API 调用成功，耗时: {elapsed_time:.2f} 秒")

                # 保存响应到 _ontology.json
                ontology_path = output_dir / f"{file_stem}_ontology.json"
                ontology_path.write_text(
                    json.dumps(api_result, ensure_ascii=False, indent=2),
                    encoding='utf-8'
                )
                logger.info(f"[FileService] Ontology JSON 已保存: {ontology_path.name}")

                return {
                    "ontology_path": str(ontology_path),
                    "elapsed_time": elapsed_time,
                    "data": api_result
                }
            else:
                logger.info(f"[FileService] extract_onto API 调用失败: HTTP {response.status_code}")
                logger.info(f"[FileService] 响应: {response.text[:500]}")
                return None

        except requests.Timeout:
            logger.info(f"[FileService] extract_onto API 请求超时")
            return None
        except Exception as e:
            logger.info(f"[FileService] extract_onto API 调用失败: {e}")
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
                        logger.info(f"[FileService] 解压并重命名: {name} -> {target_pdf_name}")
                        extracted.append(str(target_path))
                    else:
                        extracted.append(str(extracted_path))
        except Exception as e:
            logger.info(f"[FileService] 解压失败: {e}")

        return extracted

    def _build_agent_and_call_onto_api(
        self,
        task_id: str,
        output_dir: Path,
        file_stem: str,
        all_headings: list,
        page_heights: Optional[Dict[int, float]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        使用 LevelTreeConstructor 构建文档树，生成 agent.json 并调用 extract_onto API

        Args:
            task_id: 任务 ID
            output_dir: 输出目录
            file_stem: 文件名（不含扩展名）
            all_headings: Unstructured 提取的标题列表
                格式: [{id, text, level, type?}, ...]
            page_heights: 页码 -> 页面高度映射，用于坐标系转换

        Returns:
            包含 agent_path 和 ontology_path 的字典，或 None
        """
        import json
        import time
        import requests
        import re
        import glob

        try:
            logger.info(f"[FileService] 开始构建文档树...")

            # 1. 读取 fulltext.md（所有元素，含表格）
            fulltext_path = output_dir / f"{file_stem}_unstructured_fulltext.md"
            if not fulltext_path.exists():
                logger.info(f"[FileService] 警告: {fulltext_path.name} 不存在，跳过树构建")
                return None

            # 解析 fulltext.md 为 items 列表
            fulltext_items = self._parse_fulltext_md(fulltext_path)
            logger.info(f"[FileService] 读取 fulltext: {len(fulltext_items)} 个元素")

            # 1.5 解析 paragraph.txt 和 table.txt 获取 id -> page/bbox 映射
            id_to_location = self._parse_location_files(output_dir)
            logger.info(f"[FileService] 读取位置信息: {len(id_to_location)} 个元素")

            # 1.6 创建 TextMatcher 用于基于文本内容的位置匹配
            text_matcher = TextMatcher.from_location_dict(
                id_to_location,
                max_edit_distance=3,
                search_steps=5
            )
            logger.info(f"[FileService] TextMatcher 已创建")

            # 1.7 创建 TableMatcher 用于表格的位置匹配
            table_matcher = TableMatcher.from_location_dict(id_to_location)
            logger.info(f"[FileService] TableMatcher 已创建，表格数: {table_matcher.get_stats()['total_tables']}")

            # 1.8 创建统一的位置获取函数
            def get_location_for_item(item: dict, current_index: int = -1) -> list:
                """
                根据元素类型获取位置信息

                对于表格 (category=="Table" 或 id 以 "t" 开头)：使用 TableMatcher
                对于 is_toc=True 的元素：使用包含匹配
                对于其他元素：使用 TextMatcher

                Args:
                    item: 元素 dict，包含 id, text, category, is_toc
                    current_index: 当前索引（已弃用，改用 ID 中的数字）

                Returns:
                    location 列表
                """
                item_id = item.get("id", "")
                item_category = item.get("category", "")
                item_text = item.get("text", "")
                is_toc = item.get("is_toc", False)

                # 判断是否为表格
                is_table = item_category == "Table" or item_id.startswith("t")

                if is_table:
                    return self._get_location_for_table(item_id, table_matcher, page_heights)
                elif is_toc:
                    # is_toc=True 的元素使用包含匹配
                    # 从 ID 中提取数字作为索引
                    id_index = -1
                    if item_id.startswith("P_"):
                        try:
                            id_index = int(item_id.replace("P_", ""))
                        except ValueError:
                            pass
                    return self._get_location_for_toc(item_text, id_to_location, page_heights, id_index)
                else:
                    # 从 ID 中提取数字作为索引（P_00051 -> 51）
                    # 这样可以正确对应 paragraph.txt 中的 p051
                    id_index = -1
                    if item_id.startswith("P_"):
                        try:
                            id_index = int(item_id.replace("P_", ""))
                        except ValueError:
                            pass
                    return self._get_location_with_text_match(item_text, text_matcher, page_heights, id_index)

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
            logger.info(f"[FileService] 标题数: {len(model_headings)}")

            # 3. 构建 id -> level 映射 和 id -> heading 映射
            heading_level_map = {h["id"]: h["level"] for h in model_headings}
            heading_text_map = {h["id"]: h["text"] for h in model_headings}
            heading_ids = set(heading_level_map.keys())

            # 4. 构建 id -> fulltext_index 映射
            id_to_index = {item["id"]: i for i, item in enumerate(fulltext_items)}

            # 5. 按 level 切分，递归构建树（包含段落内容）
            def build_tree_recursive(items_slice, parent_level=0, base_index=0):
                """
                递归构建树，将段落内容挂载到对应的标题下

                逻辑：
                1. 遍历 items_slice，遇到标题时创建节点
                2. 标题和下一个同级/上级标题之间的内容作为该标题的 children
                3. 非标题的段落直接作为叶子节点挂载

                Args:
                    items_slice: fulltext 的切片（按索引范围）
                    parent_level: 父节点的 level
                    base_index: 当前切片在原始 fulltext_items 中的起始索引

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
                pre_heading_indices = []

                for i, item in enumerate(items_slice):
                    item_id = item.get("id", "")
                    item_text = item.get("text", "")
                    is_heading = item_id in heading_ids
                    item_level = heading_level_map.get(item_id, 999)
                    global_index = base_index + i  # 在原始列表中的索引

                    # 遇到新的标题（level <= parent_level + 1），说明需要处理
                    if is_heading and item_level <= parent_level + 1:
                        # 保存之前的标题及其子内容
                        if current_heading_idx is not None:
                            prev_item = items_slice[current_heading_idx]
                            prev_id = prev_item.get("id", "")
                            prev_text = heading_text_map.get(prev_id, prev_item.get("text", ""))
                            prev_global_index = base_index + current_heading_idx

                            # 递归构建子树（包含标题之间的所有内容）
                            sub_items = items_slice[current_children_start:i]
                            sub_base_index = base_index + current_children_start
                            sub_children = build_tree_recursive(sub_items, current_heading_level, sub_base_index)

                            children.append({
                                "pid": prev_id,
                                "title": prev_text,
                                "content": prev_text,
                                "location": get_location_for_item(prev_item, prev_global_index),
                                "children": sub_children if sub_children else None
                            })
                        else:
                            # 第一个标题之前的非标题内容，作为独立节点添加
                            for pre_idx, pre_item in zip(pre_heading_indices, pre_heading_items):
                                pre_id = pre_item.get("id", "")
                                pre_text = pre_item.get("text", "")
                                children.append({
                                    "pid": pre_id,
                                    "title": "",
                                    "content": pre_text,
                                    "location": get_location_for_item(pre_item, pre_idx)
                                })
                            pre_heading_items = []
                            pre_heading_indices = []

                        # 更新当前标题
                        current_heading_idx = i
                        current_heading_level = item_level
                        current_children_start = i + 1
                    elif current_heading_idx is None:
                        # 还没遇到第一个标题，收集非标题内容
                        pre_heading_items.append(item)
                        pre_heading_indices.append(global_index)

                # 处理最后一个标题
                if current_heading_idx is not None:
                    prev_item = items_slice[current_heading_idx]
                    prev_id = prev_item.get("id", "")
                    prev_text = heading_text_map.get(prev_id, prev_item.get("text", ""))
                    prev_global_index = base_index + current_heading_idx

                    sub_items = items_slice[current_children_start:]
                    sub_base_index = base_index + current_children_start
                    sub_children = build_tree_recursive(sub_items, current_heading_level, sub_base_index)

                    children.append({
                        "pid": prev_id,
                        "title": prev_text,
                        "content": prev_text,
                        "location": get_location_for_item(prev_item, prev_global_index),
                        "children": sub_children if sub_children else None
                    })
                else:
                    # 整个 slice 没有标题，全部作为叶子节点（段落内容）
                    for i, item in enumerate(items_slice):
                        item_id = item.get("id", "")
                        item_text = item.get("text", "")
                        global_index = base_index + i
                        children.append({
                            "pid": item_id,
                            "title": "",
                            "content": item_text,
                            "location": get_location_for_item(item, global_index)
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

            logger.info(f"[FileService] 一级标题数: {len(level1_positions)}")

            # 7. 构建根节点列表
            structured_data = []

            # 处理第一个一级标题之前的内容（如果有）
            if level1_positions and level1_positions[0] > 0:
                # 文档开头有非标题内容，创建一个虚拟根节点
                pre_items = fulltext_items[:level1_positions[0]]
                for i, item in enumerate(pre_items):
                    item_id = item.get("id", "")
                    item_text = item.get("text", "")
                    structured_data.append({
                        "pid": item_id,
                        "title": "",
                        "content": item_text,
                        "location": get_location_for_item(item, i)
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
                sub_base_index = pos + 1  # 子项在原始列表中的起始索引
                sub_children = build_tree_recursive(sub_items, 1, sub_base_index)

                root_node = {
                    "pid": first_id,
                    "title": first_text,
                    "content": first_text,
                    "location": get_location_for_item(first_item, pos)
                }
                if sub_children:
                    root_node["children"] = sub_children

                structured_data.append(root_node)

            logger.info(f"[FileService] 树构建完成，根节点数: {len(structured_data)}")

            # 打印 TextMatcher 匹配统计
            match_stats = text_matcher.get_stats()
            total_matched = match_stats['exact'] + match_stats['fuzzy']
            logger.info(
                f"[FileService] TextMatcher 匹配统计: "
                f"精确匹配 {match_stats['exact']}, "
                f"模糊匹配 {match_stats['fuzzy']}, "
                f"未匹配 {match_stats['no_match']}, "
                f"总匹配 {total_matched}"
            )

            # 打印 TableMatcher 匹配统计
            table_stats = table_matcher.get_stats()
            logger.info(
                f"[FileService] TableMatcher 匹配统计: "
                f"表格匹配 {table_stats['match']}, "
                f"未匹配 {table_stats['no_match']}, "
                f"总表格数 {table_stats['total_tables']}"
            )

            # 5. 为连续的空 title 节点添加 connect_id 标识
            structured_data = self._mark_connected_empty_title_nodes(structured_data)
            logger.info(f"[FileService] 空 title 节点 connect_id 标记完成")

            # 6. 保存 _agent.json
            agent_path = output_dir / f"{file_stem}_agent.json"
            agent_path.write_text(
                json.dumps(structured_data, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            logger.info(f"[FileService] Agent JSON 已保存: {agent_path.name}")

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

            logger.info(f"[FileService] 调用 extract_onto API...")
            logger.info(f"[FileService] URL: {api_url}")

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
                logger.info(f"[FileService] extract_onto API 调用成功，耗时: {elapsed_time:.2f} 秒")

                # 保存响应到 _ontology.json
                ontology_path = output_dir / f"{file_stem}_ontology.json"
                ontology_path.write_text(
                    json.dumps(api_result, ensure_ascii=False, indent=2),
                    encoding='utf-8'
                )
                logger.info(f"[FileService] Ontology JSON 已保存: {ontology_path.name}")
                result["ontology_path"] = str(ontology_path)
            else:
                logger.info(f"[FileService] extract_onto API 调用失败: HTTP {response.status_code}")
                logger.info(f"[FileService] 响应: {response.text[:500]}")

            return result

        except requests.Timeout:
            logger.info(f"[FileService] extract_onto API 请求超时")
            return None
        except Exception as e:
            logger.info(f"[FileService] 构建文档树或调用 API 失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _mark_connected_empty_title_nodes(self, nodes: list, connect_id_counter: list = None) -> list:
        """
        为连续的空 title 节点添加相同的 connect_id 字段

        不合并节点，保持元素独立，只通过 connect_id 标识关联关系。
        连续的 title="" 且不含表格的节点会被分配相同的 connect_id。

        Args:
            nodes: 节点列表
            connect_id_counter: 计数器 [当前ID]，用于生成唯一 connect_id

        Returns:
            标记后的节点列表（元素保持独立）
        """
        if not nodes:
            return nodes

        if connect_id_counter is None:
            connect_id_counter = [0]

        for node in nodes:
            # 递归处理 children
            if "children" in node and node["children"]:
                node["children"] = self._mark_children_connected(node["children"], connect_id_counter)

        return nodes

    def _mark_children_connected(self, children: list, connect_id_counter: list) -> list:
        """
        为 children 数组中连续的空 title 节点添加 connect_id

        Args:
            children: 子节点列表
            connect_id_counter: 计数器 [当前ID]

        Returns:
            标记后的子节点列表
        """
        if not children:
            return children

        pending_group = []  # 待标记的连续空 title 节点

        for child in children:
            is_empty_title = child.get("title", "") == ""
            has_table = "<table" in child.get("content", "").lower()

            if is_empty_title and not has_table:
                # 空 title 且不含表格，加入待标记组
                pending_group.append(child)
            else:
                # 非空 title 或 含表格，先处理待标记组
                if len(pending_group) > 1:
                    # 只有多个连续节点才需要标记 connect_id
                    connect_id_counter[0] += 1
                    current_connect_id = f"C_{connect_id_counter[0]:05d}"
                    for node in pending_group:
                        node["connect_id"] = current_connect_id
                pending_group = []

                # 递归处理当前节点的 children
                if "children" in child and child["children"]:
                    child["children"] = self._mark_children_connected(child["children"], connect_id_counter)

        # 处理最后的待标记组
        if len(pending_group) > 1:
            connect_id_counter[0] += 1
            current_connect_id = f"C_{connect_id_counter[0]:05d}"
            for node in pending_group:
                node["connect_id"] = current_connect_id

        return children

    def _normalize_text(self, text: str) -> str:
        """
        标准化文本：去除空格和零宽字符

        Args:
            text: 原始文本

        Returns:
            标准化后的文本
        """
        import re
        if not text:
            return ""
        # 移除所有空白字符（空格、制表符、换行等）
        result = re.sub(r'\s+', '', text)
        # 移除零宽字符
        # U+200B: 零宽空格, U+200C: 零宽非连接符, U+200D: 零宽连接符
        # U+FEFF: 零宽非断空格(BOM), U+00AD: 软连字符
        result = re.sub(r'[\u200b\u200c\u200d\ufeff\u00ad\u2060\u180e]', '', result)
        return result

    def _parse_location_files(self, output_dir: Path) -> Dict[str, Dict[str, Any]]:
        """
        解析 paragraph.txt 和 table.txt 获取 id -> page/bbox 映射

        文件格式:
        - paragraph.txt: <p id="p001" type="P" mcid="4" page="1" bbox="x1,y1,x2,y2">文本</p>
        - table.txt: <table id="t001" type="Table" page="1" bbox="x1,y1,x2,y2">...</table>

        Args:
            output_dir: 输出目录

        Returns:
            {id: {"page": "1", "bbox": "x1,y1,x2,y2", "text": "...", "normalized_text": "..."}, ...}
        """
        import re

        id_to_location = {}
        paragraph_count = 0
        non_empty_paragraph_count = 0
        table_count = 0

        # 匹配段落: <p id="p001" ... page="1" [bbox="..."]>文本</p>
        # bbox 可选，因为 type="LI" 的列表项可能没有 bbox
        p_pattern = re.compile(r'<p\s+id="([^"]+)"[^>]*page="([^"]+)"[^>]*>([^<]*)</p>')
        bbox_pattern = re.compile(r'bbox="([^"]+)"')
        # 匹配表格: <table id="t001" ... page="1" bbox="...">
        table_pattern = re.compile(r'<table\s+id="([^"]+)"[^>]*page="([^"]+)"[^>]*bbox="([^"]+)"')

        # 解析 paragraph.txt
        paragraph_files = list(output_dir.glob("*_paragraph.txt"))
        for pf in paragraph_files:
            try:
                content = pf.read_text(encoding='utf-8')
                # 逐行解析，分别提取 id, page, bbox(可选), text
                for line in content.split('\n'):
                    match = p_pattern.search(line)
                    if match:
                        pid, page, text = match.groups()
                        # 单独提取 bbox（可选）
                        bbox_match = bbox_pattern.search(line)
                        bbox = bbox_match.group(1) if bbox_match else ""

                        normalized_text = self._normalize_text(text)
                        id_to_location[pid] = {
                            "page": page,
                            "bbox": bbox,
                            "text": text,
                            "normalized_text": normalized_text
                        }
                        paragraph_count += 1
                        # 统计非空文本段落
                        if text.strip():
                            non_empty_paragraph_count += 1
            except Exception as e:
                logger.info(f"[FileService] 解析 paragraph.txt 失败: {e}")

        # 解析 table.txt (只取表格级别的 id，如 t001)
        table_files = list(output_dir.glob("*_table.txt"))
        for tf in table_files:
            try:
                content = tf.read_text(encoding='utf-8')
                for match in table_pattern.finditer(content):
                    tid, page, bbox = match.groups()
                    id_to_location[tid] = {"page": page, "bbox": bbox}
                    table_count += 1
            except Exception as e:
                logger.info(f"[FileService] 解析 table.txt 失败: {e}")

        # 打印统计信息
        logger.info(f"[FileService] ZIP 位置信息: {paragraph_count} 个段落 (非空: {non_empty_paragraph_count}), {table_count} 个表格")

        return id_to_location

    def _build_text_location_index(self, id_to_location: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
        """
        构建标准化文本到 pid 的索引

        Args:
            id_to_location: id -> location 映射

        Returns:
            normalized_text -> pid 映射
        """
        text_to_pid = {}
        for pid, loc_info in id_to_location.items():
            if pid.startswith("p"):  # 只处理段落，不处理表格
                normalized_text = loc_info.get("normalized_text", "")
                if normalized_text:
                    text_to_pid[normalized_text] = pid
        return text_to_pid

    def _get_pid_list(self, id_to_location: Dict[str, Dict[str, Any]]) -> list:
        """
        获取按顺序排列的段落 pid 列表

        Args:
            id_to_location: id -> location 映射

        Returns:
            排序后的 pid 列表
        """
        pids = [pid for pid in id_to_location.keys() if pid.startswith("p")]
        # 按数字排序: p001, p002, ...
        pids.sort(key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)
        return pids

    def _edit_distance(self, s1: str, s2: str, max_distance: int = 3) -> int:
        """
        计算两个字符串的编辑距离（Levenshtein 距离）

        带有早期终止优化：如果距离超过 max_distance，立即返回 max_distance + 1

        Args:
            s1: 字符串1
            s2: 字符串2
            max_distance: 最大距离阈值

        Returns:
            编辑距离，如果超过 max_distance 返回 max_distance + 1
        """
        if abs(len(s1) - len(s2)) > max_distance:
            return max_distance + 1

        if len(s1) > len(s2):
            s1, s2 = s2, s1

        if len(s1) == 0:
            return len(s2) if len(s2) <= max_distance else max_distance + 1

        previous_row = list(range(len(s1) + 1))

        for i, c2 in enumerate(s2):
            current_row = [i + 1]
            min_in_row = i + 1

            for j, c1 in enumerate(s1):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                cell = min(insertions, deletions, substitutions)
                current_row.append(cell)
                min_in_row = min(min_in_row, cell)

            # 早期终止
            if min_in_row > max_distance:
                return max_distance + 1

            previous_row = current_row

        return previous_row[-1] if previous_row[-1] <= max_distance else max_distance + 1

    def _find_location_by_text(
        self,
        item_text: str,
        id_to_location: Dict[str, Dict[str, Any]],
        text_to_pid: Dict[str, str],
        pid_list: list,
        current_index_hint: int = -1,
        max_edit_distance: int = 3,
        search_steps: int = 5
    ) -> Optional[str]:
        """
        通过文本内容查找对应的 pid

        查找策略：
        1. 首先精确匹配标准化文本
        2. 如果找不到，从 current_index_hint 向两侧查找编辑距离在 max_edit_distance 以内的段落

        Args:
            item_text: 要查找的文本
            id_to_location: id -> location 映射
            text_to_pid: normalized_text -> pid 映射
            pid_list: 按顺序排列的 pid 列表
            current_index_hint: 当前位置提示（用于确定搜索范围）
            max_edit_distance: 最大编辑距离
            search_steps: 两侧各搜索的步数

        Returns:
            匹配到的 pid，如果没找到返回 None
        """
        normalized_text = self._normalize_text(item_text)
        if not normalized_text:
            return None

        # 1. 精确匹配
        if normalized_text in text_to_pid:
            return text_to_pid[normalized_text]

        # 2. 模糊匹配：从 current_index_hint 向两侧搜索
        if current_index_hint < 0 or not pid_list:
            return None

        # 确定搜索范围
        start_left = max(0, current_index_hint - search_steps)
        end_right = min(len(pid_list), current_index_hint + search_steps + 1)

        best_match = None
        best_distance = max_edit_distance + 1

        # 向两侧搜索
        for i in range(start_left, end_right):
            pid = pid_list[i]
            loc_info = id_to_location.get(pid, {})
            candidate_text = loc_info.get("normalized_text", "")

            if not candidate_text:
                continue

            distance = self._edit_distance(normalized_text, candidate_text, max_edit_distance)
            if distance <= max_edit_distance and distance < best_distance:
                best_distance = distance
                best_match = pid

        return best_match

    def _extract_page_heights_from_pdf(self, pdf_path: Path) -> Dict[int, float]:
        """
        从 PDF 文件中提取每页的高度

        Args:
            pdf_path: PDF 文件路径

        Returns:
            页码到页面高度的映射: {1: 841.89, 2: 841.89, ...}
        """
        page_heights = {}

        try:
            import fitz  # pymupdf

            doc = fitz.open(str(pdf_path))
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                rect = page.rect
                # 页码从 1 开始
                page_heights[page_idx + 1] = rect.height
            doc.close()

            logger.info(f"[FileService] 提取 PDF 页面高度: {len(page_heights)} 页")

        except ImportError:
            logger.info(f"[FileService] 警告: pymupdf 未安装，无法提取页面高度")
        except Exception as e:
            logger.info(f"[FileService] 提取页面高度失败: {e}")

        return page_heights

    def _get_location_for_id(
        self,
        item_id: str,
        id_to_location: Dict[str, Dict[str, Any]],
        page_heights: Optional[Dict[int, float]] = None
    ) -> list:
        """
        根据 id 获取 location 列表，统一为 l,t,r,b 格式，并转换为 TOPLEFT 坐标系

        输入 bbox 格式 (PDF用户空间，左下角原点):
            [x0, y0, x1, y1]
            - x0: 左边界
            - y0: 底部 (y值较小)
            - x1: 右边界
            - y1: 顶部 (y值较大)

        输出格式 (TOPLEFT 坐标系，左上角原点):
            {"page": 1, "l": x0, "t": new_t, "r": x1, "b": new_b, "coord_origin": "TOPLEFT"}
            - l: 左边界 = x0
            - r: 右边界 = x1
            - t: 顶部 = page_height - y1 (转换后，值小表示位置高)
            - b: 底部 = page_height - y0 (转换后，值大表示位置低)

        Args:
            item_id: 元素 ID (如 P_00001, t001)
            id_to_location: id -> page/bbox 映射
            page_heights: 页码 -> 页面高度映射，用于坐标系转换

        Returns:
            location 列表: [{"page": 1, "l": ..., "t": ..., "r": ..., "b": ..., "coord_origin": "TOPLEFT"}, ...]
        """
        # 尝试直接匹配
        loc_info = id_to_location.get(item_id)

        # 如果是 P_00001 格式，尝试转换为 p001 格式
        if not loc_info and item_id.startswith("P_"):
            # P_00001 -> p001
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

        # 处理跨页情况: page="1|2" bbox="x0,y0,x1,y1|x0,y0,x1,y1"
        pages = page_str.split("|")
        bboxes = bbox_str.split("|")

        locations = []
        for i, page in enumerate(pages):
            try:
                page_num = int(page)
                bbox_coords = [float(x) for x in bboxes[i].split(",")] if i < len(bboxes) else []

                if len(bbox_coords) >= 4:
                    # 原始坐标 (PDF用户空间，左下角原点)
                    x0, y0, x1, y1 = bbox_coords[0], bbox_coords[1], bbox_coords[2], bbox_coords[3]

                    # 获取页面高度
                    page_height = page_heights.get(page_num) if page_heights else None

                    if page_height:
                        # 转换为 TOPLEFT 坐标系
                        # y' = page_height - y
                        # 原 y1 (顶部，值大) -> 新 t (值小，表示距顶部近)
                        # 原 y0 (底部，值小) -> 新 b (值大，表示距顶部远)
                        new_t = round(page_height - y1, 4)
                        new_b = round(page_height - y0, 4)

                        locations.append({
                            "page": page_num,
                            "l": round(x0, 4),
                            "t": new_t,
                            "r": round(x1, 4),
                            "b": new_b,
                            "coord_origin": "TOPLEFT"
                        })
                    else:
                        # 没有页面高度，保持原始坐标但标记为 BOTTOMLEFT
                        locations.append({
                            "page": page_num,
                            "l": round(x0, 4),
                            "t": round(y1, 4),  # 原 y1 是顶部
                            "r": round(x1, 4),
                            "b": round(y0, 4),  # 原 y0 是底部
                            "coord_origin": "BOTTOMLEFT"
                        })
                else:
                    # bbox 不完整，跳过
                    continue

            except (ValueError, IndexError):
                continue

        return locations

    def _get_location_with_text_match(
        self,
        item_text: str,
        text_matcher: TextMatcher,
        page_heights: Optional[Dict[int, float]] = None,
        current_index: int = -1
    ) -> list:
        """
        使用 TextMatcher 根据文本内容获取位置信息

        查找策略：
        1. 精确匹配：标准化文本完全相同
        2. 模糊匹配：从当前位置向两侧搜索（编辑距离）

        Args:
            item_text: 元素文本内容
            text_matcher: TextMatcher 实例
            page_heights: 页码 -> 页面高度映射
            current_index: 当前索引（用于模糊匹配范围）

        Returns:
            location 列表
        """
        # 使用 TextMatcher 查找匹配
        matched_pid, loc_info = text_matcher.find_match(
            text=item_text,
            current_index=current_index
        )

        if not matched_pid or not loc_info:
            return []

        # 获取位置信息并转换坐标系
        page_str = loc_info.get("page", "")
        bbox_str = loc_info.get("bbox", "")

        if not page_str or not bbox_str:
            return []

        # 处理跨页情况: page="1|2" bbox="x0,y0,x1,y1|x0,y0,x1,y1"
        pages = page_str.split("|")
        bboxes = bbox_str.split("|")

        locations = []
        for i, page in enumerate(pages):
            try:
                page_num = int(page)
                bbox_coords = [float(x) for x in bboxes[i].split(",")] if i < len(bboxes) else []

                if len(bbox_coords) >= 4:
                    x0, y0, x1, y1 = bbox_coords[0], bbox_coords[1], bbox_coords[2], bbox_coords[3]

                    page_height = page_heights.get(page_num) if page_heights else None

                    if page_height:
                        new_t = round(page_height - y1, 4)
                        new_b = round(page_height - y0, 4)

                        locations.append({
                            "page": page_num,
                            "l": round(x0, 4),
                            "t": new_t,
                            "r": round(x1, 4),
                            "b": new_b,
                            "coord_origin": "TOPLEFT"
                        })
                    else:
                        locations.append({
                            "page": page_num,
                            "l": round(x0, 4),
                            "t": round(y1, 4),
                            "r": round(x1, 4),
                            "b": round(y0, 4),
                            "coord_origin": "BOTTOMLEFT"
                        })
            except (ValueError, IndexError):
                continue

        return locations

    def _get_location_for_table(
        self,
        table_id: str,
        table_matcher: TableMatcher,
        page_heights: Optional[Dict[int, float]] = None
    ) -> list:
        """
        使用 TableMatcher 根据表格 ID 获取位置信息

        Args:
            table_id: 表格 ID (如 t001)
            table_matcher: TableMatcher 实例
            page_heights: 页码 -> 页面高度映射

        Returns:
            location 列表
        """
        loc_info = table_matcher.find_match(table_id)

        if not loc_info:
            return []

        page_str = loc_info.get("page", "")
        bbox_str = loc_info.get("bbox", "")

        if not page_str or not bbox_str:
            return []

        # 处理跨页情况: page="1|2" bbox="x0,y0,x1,y1|x0,y0,x1,y1"
        pages = page_str.split("|")
        bboxes = bbox_str.split("|")

        locations = []
        for i, page in enumerate(pages):
            try:
                page_num = int(page)
                bbox_coords = [float(x) for x in bboxes[i].split(",")] if i < len(bboxes) else []

                if len(bbox_coords) >= 4:
                    x0, y0, x1, y1 = bbox_coords[0], bbox_coords[1], bbox_coords[2], bbox_coords[3]

                    page_height = page_heights.get(page_num) if page_heights else None

                    if page_height:
                        new_t = round(page_height - y1, 4)
                        new_b = round(page_height - y0, 4)

                        locations.append({
                            "page": page_num,
                            "l": round(x0, 4),
                            "t": new_t,
                            "r": round(x1, 4),
                            "b": new_b,
                            "coord_origin": "TOPLEFT"
                        })
                    else:
                        locations.append({
                            "page": page_num,
                            "l": round(x0, 4),
                            "t": round(y1, 4),
                            "r": round(x1, 4),
                            "b": round(y0, 4),
                            "coord_origin": "BOTTOMLEFT"
                        })
            except (ValueError, IndexError):
                continue

        return locations

    def _get_location_for_toc(
        self,
        item_text: str,
        id_to_location: Dict[str, Dict[str, Any]],
        page_heights: Optional[Dict[int, float]] = None,
        current_index: int = -1,
        search_steps: int = 10
    ) -> list:
        """
        为 is_toc=True 的元素获取位置信息（使用包含匹配）

        is_toc 元素的文本格式通常是 "标题文本	页码"（如 "二、技术要求	31"）
        PDF 中的文本可能只有 "二、技术要求" 或者 "二、技术要求31"

        匹配策略：
        1. 从 item_text 中提取标题部分（去掉页码）
        2. 根据 pid 向两侧搜索 paragraph.txt 中的内容
        3. 如果 pdf 读取的文本包含 unstructured 的标题文本，就取对应的 page 和 bbox

        Args:
            item_text: is_toc 元素的文本（如 "二、技术要求	31"）
            id_to_location: id -> page/bbox 映射
            page_heights: 页码 -> 页面高度映射
            current_index: 当前索引位置（用于向两侧搜索）
            search_steps: 两侧各搜索的步数

        Returns:
            location 列表
        """
        import re

        if not item_text:
            return []

        # 1. 提取标题部分（去掉页码）
        # 目录条目格式: "标题文本\t页码" 或 "标题文本    页码" 或 "标题文本……页码"
        # 使用正则匹配：去掉末尾的数字（页码）和前面的 tab/空格/点
        title_text = re.sub(r'[\t\s…\.]+\d+\s*$', '', item_text).strip()
        if not title_text:
            title_text = item_text.strip()

        # 标准化标题文本（去掉空格和零宽字符）
        normalized_title = normalize_text(title_text)
        if not normalized_title:
            return []

        # 2. 获取按顺序排列的 pid 列表
        pids = [pid for pid in id_to_location.keys() if pid.startswith("p")]
        pids.sort(key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)

        if not pids:
            return []

        # 3. 确定搜索范围
        if current_index < 0:
            current_index = 0
        start_left = max(0, current_index - search_steps)
        end_right = min(len(pids), current_index + search_steps + 1)

        # 4. 向两侧搜索，使用包含匹配
        for i in range(start_left, end_right):
            pid = pids[i]
            loc_info = id_to_location.get(pid, {})
            candidate_text = loc_info.get("normalized_text", "")

            if not candidate_text:
                continue

            # 包含匹配：PDF 的文本包含 unstructured 的标题，或反过来
            if normalized_title in candidate_text or candidate_text in normalized_title:
                # 找到匹配，获取位置信息并转换坐标系
                page_str = loc_info.get("page", "")
                bbox_str = loc_info.get("bbox", "")

                if not page_str or not bbox_str:
                    continue

                # 处理跨页情况
                pages = page_str.split("|")
                bboxes = bbox_str.split("|")

                locations = []
                for j, page in enumerate(pages):
                    try:
                        page_num = int(page)
                        bbox_coords = [float(x) for x in bboxes[j].split(",")] if j < len(bboxes) else []

                        if len(bbox_coords) >= 4:
                            x0, y0, x1, y1 = bbox_coords[0], bbox_coords[1], bbox_coords[2], bbox_coords[3]

                            page_height = page_heights.get(page_num) if page_heights else None

                            if page_height:
                                new_t = round(page_height - y1, 4)
                                new_b = round(page_height - y0, 4)

                                locations.append({
                                    "page": page_num,
                                    "l": round(x0, 4),
                                    "t": new_t,
                                    "r": round(x1, 4),
                                    "b": new_b,
                                    "coord_origin": "TOPLEFT"
                                })
                            else:
                                locations.append({
                                    "page": page_num,
                                    "l": round(x0, 4),
                                    "t": round(y1, 4),
                                    "r": round(x1, 4),
                                    "b": round(y0, 4),
                                    "coord_origin": "BOTTOMLEFT"
                                })
                    except (ValueError, IndexError):
                        continue

                if locations:
                    return locations

        # 没有找到匹配
        return []

    def _parse_fulltext_md(self, fulltext_path: Path) -> list:
        """
        解析 fulltext.md 文件为 items 列表

        fulltext.md 格式:
        - # [category] 标题文本 {id=P_00001, ...}  -> 标题候选项
        - - [category] 段落文本 {id=P_00002, ...}  -> 普通段落
        - [Table] t001                            -> 表格
          <table>...</table>

        toc_level 目录层级对应关系:
        - toc_level: 0 → TOC Heading（目录标题："目  录"）
        - toc_level: 1 → toc 1（一级目录：第一章、第二章...）
        - toc_level: 2 → toc 2（二级目录：第1节、技术要求...）
        - toc_level: 3 → toc 3（三级目录：一、二、三...）

        Args:
            fulltext_path: fulltext.md 文件路径

        Returns:
            items 列表，每个元素: {"id": "P_00001", "text": "...", "category": "...", "is_toc": bool, "toc_level": int|None}
        """
        import re

        content = fulltext_path.read_text(encoding='utf-8')
        lines = content.split('\n')

        items = []
        id_pattern = re.compile(r'\{id=([^},]+)')
        category_pattern = re.compile(r'\[([^\]]+)\]')
        is_toc_pattern = re.compile(r'is_toc=true')
        toc_level_pattern = re.compile(r'toc_level=(\d+)')

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
                    "category": "Table",
                    "is_toc": False
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

                # 检查 is_toc 标记和 toc_level
                is_toc = bool(is_toc_pattern.search(line))
                toc_level = None
                toc_level_match = toc_level_pattern.search(line)
                if toc_level_match:
                    toc_level = int(toc_level_match.group(1))

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
                    item = {
                        "id": item_id,
                        "text": text,
                        "category": category,
                        "is_toc": is_toc
                    }
                    if toc_level is not None:
                        item["toc_level"] = toc_level
                    items.append(item)

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
                logger.info(f"[FileService] Task {task_id} status updated to {status} (local)")
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
                        logger.info(f"[FileService] Task {task_id} status updated to {status} (mysql)")

        except Exception as e:
            logger.info(f"[FileService] Failed to update task status: {e}")
            import traceback
            traceback.print_exc()


# 全局服务实例
_file_service = None


def _process_file_in_subprocess(
    file_path: Path,
    file_type: str,
    task_id: str,
    db_task_id: Optional[int],
    output_dir: Path
):
    """
    子进程入口函数

    multiprocessing.Process 不能直接调用实例方法，所以需要这个模块级函数。
    子进程独立于主进程，主进程热更新不影响已启动的子进程。

    Args:
        file_path: 文件路径
        file_type: 文件类型
        task_id: 任务 ID
        db_task_id: 数据库任务 ID
        output_dir: 输出目录
    """
    # 在子进程中创建新的服务实例
    service = FileService()
    service._process_file_sync(file_path, file_type, task_id, db_task_id, output_dir)


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
    logger.info(f"[FileService] 文件处理测试")
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
