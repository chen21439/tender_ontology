"""
Docling 后台任务处理

用于异步处理 PDF 推理任务
"""

import threading
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import json
import requests

from tender_ontology.services.docling import DoclingInferenceService


class DoclingBackgroundTask:
    """Docling 后台任务处理器"""

    def __init__(self):
        """初始化后台任务处理器"""
        self.docling_service = DoclingInferenceService(
            offline_mode=True,
            disable_table_recognition=True  # 默认快速模式
        )

    def process_pdf_sync(
        self,
        pdf_path: Path,
        task_id: str,
        db_task_id: Optional[int] = None,
        output_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        异步处理 PDF 文件

        Args:
            pdf_path: PDF 文件路径
            task_id: 任务 ID
            db_task_id: 数据库任务 ID（用于更新状态）
            output_dir: 输出目录（可选，默认使用配置中的目录）

        Returns:
            处理结果
        """
        print(f"[Docling Task] ========== Start ==========")
        print(f"[Docling Task] Task ID: {task_id}")
        print(f"[Docling Task] PDF: {pdf_path}")
        print(f"[Docling Task] DB Task ID: {db_task_id}")
        print(f"[Docling Task] ================================")

        try:
            # 1. 更新状态为"处理中"
            if db_task_id:
                self._update_task_status(
                    db_task_id,
                    status=3,  # 解析中
                    message="Docling 推理中..."
                )

            # 2. 直接运行 Docling 推理（传递输出目录）
            results = self._run_docling_inference(pdf_path, task_id, output_dir)

            print(f"[Docling Task] Inference completed in {results['total_time']:.2f}s")
            print(f"[Docling Task] Generated files:")
            print(f"  - Markdown: {results.get('markdown_path', 'N/A')}")
            print(f"  - JSON: {results.get('json_path', 'N/A')}")
            print(f"  - Labeled JSON: {results.get('labeled_path', 'N/A')}")
            print(f"  - Headers JSON: {results.get('headers_path', 'N/A')}")

            # 3. 读取生成的文件内容
            artifacts = self._collect_artifacts(results)

            # 3.5 并行调用两个千问 API
            fulltext_data = None
            if "fulltext_path" in results:
                fulltext_path = Path(results["fulltext_path"])
                fulltext_data = json.loads(fulltext_path.read_text(encoding='utf-8'))
                header_count = sum(1 for item in fulltext_data if item.get("label") == "section_header")
                print(f"[Docling Task] fulltext.json 中共有 {header_count} 个标题")

            # 调用千问 API
            if fulltext_data and "title_md_path" in results:
                print(f"[Docling Task] 开始调用千问 API...")

                # 调用1：提取所有标题层级（暂时禁用，恢复时取消注释即可）
                # try:
                #     result_data = self._extract_all_headings(
                #         results["title_md_path"],
                #         header_count,
                #         fulltext_data
                #     )
                #     if result_data:
                #         artifacts.update(result_data)
                # except Exception as e:
                #     print(f"[Docling Task] 千问调用异常: {e}")
                #     import traceback
                #     traceback.print_exc()

                # 调用2：两阶段标题提取（使用内部qwen3-32b API）
                if "header_only_path" in results and "title_md_path" in results:
                    try:
                        result_data = self._extract_level12_headings(
                            results["header_only_path"],
                            results["title_md_path"],
                            fulltext_data
                        )
                        if result_data:
                            artifacts.update(result_data)
                    except Exception as e:
                        print(f"[Docling Task] 千问调用2异常: {e}")
                        import traceback
                        traceback.print_exc()

                print(f"[Docling Task] 千问 API 调用完成")

            # 4. 更新数据库状态为"完成"
            if db_task_id:
                self._update_task_status(
                    db_task_id,
                    status=2,  # 完成
                    message="Docling 推理完成",
                    artifacts=artifacts
                )

            return {
                "success": True,
                "task_id": task_id,
                "inference_time": results["total_time"],
                "artifacts": artifacts
            }

        except Exception as e:
            print(f"[Docling Task] Error: {e}")
            import traceback
            traceback.print_exc()

            # 更新状态为"失败"
            if db_task_id:
                self._update_task_status(
                    db_task_id,
                    status=4,  # 失败
                    message=f"Docling 推理失败: {str(e)}"
                )

            return {
                "success": False,
                "task_id": task_id,
                "error": str(e)
            }

    def _run_docling_inference(
        self,
        pdf_path: Path,
        task_id: str,
        output_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        运行 Docling 推理（同步方法，在线程池中执行）

        Args:
            pdf_path: PDF 文件路径
            task_id: 任务 ID
            output_dir: 输出目录（可选）

        Returns:
            推理结果
        """
        # 如果指定了输出目录，创建新的 service 实例
        if output_dir:
            service = DoclingInferenceService(
                output_dir=output_dir,
                offline_mode=True,
                disable_table_recognition=True
            )
            results = service.infer(
                file_path=pdf_path,
                save_markdown=True,
                save_json=True,
                save_labeled=True,
                save_headers=True,
                save_markdown_json=True,
                save_fulltext=True,
                save_doctags=False
            )
        else:
            # 使用默认的 service 实例
            results = self.docling_service.infer(
                file_path=pdf_path,
                save_markdown=True,
                save_json=True,
                save_labeled=True,
                save_headers=True,
                save_doctags=False
            )
        return results

    def _extract_all_headings(
        self,
        title_md_path: str,
        header_count: int,
        fulltext_data: list
    ) -> Optional[Dict[str, Any]]:
        """
        提取所有标题层级（千问调用1）

        Args:
            title_md_path: title_with_id.md 文件路径
            header_count: 标题数量
            fulltext_data: fulltext 数据

        Returns:
            artifacts 字典
        """
        try:
            from .qwen_heading_extractor import QwenDirectExtractor

            print(f"[Qwen API 1] 开始提取所有标题层级...")

            extractor = QwenDirectExtractor()
            qwen_headings = extractor.extract_headings(
                title_md_path,
                header_count=header_count,
                verbose=True
            )
            print(f"[Qwen API 1] 提取完成，共 {len(qwen_headings)} 个标题")

            # 填充位置信息
            extractor.enrich_headings_with_location(qwen_headings, fulltext_data, verbose=True)

            # 保存结果
            title_md_path = Path(title_md_path)
            base_name = title_md_path.stem.replace('_title_with_id', '')
            output_dir = title_md_path.parent

            artifacts = {}

            # 保存 _model.json
            model_json_path = output_dir / f"{base_name}_model.json"
            model_json_path.write_text(
                json.dumps(qwen_headings, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            print(f"[Qwen API 1] 模型标题已保存: {model_json_path.name}")
            artifacts["model"] = {
                "path": str(model_json_path),
                "total_headings": len(qwen_headings)
            }

            # 构建文档树
            print(f"[Qwen API 1] 开始构建文档层级树...")
            tree_result = self._build_document_tree(qwen_headings, fulltext_data)

            if tree_result:
                # 保存 _tree.json
                tree_json_path = output_dir / f"{base_name}_tree.json"
                tree_json_path.write_text(
                    json.dumps(tree_result, ensure_ascii=False, indent=2),
                    encoding='utf-8'
                )
                print(f"[Qwen API 1] 文档树已保存: {tree_json_path.name}")
                artifacts["tree"] = {
                    "path": str(tree_json_path),
                    "summary": tree_result["summary"]
                }

                # 保存 _forward.json
                if "artifact" in tree_result:
                    forward_json_path = output_dir / f"{base_name}_forward.json"
                    forward_json_path.write_text(
                        json.dumps(tree_result["artifact"], ensure_ascii=False, indent=2),
                        encoding='utf-8'
                    )
                    print(f"[Qwen API 1] Forward JSON 已保存: {forward_json_path.name}")
                    artifacts["forward"] = {"path": str(forward_json_path)}

            return artifacts

        except Exception as e:
            print(f"[Qwen API 1] 提取失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _extract_level12_headings(
        self,
        header_only_path: str,
        title_md_path: str,
        fulltext_data: list
    ) -> Optional[Dict[str, Any]]:
        """
        两阶段标题提取（千问调用2，使用内部qwen3-32b API）

        阶段1：提取一二级标题（volume/chapter）
        阶段2：并发提取各章节内的子标题，聚合后构建完整树

        Args:
            header_only_path: sectionHeader_only.md 文件路径
            title_md_path: title_with_id.md 文件路径
            fulltext_data: fulltext 数据

        Returns:
            artifacts 字典
        """
        try:
            from .qwen_heading_extractor_file import QwenHeadingExtractor
            import re
            import time

            total_start = time.time()
            print(f"[Qwen API 2] 开始两阶段标题提取...")

            extractor = QwenHeadingExtractor()

            # ========== 阶段1：提取一二级标题 ==========
            stage1_start = time.time()
            print(f"[Qwen API 2] 阶段1：提取一二级标题...")
            level12_headings = extractor.extract_headings_internal(
                header_only_path,
                header_count=0,
                verbose=True,
                save_response=True
            )
            stage1_time = time.time() - stage1_start
            print(f"[Qwen API 2] 阶段1完成，共 {len(level12_headings)} 个标题，耗时: {stage1_time:.2f} 秒")

            # 保存一阶段结果
            header_only_path = Path(header_only_path)
            base_name = header_only_path.stem.replace('_sectionHeader_only', '')
            output_dir = header_only_path.parent

            level12_json_path = output_dir / f"{base_name}_level12.json"
            level12_json_path.write_text(
                json.dumps(level12_headings, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            print(f"[Qwen API 2] 一二级标题已保存: {level12_json_path.name}")

            artifacts = {
                "level12": {
                    "path": str(level12_json_path),
                    "total_headings": len(level12_headings)
                }
            }

            # ========== 阶段2：并发提取章节内子标题 ==========
            # 筛选出 chapter 标题（一阶段模型已标记 type=chapter）
            chapter_headings = [
                h for h in level12_headings
                if h.get("type") == "chapter"
            ]

            if chapter_headings:
                stage2_start = time.time()
                print(f"[Qwen API 2] 阶段2：并发提取 {len(chapter_headings)} 个章节的子标题...")

                chapter_results = extractor.extract_headings_by_chapters(
                    title_md_path,
                    chapter_headings,
                    max_workers=8,
                    verbose=True,
                    save_responses=False
                )

                # ========== 聚合结果（复用 extractor 的方法） ==========
                all_headings = extractor.merge_stage2_results(
                    level12_headings,
                    chapter_results,
                    verbose=True
                )
                stage2_time = time.time() - stage2_start
                print(f"[Qwen API 2] 阶段2完成，聚合后共 {len(all_headings)} 个标题，耗时: {stage2_time:.2f} 秒")

                # 填充位置信息
                extractor.enrich_headings_with_location(all_headings, fulltext_data, verbose=True)

                # 保存聚合后的标题
                agent_headings_path = output_dir / f"{base_name}_agent_headings.json"
                agent_headings_path.write_text(
                    json.dumps(all_headings, ensure_ascii=False, indent=2),
                    encoding='utf-8'
                )
                print(f"[Qwen API 2] 聚合标题已保存: {agent_headings_path.name}")

                # ========== 构建文档树（复用 extractor 的方法） ==========
                print(f"[Qwen API 2] 开始构建文档层级树...")
                tree_result = extractor.build_document_tree(all_headings, fulltext_data, verbose=True)

                if tree_result:
                    # 保存 _agent_tree.json
                    tree_json_path = output_dir / f"{base_name}_agent_tree.json"
                    tree_json_path.write_text(
                        json.dumps(tree_result, ensure_ascii=False, indent=2),
                        encoding='utf-8'
                    )
                    print(f"[Qwen API 2] 文档树已保存: {tree_json_path.name}")
                    artifacts["agent_tree"] = {
                        "path": str(tree_json_path),
                        "summary": tree_result["summary"]
                    }

                    # 保存 _agent.json（和 _forward.json 格式相同）
                    if "artifact" in tree_result:
                        agent_json_path = output_dir / f"{base_name}_agent.json"
                        agent_json_path.write_text(
                            json.dumps(tree_result["artifact"], ensure_ascii=False, indent=2),
                            encoding='utf-8'
                        )
                        print(f"[Qwen API 2] Agent JSON 已保存: {agent_json_path.name}")
                        artifacts["agent"] = {"path": str(agent_json_path)}

                        # 调用 extract_onto API 上报结构化数据
                        print(f"[Qwen API 2] 准备调用 extract_onto API...")
                        try:
                            self._call_extract_onto_api(
                                task_id=output_dir.name,  # task_id 是目录名
                                pdf_path=output_dir,  # 用于构建 pdf_url
                                structured_data=tree_result["artifact"]
                            )
                        except Exception as api_e:
                            print(f"[Qwen API 2] extract_onto API 调用异常: {api_e}")
                            import traceback
                            traceback.print_exc()

                # 打印耗时统计
                total_time = time.time() - total_start
                print(f"\n{'=' * 60}")
                print(f"[Qwen API 2] 两阶段标题提取完成！")
                print(f"{'=' * 60}")
                print(f"[耗时统计]")
                print(f"  - 阶段1 (一二级标题提取): {stage1_time:.2f} 秒")
                print(f"  - 阶段2 (章节并发重建+聚合): {stage2_time:.2f} 秒")
                print(f"  - 总耗时: {total_time:.2f} 秒")
                print(f"{'=' * 60}")

            return artifacts

        except Exception as e:
            print(f"[Qwen API 2] 提取失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _call_extract_onto_api(
        self,
        task_id: str,
        pdf_path: Path,
        structured_data: list
    ) -> Optional[Dict[str, Any]]:
        """
        调用 extract_onto API 上报结构化数据

        Args:
            task_id: 任务 ID
            pdf_path: PDF 文件所在目录（用于保存响应）
            structured_data: agent.json 的内容（结构化数据列表）

        Returns:
            API 响应或 None（如果调用失败）
        """
        import time

        try:
            from tender_ontology.config.settings import settings

            # 构建请求数据
            request_data = {
                "task_id": task_id,
                "pdf_url": "",
                "document_type": "",
                "region": "",
                "structured_data": structured_data
            }

            print(f"[Extract Onto API] 开始调用 API...")
            print(f"[Extract Onto API] URL: {settings.tender_extract_api_url}")
            print(f"[Extract Onto API] task_id: {task_id}")
            print(f"[Extract Onto API] structured_data 条数: {len(structured_data)}")

            # 发送请求（带耗时统计）
            start_time = time.time()
            response = requests.post(
                settings.tender_extract_api_url,
                json=request_data,
                headers={"Content-Type": "application/json"},
                timeout=settings.tender_extract_api_timeout
            )
            elapsed_time = time.time() - start_time

            # 检查响应
            if response.status_code == 200:
                result = response.json()
                print(f"[Extract Onto API] 调用成功，耗时: {elapsed_time:.2f} 秒")

                # 保存响应到 _ontology.json
                if isinstance(pdf_path, Path) and pdf_path.exists():
                    # 查找基础文件名
                    agent_files = list(pdf_path.glob("*_agent.json"))
                    if agent_files:
                        base_name = agent_files[0].stem.replace('_agent', '')
                        ontology_path = pdf_path / f"{base_name}_ontology.json"
                    else:
                        ontology_path = pdf_path / f"{task_id}_ontology.json"

                    ontology_path.write_text(
                        json.dumps(result, ensure_ascii=False, indent=2),
                        encoding='utf-8'
                    )
                    print(f"[Extract Onto API] 响应已保存: {ontology_path.name}")

                return result
            else:
                print(f"[Extract Onto API] 调用失败: HTTP {response.status_code}，耗时: {elapsed_time:.2f} 秒")
                print(f"[Extract Onto API] 响应内容: {response.text[:500]}")
                return None

        except requests.Timeout:
            print(f"[Extract Onto API] 请求超时（{settings.tender_extract_api_timeout}秒）")
            return None
        except requests.RequestException as e:
            print(f"[Extract Onto API] 请求异常: {e}")
            return None
        except Exception as e:
            print(f"[Extract Onto API] 调用失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _build_document_tree(
        self,
        model_headings: list,
        fulltext_data: list
    ) -> Optional[Dict[str, Any]]:
        """
        使用 LevelTreeConstructor 构建文档层级树

        Args:
            model_headings: 千问返回的标题列表（带 level）
            fulltext_data: docling fulltext 数据（按阅读顺序）

        Returns:
            树结构和统计信息
        """
        try:
            from tender_ontology.utils.document_struct.tree import LevelTreeConstructor

            constructor = LevelTreeConstructor(verbose=True)
            result = constructor.build_tree(model_headings, fulltext_data)

            # 打印树结构预览（只显示标题）
            constructor.print_tree(max_depth=4, show_non_headers=False)

            return result
        except Exception as e:
            print(f"[Docling Task] 构建文档树失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _collect_artifacts(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        收集生成的文件内容

        Args:
            results: Docling 推理结果

        Returns:
            文件内容字典
        """
        artifacts = {}

        # 读取 Headers JSON
        if "headers_path" in results:
            try:
                headers_path = Path(results["headers_path"])
                headers_data = json.loads(headers_path.read_text(encoding='utf-8'))
                artifacts["headers"] = {
                    "path": str(headers_path),
                    "total_headers": headers_data.get("total_headers", 0),
                    "headers": headers_data.get("headers", [])
                }
            except Exception as e:
                print(f"[Docling Task] Failed to read headers: {e}")

        # 读取 Labeled JSON 统计信息
        if "labeled_path" in results:
            try:
                labeled_path = Path(results["labeled_path"])
                labeled_data = json.loads(labeled_path.read_text(encoding='utf-8'))
                artifacts["labeled"] = {
                    "path": str(labeled_path),
                    "total_items": labeled_data.get("total_items", 0)
                }
            except Exception as e:
                print(f"[Docling Task] Failed to read labeled: {e}")

        # 添加其他文件路径
        for key in ["markdown_path", "json_path"]:
            if key in results:
                artifacts[key.replace("_path", "")] = {
                    "path": results[key]
                }

        return artifacts

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
            status: 状态码
                - 1: 待审查
                - 2: 审查完成
                - 3: 解析中
                - 4: 解析失败
            message: 状态消息
            artifacts: 生成的文件信息
        """
        try:
            from tender_ontology.utils.db.local_storage import is_local_mode, get_local_storage

            if is_local_mode():
                # 本地存储模式
                storage = get_local_storage()
                storage.update_task_status(task_id, status, message)
                print(f"[Docling Task] Task {task_id} status updated to {status} (local)")

                # 打印 artifacts 信息
                if artifacts and status == 2:
                    print(f"[Docling Task] Artifacts generated:")
                    print(f"  - Headers: {artifacts.get('headers', {}).get('total_headers', 0)} items")
                    print(f"  - Labeled: {artifacts.get('labeled', {}).get('total_items', 0)} items")
                    print(f"  - Model Headings: {artifacts.get('model', {}).get('total_headings', 0)} items")
                    print(f"  - Files: {artifacts.get('headers', {}).get('path')}")
            else:
                # MySQL 模式
                from tender_ontology.utils.db.mysql import get_db
                from tender_ontology.utils.db.mysql.models import ComplianceFileTask

                # 使用全局数据库连接池
                mysql = get_db()

                with mysql.get_session() as session:
                    task = session.query(ComplianceFileTask).filter(
                        ComplianceFileTask.id == task_id
                    ).first()

                    if task:
                        task.review_status = status
                        task.update_time = datetime.now()

                        # review_result 是整数类型，只存储简单的结果码
                        # artifacts 信息只打印日志，不存储到数据库
                        if artifacts and status == 2:
                            print(f"[Docling Task] Artifacts generated:")
                            print(f"  - Headers: {artifacts.get('headers', {}).get('total_headers', 0)} items")
                            print(f"  - Labeled: {artifacts.get('labeled', {}).get('total_items', 0)} items")
                            print(f"  - Model Headings: {artifacts.get('model', {}).get('total_headings', 0)} items")
                            print(f"  - Files: {artifacts.get('headers', {}).get('path')}")
                            # 如果需要存储 artifacts，可以考虑添加新的 TEXT/JSON 字段

                        session.commit()
                        print(f"[Docling Task] Task {task_id} status updated to {status}")

        except Exception as e:
            print(f"[Docling Task] Failed to update task status: {e}")
            import traceback
            traceback.print_exc()

    def process_docx_sync(
        self,
        docx_path: Path,
        task_id: str,
        db_task_id: Optional[int] = None,
        output_dir: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        处理 DOCX 文件（与 PDF 流程统一）

        Args:
            docx_path: DOCX 文件路径
            task_id: 任务 ID
            db_task_id: 数据库任务 ID（用于更新状态）
            output_dir: 输出目录

        Returns:
            处理结果
        """
        import time

        print(f"[Docling Task] ========== DOCX Start ==========")
        print(f"[Docling Task] Task ID: {task_id}")
        print(f"[Docling Task] DOCX: {docx_path}")
        print(f"[Docling Task] DB Task ID: {db_task_id}")
        print(f"[Docling Task] ================================")

        total_start = time.time()

        try:
            # 1. 更新状态为"处理中"
            if db_task_id:
                self._update_task_status(
                    db_task_id,
                    status=3,  # 解析中
                    message="DOCX 解析中..."
                )

            # 2. 确定输出目录
            if output_dir is None:
                output_dir = docx_path.parent

            # 3. 使用 DocxReader 读取并生成辅助文件
            from .docx.reader import DocxReader

            reader = DocxReader(debug=True)

            print(f"[Docling Task] 开始读取 DOCX 并生成辅助文件...")
            aux_files = reader.generate_auxiliary_files(docx_path, output_dir)

            print(f"[Docling Task] 辅助文件生成完成:")
            print(f"  - fulltext: {aux_files.get('fulltext_path', 'N/A')}")
            print(f"  - header_only: {aux_files.get('header_only_path', 'N/A')}")
            print(f"  - title_md: {aux_files.get('title_md_path', 'N/A')}")
            print(f"  - header_count: {aux_files.get('header_count', 0)}")

            artifacts = {}

            # 4. 读取 fulltext 数据
            fulltext_data = None
            if "fulltext_path" in aux_files:
                fulltext_path = Path(aux_files["fulltext_path"])
                fulltext_data = json.loads(fulltext_path.read_text(encoding='utf-8'))
                header_count = sum(1 for item in fulltext_data if item.get("label") == "section_header")
                print(f"[Docling Task] fulltext.json 中共有 {header_count} 个标题")

            # 5. 调用两阶段标题提取（复用 PDF 流程）
            if fulltext_data and "header_only_path" in aux_files and "title_md_path" in aux_files:
                print(f"[Docling Task] 开始调用千问 API（两阶段标题提取）...")

                try:
                    result_data = self._extract_docx_headings(
                        aux_files["header_only_path"],
                        aux_files["title_md_path"],
                        fulltext_data,
                        output_dir,
                        docx_path.stem
                    )
                    if result_data:
                        artifacts.update(result_data)
                except Exception as e:
                    print(f"[Docling Task] 千问调用异常: {e}")
                    import traceback
                    traceback.print_exc()

            # 6. 更新数据库状态为"完成"
            total_time = time.time() - total_start
            if db_task_id:
                self._update_task_status(
                    db_task_id,
                    status=2,  # 完成
                    message="DOCX 解析完成",
                    artifacts=artifacts
                )

            print(f"\n[Docling Task] ========== DOCX Complete ==========")
            print(f"[Docling Task] 总耗时: {total_time:.2f} 秒")
            print(f"[Docling Task] ====================================")

            return {
                "success": True,
                "task_id": task_id,
                "total_time": total_time,
                "artifacts": artifacts
            }

        except Exception as e:
            print(f"[Docling Task] Error: {e}")
            import traceback
            traceback.print_exc()

            # 更新状态为"失败"
            if db_task_id:
                self._update_task_status(
                    db_task_id,
                    status=4,  # 失败
                    message=f"DOCX 解析失败: {str(e)}"
                )

            return {
                "success": False,
                "task_id": task_id,
                "error": str(e)
            }

    def _extract_docx_headings(
        self,
        header_only_path: str,
        title_md_path: str,
        fulltext_data: list,
        output_dir: Path,
        base_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        DOCX 两阶段标题提取（复用 PDF 流程逻辑）

        Args:
            header_only_path: sectionHeader_only.md 文件路径
            title_md_path: title_with_id.md 文件路径
            fulltext_data: fulltext 数据
            output_dir: 输出目录
            base_name: 基础文件名

        Returns:
            artifacts 字典
        """
        try:
            from .qwen_heading_extractor_file import QwenHeadingExtractor
            import time

            total_start = time.time()
            print(f"[Qwen API DOCX] 开始两阶段标题提取...")

            extractor = QwenHeadingExtractor()

            # ========== 阶段1：提取一二级标题 ==========
            stage1_start = time.time()
            print(f"[Qwen API DOCX] 阶段1：提取一二级标题...")
            level12_headings = extractor.extract_headings_internal(
                header_only_path,
                header_count=0,
                verbose=True,
                save_response=True
            )
            stage1_time = time.time() - stage1_start
            print(f"[Qwen API DOCX] 阶段1完成，共 {len(level12_headings)} 个标题，耗时: {stage1_time:.2f} 秒")

            # 保存一阶段结果（使用 _docx 前缀）
            level12_json_path = output_dir / f"{base_name}_docx_level12.json"
            level12_json_path.write_text(
                json.dumps(level12_headings, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            print(f"[Qwen API DOCX] 一二级标题已保存: {level12_json_path.name}")

            artifacts = {
                "level12": {
                    "path": str(level12_json_path),
                    "total_headings": len(level12_headings)
                }
            }

            # ========== 阶段2：并发提取章节内子标题 ==========
            chapter_headings = [
                h for h in level12_headings
                if h.get("type") == "chapter"
            ]

            if chapter_headings:
                stage2_start = time.time()
                print(f"[Qwen API DOCX] 阶段2：并发提取 {len(chapter_headings)} 个章节的子标题...")

                chapter_results = extractor.extract_headings_by_chapters(
                    title_md_path,
                    chapter_headings,
                    max_workers=8,
                    verbose=True,
                    save_responses=False
                )

                # 聚合结果
                all_headings = extractor.merge_stage2_results(
                    level12_headings,
                    chapter_results,
                    verbose=True
                )
                stage2_time = time.time() - stage2_start
                print(f"[Qwen API DOCX] 阶段2完成，聚合后共 {len(all_headings)} 个标题，耗时: {stage2_time:.2f} 秒")

                # 填充位置信息
                extractor.enrich_headings_with_location(all_headings, fulltext_data, verbose=True)

                # 保存聚合后的标题（使用 _docx 前缀）
                agent_headings_path = output_dir / f"{base_name}_docx_agent_headings.json"
                agent_headings_path.write_text(
                    json.dumps(all_headings, ensure_ascii=False, indent=2),
                    encoding='utf-8'
                )
                print(f"[Qwen API DOCX] 聚合标题已保存: {agent_headings_path.name}")

                # 构建文档树
                print(f"[Qwen API DOCX] 开始构建文档层级树...")
                tree_result = extractor.build_document_tree(all_headings, fulltext_data, verbose=True)

                if tree_result:
                    # 保存 _docx_agent_tree.json
                    tree_json_path = output_dir / f"{base_name}_docx_agent_tree.json"
                    tree_json_path.write_text(
                        json.dumps(tree_result, ensure_ascii=False, indent=2),
                        encoding='utf-8'
                    )
                    print(f"[Qwen API DOCX] 文档树已保存: {tree_json_path.name}")
                    artifacts["agent_tree"] = {
                        "path": str(tree_json_path),
                        "summary": tree_result["summary"]
                    }

                    # 保存 _docx_agent.json
                    if "artifact" in tree_result:
                        agent_json_path = output_dir / f"{base_name}_docx_agent.json"
                        agent_json_path.write_text(
                            json.dumps(tree_result["artifact"], ensure_ascii=False, indent=2),
                            encoding='utf-8'
                        )
                        print(f"[Qwen API DOCX] Agent JSON 已保存: {agent_json_path.name}")
                        artifacts["agent"] = {"path": str(agent_json_path)}

                        # 调用 extract_onto API
                        self._call_extract_onto_api(
                            task_id=output_dir.name,
                            pdf_path=output_dir,
                            structured_data=tree_result["artifact"]
                        )

                # 打印耗时统计
                total_time = time.time() - total_start
                print(f"\n{'=' * 60}")
                print(f"[Qwen API DOCX] 两阶段标题提取完成！")
                print(f"{'=' * 60}")
                print(f"[耗时统计]")
                print(f"  - 阶段1 (一二级标题提取): {stage1_time:.2f} 秒")
                print(f"  - 阶段2 (章节并发重建+聚合): {stage2_time:.2f} 秒")
                print(f"  - 总耗时: {total_time:.2f} 秒")
                print(f"{'=' * 60}")

            return artifacts

        except Exception as e:
            print(f"[Qwen API DOCX] 提取失败: {e}")
            import traceback
            traceback.print_exc()
            return None


# 全局任务处理器实例
_background_task_handler = None


def get_background_task_handler() -> DoclingBackgroundTask:
    """
    获取全局后台任务处理器实例（单例模式）

    Returns:
        DoclingBackgroundTask 实例
    """
    global _background_task_handler
    if _background_task_handler is None:
        _background_task_handler = DoclingBackgroundTask()
    return _background_task_handler


def test_extract_onto_api(task_id: str = "25112810181731940156"):
    """
    测试 extract_onto API 调用

    直接读取指定任务目录下的 _agent.json 文件并调用 API

    Args:
        task_id: 任务 ID，默认为 25112810181731940156
    """
    import json
    import requests
    from pathlib import Path

    # 构建任务目录路径
    base_dir = Path(__file__).parent.parent.parent.parent.parent / "static" / "upload" / task_id

    print(f"{'=' * 60}")
    print(f"[测试] Extract Onto API 调用测试")
    print(f"{'=' * 60}")
    print(f"[测试] 任务 ID: {task_id}")
    print(f"[测试] 任务目录: {base_dir}")

    # 查找 _agent.json 文件
    agent_files = list(base_dir.glob("*_agent.json"))
    if not agent_files:
        print(f"[测试] 错误: 未找到 *_agent.json 文件")
        print(f"[测试] 目录内容: {list(base_dir.glob('*'))[:10]}")
        return None

    agent_file = agent_files[0]
    print(f"[测试] 找到 agent.json: {agent_file.name}")

    # 读取文件内容
    try:
        structured_data = json.loads(agent_file.read_text(encoding='utf-8'))
        print(f"[测试] structured_data 条数: {len(structured_data)}")
    except Exception as e:
        print(f"[测试] 读取文件失败: {e}")
        return None

    # 加载配置
    try:
        from tender_ontology.config.settings import settings
        api_url = settings.tender_extract_api_url
        timeout = settings.tender_extract_api_timeout
    except Exception:
        # 如果无法加载配置，使用默认值
        api_url = "http://112.111.20.89:8902/tender/extract_onto"
        timeout = 600

    # 构建请求数据
    request_data = {
        "task_id": task_id,
        "pdf_url": "",
        "document_type": "",
        "region": "",
        "structured_data": structured_data
    }

    print(f"\n[测试] 开始调用 API...")
    print(f"[测试] URL: {api_url}")
    print(f"[测试] task_id: {task_id}")
    print(f"[测试] pdf_url: (空)")
    print(f"[测试] structured_data 条数: {len(structured_data)}")

    # 发送请求
    import time
    try:
        start_time = time.time()
        response = requests.post(
            api_url,
            json=request_data,
            headers={"Content-Type": "application/json"},
            timeout=timeout
        )
        elapsed_time = time.time() - start_time

        print(f"\n[测试] HTTP 状态码: {response.status_code}")
        print(f"[测试] 耗时: {elapsed_time:.2f} 秒")

        if response.status_code == 200:
            result = response.json()
            print(f"[测试] 调用成功!")
            print(f"[测试] 响应: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}")

            # 保存响应到 _ontology.json
            base_name = agent_file.stem.replace('_agent', '')
            ontology_path = base_dir / f"{base_name}_ontology.json"
            ontology_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            print(f"[测试] 响应已保存: {ontology_path}")

            return result
        else:
            print(f"[测试] 调用失败!")
            print(f"[测试] 响应内容: {response.text[:500]}")
            return None

    except requests.Timeout:
        print(f"[测试] 请求超时（{timeout}秒）")
        return None
    except requests.RequestException as e:
        print(f"[测试] 请求异常: {e}")
        return None
    except Exception as e:
        print(f"[测试] 未知错误: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_docx_process(task_id: str = "25112810181731940156"):
    """
    测试 DOCX 处理流程

    从 static/upload/{task_id}/ 目录中查找 DOCX 文件并处理

    Args:
        task_id: 任务 ID
    """
    from pathlib import Path

    # 构建任务目录路径
    base_dir = Path(__file__).parent.parent.parent.parent.parent / "static" / "upload" / task_id

    print(f"{'=' * 60}")
    print(f"[测试] DOCX 处理流程测试")
    print(f"{'=' * 60}")
    print(f"[测试] 任务 ID: {task_id}")
    print(f"[测试] 任务目录: {base_dir}")

    if not base_dir.exists():
        print(f"[测试] 错误: 目录不存在")
        return None

    # 查找 DOCX 文件
    docx_files = list(base_dir.glob("*.docx"))
    if not docx_files:
        print(f"[测试] 错误: 未找到 .docx 文件")
        print(f"[测试] 目录内容: {list(base_dir.glob('*'))[:10]}")
        return None

    docx_file = docx_files[0]
    print(f"[测试] 找到 DOCX 文件: {docx_file.name}")

    # 创建处理器并执行
    handler = get_background_task_handler()
    result = handler.process_docx_sync(
        docx_path=docx_file,
        task_id=task_id,
        output_dir=base_dir
    )

    print(f"\n[测试] 处理结果: {'成功' if result.get('success') else '失败'}")
    if result.get('success'):
        print(f"[测试] 总耗时: {result.get('total_time', 0):.2f} 秒")
        print(f"[测试] 生成文件: {list(result.get('artifacts', {}).keys())}")

    return result


if __name__ == "__main__":
    import sys

    # 如果有命令行参数
    if len(sys.argv) > 1:
        task_id = sys.argv[1]
        # 第二个参数指定测试类型
        if len(sys.argv) > 2 and sys.argv[2] == "docx":
            test_docx_process(task_id)
        else:
            test_extract_onto_api(task_id)
    else:
        # 默认测试 extract_onto API
        task_id = "25112810181731940156"
        test_extract_onto_api(task_id)