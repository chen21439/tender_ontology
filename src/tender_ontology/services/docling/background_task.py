"""
Docling 后台任务处理

用于异步处理 PDF 推理任务
"""

import threading
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import json

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

            # 3.5 调用千问提取层级标题
            qwen_headings = None
            if "markdown_path" in results:
                try:
                    print(f"[Docling Task] 开始千问标题提取...")
                    qwen_headings = self._extract_headings_with_qwen(results["markdown_path"])
                    print(f"[Docling Task] 千问标题提取完成，共 {len(qwen_headings)} 个标题")

                    # 保存千问标题到 JSON 文件（直接保存数组）
                    markdown_path = Path(results["markdown_path"])
                    model_json_path = markdown_path.parent / f"{markdown_path.stem}_model.json"
                    model_json_path.write_text(json.dumps(qwen_headings, ensure_ascii=False, indent=2), encoding='utf-8')
                    print(f"[Docling Task] 模型标题已保存: {model_json_path.name}")

                    artifacts["model"] = {
                        "path": str(model_json_path),
                        "total_headings": len(qwen_headings)
                    }
                except Exception as e:
                    print(f"[Docling Task] 千问标题提取失败: {e}")
                    import traceback
                    traceback.print_exc()

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

    def _extract_headings_with_qwen(self, markdown_path: str) -> list:
        """
        使用千问API提取Markdown中的层级标题（完整流程：上传+提取）

        Args:
            markdown_path: Markdown 文件路径

        Returns:
            标题列表，每个标题包含 text, level, page 字段
        """
        from tender_ontology.utils.document_struct.qwen_client import QwenClient

        # 创建千问客户端
        api_key = "sk-f67e1a1d436c4df19ac575d8483e247d"
        client = QwenClient(api_key=api_key, model="qwen-long")

        # 第一步：上传文件获取 file_id
        print(f"[Qwen] 上传文件中...")
        file_id = client.upload_file(markdown_path, purpose="file-extract", verbose=True)
        print(f"[Qwen] 文件上传成功，file_id: {file_id}")

        # 第二步：使用 file_id 提取标题
        return self.extract_headings_by_file_id(file_id)

    def extract_headings_by_file_id(self, file_id: str = "file-fe-b75e560d00cc48bfa37e36ca") -> list:
        """
        使用千问API根据 file_id 提取标题（独立方法，可直接调用）

        Args:
            file_id: 千问文件ID，默认使用测试文件

        Returns:
            标题列表，每个标题包含 text, level, page 字段
        """
        from tender_ontology.utils.document_struct.qwen_client import QwenClient
        import re

        # 提示词
        prompt = """你是一个专业的文档结构分析引擎，**仅**专注于修复原文中所有不规范的标题标记（如误用 | 或 --- 的地方）。

## 输出要求
- 仅在```markdown```中返回修正并层级化后的标题结构，不包含任何段落、表格或说明。
- 标题层级使用# ## ### 在markdown中显示。

示例输出格式：
```markdown
# 一级标题
## 二级标题
### 三级标题
#### 四级标题
```

现在，请提取文档中的所有标题。"""

        # 创建千问客户端
        api_key = "sk-f67e1a1d436c4df19ac575d8483e247d"
        client = QwenClient(api_key=api_key, model="qwen-long-latest")

        # 构建消息（fileid 放在 system，任务放在 user）
        system_prompt = f"fileid://{file_id}"

        print(f"[Qwen] 使用 file_id: {file_id} 提取标题...")

        # 发送请求
        response = client.send_request(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.0,
            verbose=True
        )

        # 解析 Markdown 响应
        markdown_match = re.search(r'```markdown\s*(.*?)\s*```', response, re.DOTALL)
        if markdown_match:
            markdown_content = markdown_match.group(1).strip()
        else:
            markdown_content = response.strip()

        # 将 Markdown 标题转换为结构化数据
        headings = []
        for line in markdown_content.split('\n'):
            line = line.strip()
            if line.startswith('#'):
                level = len(line) - len(line.lstrip('#'))
                text = line.lstrip('#').strip()
                if text:
                    headings.append({
                        "text": text,
                        "level": level,
                        "page": ""
                    })

        print(f"[Qwen] 提取完成，共 {len(headings)} 个标题")
        return headings

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
        更新数据库中的任务状态

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
            from tender_ontology.utils.db.mysql import MySQLUtil
            from tender_ontology.utils.db.mysql.models import ComplianceFileTask

            mysql = MySQLUtil(
                host="172.16.0.116",
                port=3306,
                user="root",
                password="123456",
                database="tender_compliance",
                charset="utf8mb4",
                echo=False
            )

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

            mysql.close()

        except Exception as e:
            print(f"[Docling Task] Failed to update task status: {e}")
            import traceback
            traceback.print_exc()


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


if __name__ == "__main__":
    # 直接测试千问标题提取
    handler = get_background_task_handler()

    # 使用默认 file_id 或者传入你自己的
    file_id = "file-fe-b75e560d00cc48bfa37e36ca"

    print(f"开始提取标题，使用 file_id: {file_id}\n")

    headings = handler.extract_headings_by_file_id(file_id)

    print(f"\n{'='*80}")
    print(f"提取完成！共 {len(headings)} 个标题")
    print(f"{'='*80}\n")

    # 打印所有标题（Markdown 格式）
    for h in headings:
        prefix = "#" * h["level"]
        print(f"{prefix} {h['text']}")