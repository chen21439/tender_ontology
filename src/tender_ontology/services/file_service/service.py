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
            if pdf_result:
                artifacts["docx_pdf"] = pdf_result
                artifacts["pdf_path"] = pdf_result.get("pdf_path", "")
                print(f"[FileService] DOCX 转 PDF 完成: {pdf_result.get('pdf_path', '')}")

            # 处理 Unstructured 结果
            print(f"[FileService] Unstructured 提取完成")

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

            # 从配置获取服务地址（如果没有配置，使用默认值）
            base_url = getattr(settings, 'docx_pdf_service_url', 'http://localhost:8080')

            print(f"[FileService] 调用 DOCX 转 PDF 服务: {base_url}")

            client = DocxPdfClient(
                base_url=base_url,
                timeout=120.0,
                verbose=True
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
