"""
Predict API 客户端

调用推理服务的 /predict 接口
"""

from typing import Dict, Any, Optional, List

from tender_ontology.utils.request.http_client import HttpClient
from tender_ontology.config.settings import settings
from tender_ontology.config.logging_config import logger


class PredictClient:
    """Predict API 客户端"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 300.0,
        verbose: bool = True
    ):
        """
        初始化 Predict 客户端

        Args:
            base_url: 服务地址（默认从配置读取）
            timeout: 请求超时时间（秒），默认 5 分钟
            verbose: 是否打印详细日志
        """
        self.base_url = base_url or settings.infer_service_url
        self.timeout = timeout
        self.verbose = verbose
        self.http = HttpClient(
            base_url=self.base_url,
            timeout=timeout,
            max_retries=3,
            retry_delay=2.0,
            verbose=verbose
        )

    def _log(self, message: str):
        """打印日志"""
        if self.verbose:
            logger.info(f"[PredictClient] {message}")

    def predict(
        self,
        document_name: str,
        task_id: Optional[str] = None,
        build_tree: bool = True,
        convert_to_onto: bool = True,
        page_heights: Optional[Dict[int, float]] = None
    ) -> Dict[str, Any]:
        """
        调用 predict API

        Args:
            document_name: 文档名称（不含扩展名，如 filename.docx 传 filename）
            task_id: 任务 ID（可选，后续接口会支持）
            build_tree: 是否将扁平数据构建成树结构（默认 True）
            convert_to_onto: 是否转换为 extract_onto API 格式（默认 True）
            page_heights: 页面高度映射（用于坐标系转换，可选）

        Returns:
            API 响应结果，包含:
            - success: 是否成功
            - data: 原始响应数据
            - structured_data: 构建好的树结构（如果 build_tree=True）
            - onto_data: 转换为 extract_onto 格式的数据（如果 convert_to_onto=True）
        """
        self._log(f"调用 predict API: document_name={document_name}, task_id={task_id}")
        self._log(f"服务地址: {self.base_url}/predict")

        # 构建请求数据
        data = {
            "document_name": document_name
        }
        if task_id:
            data["task_id"] = task_id

        try:
            result = self.http.post_json(
                endpoint="/predict",
                data=data,
                timeout=self.timeout
            )
            self._log(f"predict API 调用成功")
            self._log(f"响应类型: {type(result).__name__}")
            if isinstance(result, dict):
                self._log(f"响应键: {list(result.keys())}")
            elif isinstance(result, list):
                self._log(f"响应列表长度: {len(result)}")

            response = {
                "success": True,
                "data": result
            }

            # 构建树结构
            if build_tree:
                flat_data = self._extract_flat_data(result)
                self._log(f"提取扁平数据: {len(flat_data) if flat_data else 'None'}")
                if flat_data:
                    structured_data = self._build_tree(flat_data)
                    response["structured_data"] = structured_data
                    self._log(f"树构建完成，根节点数: {len(structured_data)}")

                    # 转换为 extract_onto 格式
                    if convert_to_onto:
                        onto_data = self._convert_to_onto_format(structured_data, page_heights)
                        response["onto_data"] = onto_data
                        self._log(f"格式转换完成，onto_data 根节点数: {len(onto_data)}")

            return response

        except Exception as e:
            self._log(f"predict API 调用失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _extract_flat_data(self, result: Any) -> Optional[List[Dict[str, Any]]]:
        """
        从 API 响应中提取扁平数据

        Args:
            result: API 响应

        Returns:
            扁平数据列表，或 None
        """
        # 响应可能是列表或字典
        if isinstance(result, list):
            return result
        elif isinstance(result, dict):
            # 尝试从常见字段中提取
            for key in ["data", "items", "nodes", "lines", "result"]:
                if key in result and isinstance(result[key], list):
                    return result[key]
            # 如果字典本身就是数据
            if "line_id" in result or "parent_id" in result:
                return [result]
        return None

    def _build_tree(self, flat_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        将扁平数据构建成树结构

        Args:
            flat_data: 扁平数据列表

        Returns:
            树结构列表
        """
        from tender_ontology.utils.tree_builder import build_tree_from_flat_data

        return build_tree_from_flat_data(
            flat_data,
            id_field="line_id",
            parent_id_field="parent_id",
            relation_field="relation",
            verbose=self.verbose
        )

    def _convert_to_onto_format(
        self,
        tree: List[Dict[str, Any]],
        page_heights: Optional[Dict[int, float]] = None
    ) -> List[Dict[str, Any]]:
        """
        将树结构转换为 extract_onto API 需要的格式

        Args:
            tree: 树结构列表
            page_heights: 页面高度映射（用于坐标系转换）

        Returns:
            转换后的树结构列表
        """
        from tender_ontology.utils.tree_builder import convert_tree_to_onto_format

        return convert_tree_to_onto_format(tree, page_heights, self.verbose)


# 单例实例（可选）
_predict_client: Optional[PredictClient] = None


def get_predict_client() -> PredictClient:
    """获取 PredictClient 单例"""
    global _predict_client
    if _predict_client is None:
        _predict_client = PredictClient()
    return _predict_client