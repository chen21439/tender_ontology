"""
HTTP 请求客户端

提供通用的 HTTP 请求功能，支持：
- 文件上传
- JSON 请求
- 文件下载
- 重试机制
"""

import time
import requests
from pathlib import Path
from typing import Optional, Dict, Any, Union


class HttpClient:
    """通用 HTTP 客户端"""

    def __init__(
        self,
        base_url: str = "",
        timeout: float = 60.0,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        verbose: bool = True
    ):
        """
        初始化 HTTP 客户端

        Args:
            base_url: 基础 URL（可选）
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
            verbose: 是否打印详细日志
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.verbose = verbose

    def _log(self, message: str):
        """打印日志"""
        if self.verbose:
            print(f"[HttpClient] {message}")

    def _build_url(self, endpoint: str) -> str:
        """构建完整 URL"""
        if endpoint.startswith("http"):
            return endpoint
        return f"{self.base_url}{endpoint}"

    def post_json(
        self,
        endpoint: str,
        data: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        发送 JSON POST 请求

        Args:
            endpoint: API 端点
            data: 请求数据
            headers: 请求头
            timeout: 超时时间（可选，使用实例默认值）

        Returns:
            响应 JSON 数据

        Raises:
            Exception: 请求失败
        """
        url = self._build_url(endpoint)
        timeout = timeout or self.timeout

        default_headers = {"Content-Type": "application/json"}
        if headers:
            default_headers.update(headers)

        self._log(f"POST JSON: {url}")

        last_error = None
        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    self._log(f"重试 {attempt}/{self.max_retries - 1}...")
                    time.sleep(self.retry_delay)

                response = requests.post(
                    url,
                    json=data,
                    headers=default_headers,
                    timeout=timeout
                )
                response.raise_for_status()

                result = response.json()
                self._log(f"响应成功: {response.status_code}")
                return result

            except Exception as e:
                last_error = e
                self._log(f"请求失败: {e}")

        raise Exception(f"POST JSON 失败: {last_error}")

    def post_file(
        self,
        endpoint: str,
        file_path: Union[str, Path],
        file_field: str = "file",
        extra_fields: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        上传文件（multipart/form-data）

        Args:
            endpoint: API 端点
            file_path: 文件路径
            file_field: 文件字段名
            extra_fields: 额外的表单字段
            timeout: 超时时间

        Returns:
            响应 JSON 数据

        Raises:
            Exception: 请求失败
        """
        url = self._build_url(endpoint)
        timeout = timeout or self.timeout
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        self._log(f"POST FILE: {url}")
        self._log(f"文件: {file_path.name}")

        last_error = None
        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    self._log(f"重试 {attempt}/{self.max_retries - 1}...")
                    time.sleep(self.retry_delay)

                with open(file_path, "rb") as f:
                    files = {file_field: (file_path.name, f)}
                    data = extra_fields or {}

                    response = requests.post(
                        url,
                        files=files,
                        data=data,
                        timeout=timeout
                    )
                    response.raise_for_status()

                result = response.json()
                self._log(f"响应成功: {response.status_code}")
                return result

            except Exception as e:
                last_error = e
                self._log(f"请求失败: {e}")

        raise Exception(f"POST FILE 失败: {last_error}")

    def get_json(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        发送 GET 请求

        Args:
            endpoint: API 端点
            params: 查询参数
            headers: 请求头
            timeout: 超时时间

        Returns:
            响应 JSON 数据

        Raises:
            Exception: 请求失败
        """
        url = self._build_url(endpoint)
        timeout = timeout or self.timeout

        self._log(f"GET: {url}")

        last_error = None
        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    self._log(f"重试 {attempt}/{self.max_retries - 1}...")
                    time.sleep(self.retry_delay)

                response = requests.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout
                )
                response.raise_for_status()

                result = response.json()
                self._log(f"响应成功: {response.status_code}")
                return result

            except Exception as e:
                last_error = e
                self._log(f"请求失败: {e}")

        raise Exception(f"GET 失败: {last_error}")

    def download_file(
        self,
        endpoint: str,
        save_path: Union[str, Path],
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None
    ) -> Path:
        """
        下载文件

        Args:
            endpoint: API 端点
            save_path: 保存路径
            params: 查询参数
            timeout: 超时时间

        Returns:
            保存的文件路径

        Raises:
            Exception: 下载失败
        """
        url = self._build_url(endpoint)
        timeout = timeout or self.timeout
        save_path = Path(save_path)

        # 确保目录存在
        save_path.parent.mkdir(parents=True, exist_ok=True)

        self._log(f"DOWNLOAD: {url}")
        self._log(f"保存到: {save_path}")

        last_error = None
        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    self._log(f"重试 {attempt}/{self.max_retries - 1}...")
                    time.sleep(self.retry_delay)

                response = requests.get(
                    url,
                    params=params,
                    timeout=timeout,
                    stream=True
                )
                response.raise_for_status()

                # 写入文件
                with open(save_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                file_size = save_path.stat().st_size
                self._log(f"下载成功: {file_size} bytes")
                return save_path

            except Exception as e:
                last_error = e
                self._log(f"下载失败: {e}")

        raise Exception(f"DOWNLOAD 失败: {last_error}")


# ============== DOCX 转 PDF 服务客户端 ==============

class DocxPdfClient:
    """DOCX 转 PDF 服务客户端"""

    # 任务状态常量
    STATUS_UPLOADED = "UPLOADED"
    STATUS_CONVERTING = "CONVERTING"
    STATUS_EXTRACTING = "EXTRACTING"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_FAILED = "FAILED"
    STATUS_NOT_FOUND = "NOT_FOUND"

    # 终态列表
    FINAL_STATUSES = {STATUS_COMPLETED, STATUS_FAILED, STATUS_NOT_FOUND}

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        timeout: float = 120.0,
        poll_interval: float = 2.0,
        max_poll_time: float = 300.0,
        verbose: bool = True
    ):
        """
        初始化客户端

        Args:
            base_url: 服务地址
            timeout: 请求超时时间
            poll_interval: 状态轮询间隔（秒）
            max_poll_time: 最大轮询时间（秒）
            verbose: 是否打印日志
        """
        self.http = HttpClient(
            base_url=base_url,
            timeout=timeout,
            verbose=verbose
        )
        self.poll_interval = poll_interval
        self.max_poll_time = max_poll_time
        self.verbose = verbose

    def _log(self, message: str):
        """打印日志"""
        if self.verbose:
            print(f"[DocxPdfClient] {message}")

    def process(
        self,
        docx_path: Union[str, Path],
        include_mcid: bool = False
    ) -> Dict[str, Any]:
        """
        上传 DOCX 并处理

        POST /api/docx-pdf/process

        Args:
            docx_path: DOCX 文件路径
            include_mcid: 是否包含 MCID

        Returns:
            {
                "success": bool,
                "taskId": str,
                "message": str
            }
        """
        self._log(f"开始处理: {docx_path}")

        extra_fields = {}
        if include_mcid:
            extra_fields["includeMcid"] = "true"

        result = self.http.post_file(
            endpoint="/api/docx-pdf/process",
            file_path=docx_path,
            file_field="file",
            extra_fields=extra_fields
        )

        if result.get("success"):
            self._log(f"处理成功, taskId: {result.get('taskId')}")
        else:
            self._log(f"处理失败: {result.get('message')}")

        return result

    def get_status(self, task_id: str, silent: bool = False) -> Dict[str, Any]:
        """
        查询任务状态

        GET /api/docx-pdf/status/{taskId}

        Args:
            task_id: 任务 ID
            silent: 是否静默模式（不打印日志）

        Returns:
            {
                "taskId": str,
                "exists": bool,
                "status": str,  # UPLOADED/CONVERTING/EXTRACTING/COMPLETED/FAILED/NOT_FOUND
                "message": str,
                "updateTime": int,
                "pdfPath": str,
                "txtPath": str
            }
        """
        # 临时关闭日志
        if silent:
            old_verbose = self.http.verbose
            self.http.verbose = False
            try:
                return self.http.get_json(endpoint=f"/api/docx-pdf/status/{task_id}")
            finally:
                self.http.verbose = old_verbose
        return self.http.get_json(endpoint=f"/api/docx-pdf/status/{task_id}")

    def wait_for_completion(
        self,
        task_id: str,
        poll_interval: Optional[float] = None,
        max_poll_time: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        轮询等待任务完成

        Args:
            task_id: 任务 ID
            poll_interval: 轮询间隔（秒），默认 5 秒
            max_poll_time: 最大等待时间（秒），默认使用实例配置

        Returns:
            最终状态信息
        """
        import time

        poll_interval = poll_interval or 5.0  # 默认 5 秒轮询一次
        max_poll_time = max_poll_time or self.max_poll_time

        self._log(f"等待任务完成: {task_id} (每{poll_interval}s轮询, 最长{max_poll_time}s)")
        start_time = time.time()
        last_status = None

        while True:
            elapsed = time.time() - start_time
            if elapsed > max_poll_time:
                return {
                    "success": False,
                    "status": "TIMEOUT",
                    "message": f"轮询超时（{max_poll_time}秒）"
                }

            try:
                status_result = self.get_status(task_id, silent=True)  # 静默模式，不打印轮询日志
                status = status_result.get("status", "UNKNOWN")

                # 只在状态变化时打印日志
                if status != last_status:
                    self._log(f"状态: {status} ({elapsed:.0f}s)")
                    last_status = status

                if status in self.FINAL_STATUSES:
                    if status == self.STATUS_COMPLETED:
                        return {
                            "success": True,
                            "status": status,
                            "message": status_result.get("message", "处理完成"),
                            "pdfPath": status_result.get("pdfPath"),
                            "txtPath": status_result.get("txtPath")
                        }
                    else:
                        return {
                            "success": False,
                            "status": status,
                            "message": status_result.get("message", f"任务失败: {status}")
                        }

                time.sleep(poll_interval)

            except Exception as e:
                self._log(f"轮询异常: {e}")
                time.sleep(poll_interval)

    def download_artifact(
        self,
        task_id: str,
        save_path: Union[str, Path]
    ) -> Path:
        """
        下载处理结果 ZIP

        GET /api/docx-pdf/artifact/{taskId}

        Args:
            task_id: 任务 ID
            save_path: 保存路径

        Returns:
            保存的文件路径
        """
        self._log(f"下载结果: taskId={task_id}")

        return self.http.download_file(
            endpoint=f"/api/docx-pdf/artifact/{task_id}",
            save_path=save_path
        )

    def process_and_download(
        self,
        docx_path: Union[str, Path],
        output_dir: Union[str, Path],
        include_mcid: bool = False
    ) -> Dict[str, Any]:
        """
        完整流程：处理 DOCX → 等待完成 → 下载结果

        Args:
            docx_path: DOCX 文件路径
            output_dir: 输出目录
            include_mcid: 是否包含 MCID

        Returns:
            {
                "success": bool,
                "taskId": str,
                "zip_path": Path,
                "pdfPath": str,
                "txtPath": str,
                "message": str
            }
        """
        docx_path = Path(docx_path)
        output_dir = Path(output_dir)

        # Step 1: 上传并处理
        process_result = self.process(docx_path, include_mcid)

        if not process_result.get("success"):
            return {
                "success": False,
                "message": process_result.get("message", "处理失败")
            }

        task_id = process_result.get("taskId")

        # Step 2: 等待完成
        wait_result = self.wait_for_completion(task_id)

        if not wait_result.get("success"):
            return {
                "success": False,
                "taskId": task_id,
                "message": wait_result.get("message", "等待完成失败")
            }

        # Step 3: 下载结果
        zip_path = output_dir / f"{task_id}.zip"
        try:
            self.download_artifact(task_id, zip_path)
            return {
                "success": True,
                "taskId": task_id,
                "zip_path": zip_path,
                "pdfPath": wait_result.get("pdfPath"),
                "txtPath": wait_result.get("txtPath"),
                "message": "处理并下载成功"
            }
        except Exception as e:
            return {
                "success": False,
                "taskId": task_id,
                "message": f"下载失败: {e}"
            }


# ============== Aspose Words API 客户端 ==============

class AsposeWordsClient:
    """
    Aspose Words Cloud API 客户端

    用于 DOCX 转 PDF 等文档转换操作
    直接使用传入的 Bearer Token，无需 OAuth 流程

    API 文档: https://docs.aspose.cloud/words/
    """

    # API 端点
    API_BASE_URL = "https://api.aspose.cloud/v4.0/words"

    def __init__(
        self,
        access_token: str,
        timeout: float = 120.0,
        verbose: bool = True
    ):
        """
        初始化 Aspose Words 客户端

        Args:
            access_token: Bearer Token（已获取好的 access token）
            timeout: 请求超时时间（秒）
            verbose: 是否打印详细日志
        """
        self.access_token = access_token
        self.timeout = timeout
        self.verbose = verbose

    def _log(self, message: str):
        """打印日志"""
        if self.verbose:
            print(f"[AsposeWords] {message}")

    def convert_docx_to_pdf(
        self,
        docx_path: Union[str, Path],
        output_path: Optional[Union[str, Path]] = None,
        compliance: str = "Pdf17"
    ) -> Dict[str, Any]:
        """
        将 DOCX 转换为 PDF

        使用 Aspose Words Cloud API 的 saveAs 接口

        Args:
            docx_path: DOCX 文件路径
            output_path: 输出 PDF 路径（可选，默认同目录同名 .pdf）
            compliance: PDF 合规性标准
                - "Pdf17": PDF 1.7 (默认)
                - "PdfA1a": PDF/A-1a
                - "PdfA1b": PDF/A-1b
                - "PdfA2a": PDF/A-2a
                - "PdfA2u": PDF/A-2u
                - "PdfA4": PDF/A-4
                - "PdfUa1": PDF/UA-1

        Returns:
            {
                "success": bool,
                "output_path": Path,
                "file_size": int,
                "error": str (if failed)
            }
        """
        docx_path = Path(docx_path)

        if not docx_path.exists():
            return {"success": False, "error": f"文件不存在: {docx_path}"}

        # 确定输出路径
        if output_path is None:
            output_path = docx_path.with_suffix(".pdf")
        else:
            output_path = Path(output_path)

        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)

        self._log(f"开始转换: {docx_path.name} -> {output_path.name}")

        # 构建保存选项
        save_options = {
            "SaveFormat": "pdf",
            "FileName": output_path.name,
            "Compliance": compliance,
            # 导出文档结构
            "ExportDocumentStructure": True,
            # 导出所有书签为 PDF 大纲/书签（级别 1 表示全部导出）
            "BookmarksOutlineLevel": 1,
            # 不导出标题为大纲（只要书签）
            "HeadingsOutlineLevels": 0
        }

        self._log(f"SaveOptions:")
        for key, value in save_options.items():
            self._log(f"  {key}: {value}")

        # 发送请求
        url = f"{self.API_BASE_URL}/online/put/saveAs"

        try:
            import json as json_module
            from requests_toolbelt import MultipartEncoder

            # 构建 multipart/form-data 请求
            # 按 curl 的 --form 顺序：先 document，后 saveOptionsData
            save_options_json = json_module.dumps(save_options)

            with open(docx_path, "rb") as f:
                file_content = f.read()

            # 使用 MultipartEncoder 确保字段顺序和格式正确
            multipart_data = MultipartEncoder(
                fields={
                    'document': (docx_path.name, file_content, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
                    'saveOptionsData': save_options_json
                }
            )

            response = requests.put(
                url,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": multipart_data.content_type
                },
                data=multipart_data,
                timeout=self.timeout
            )

            if response.status_code == 200:
                # 成功，保存 PDF
                with open(output_path, "wb") as out_f:
                    out_f.write(response.content)

                file_size = output_path.stat().st_size
                self._log(f"转换成功: {output_path.name} ({file_size} bytes)")

                return {
                    "success": True,
                    "output_path": output_path,
                    "file_size": file_size
                }

            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:500]}"
                self._log(f"转换失败: {error_msg}")
                return {"success": False, "error": error_msg}

        except requests.Timeout:
            self._log("请求超时")
            return {"success": False, "error": f"请求超时（{self.timeout}秒）"}

        except Exception as e:
            self._log(f"转换异常: {e}")
            return {"success": False, "error": str(e)}

    def convert_docx_to_pdf_with_retry(
        self,
        docx_path: Union[str, Path],
        output_path: Optional[Union[str, Path]] = None,
        compliance: str = "Pdf17",
        max_retries: int = 3,
        retry_delay: float = 2.0
    ) -> Dict[str, Any]:
        """
        带重试的 DOCX 转 PDF

        Args:
            docx_path: DOCX 文件路径
            output_path: 输出 PDF 路径
            compliance: PDF 合规性标准
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）

        Returns:
            与 convert_docx_to_pdf 相同
        """
        last_error = None
        for attempt in range(max_retries):
            if attempt > 0:
                self._log(f"重试 {attempt}/{max_retries - 1}...")
                time.sleep(retry_delay)

            result = self.convert_docx_to_pdf(
                docx_path=docx_path,
                output_path=output_path,
                compliance=compliance
            )

            if result["success"]:
                return result

            last_error = result.get("error")
            self._log(f"尝试 {attempt + 1} 失败: {last_error}")

        return {"success": False, "error": f"已重试 {max_retries} 次: {last_error}"}


def get_aspose_client(access_token: Optional[str] = None) -> Optional[AsposeWordsClient]:
    """
    获取 Aspose Words 客户端实例

    Args:
        access_token: Bearer Token，如不提供则从配置读取

    Returns:
        AsposeWordsClient 实例，如果 token 不存在则返回 None
    """
    try:
        if not access_token:
            from tender_ontology.config.settings import settings
            access_token = getattr(settings, 'aspose_access_token', None)

        if not access_token:
            print("[AsposeWords] 未提供 access_token")
            return None

        return AsposeWordsClient(
            access_token=access_token,
            verbose=True
        )

    except Exception as e:
        print(f"[AsposeWords] 初始化失败: {e}")
        return None


# ============== 命令行测试 ==============

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python http_client.py <command> [args...]")
        print()
        print("命令:")
        print("  docx-pdf <docx_path> [output_dir]  - 使用本地服务转换")
        print("  aspose <docx_path> [output_path]   - 使用 Aspose Cloud 转换")
        print()
        print("示例:")
        print("  python http_client.py docx-pdf test.docx ./output")
        print("  python http_client.py aspose test.docx test.pdf")
        sys.exit(1)

    command = sys.argv[1]

    if command == "docx-pdf":
        docx_path = Path(sys.argv[2])
        output_dir = Path(sys.argv[3]) if len(sys.argv) > 3 else docx_path.parent

        client = DocxPdfClient(
            base_url="http://localhost:8080",
            verbose=True
        )

        result = client.process_and_download(
            docx_path=docx_path,
            output_dir=output_dir,
            include_mcid=True
        )

        print(f"\n结果: {result}")

    elif command == "aspose":
        docx_path = Path(sys.argv[2])
        output_path = Path(sys.argv[3]) if len(sys.argv) > 3 else None

        client = get_aspose_client()
        if client is None:
            print("请配置 ASPOSE_CLIENT_ID 和 ASPOSE_CLIENT_SECRET 环境变量")
            sys.exit(1)

        try:
            result_path = client.convert_docx_to_pdf(
                docx_path=docx_path,
                output_path=output_path
            )
            print(f"\n转换成功: {result_path}")
        except Exception as e:
            print(f"\n转换失败: {e}")
            sys.exit(1)

    else:
        print(f"未知命令: {command}")
        sys.exit(1)
