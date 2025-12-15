"""
文档系统路由（演示模式）

基于 JSON 文件的虚拟文件夹管理：
- 存储：扁平化 parent_id 结构
- 返回：树形 children 结构
"""

from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from pathlib import Path
import json

# 创建路由
router = APIRouter(prefix="/document_system", tags=["文档系统"])

# 默认数据文件名
DEFAULT_DATA_FILE = "document/document.json"


# ==================== 请求/响应模型 ====================

class FolderCreateRequest(BaseModel):
    """创建文件夹请求"""
    name: str = Field(..., description="文件夹名称")
    parent_id: Optional[int] = Field(None, description="父节点ID，不填则创建根节点")


class FolderDeleteRequest(BaseModel):
    """删除文件夹请求"""
    id: int = Field(..., description="要删除的节点ID")
    force: bool = Field(False, description="是否强制删除有子节点的文件夹")


class FolderUpdateRequest(BaseModel):
    """修改文件夹请求"""
    id: int = Field(..., description="要修改的节点ID")
    name: str = Field(..., description="新名称")


class FolderInfo(BaseModel):
    """文件夹信息"""
    id: int = Field(..., description="节点ID")
    parent_id: Optional[int] = Field(None, description="父节点ID")
    code: str = Field(..., description="节点编码")
    name: str = Field(..., description="文件夹名称")
    content: str = Field("", description="内容")


class TreeNode(BaseModel):
    """树节点（返回给前端）"""

    id: int = Field(..., description="节点ID")
    parent_id: Optional[int] = Field(None, description="父节点ID")
    code: str = Field(..., description="节点编码")
    name: str = Field(..., description="节点名称")
    path: str = Field(..., description="完整路径")
    content: str = Field("", description="节点内容")
    children: List["TreeNode"] = Field(default_factory=list, description="子节点")


class BaseResponse(BaseModel):
    """基础响应"""
    success: bool = Field(..., description="是否成功")
    errCode: Optional[str] = Field(None, description="错误码")
    errMsg: Optional[str] = Field(None, description="错误信息")
    data: Optional[Any] = Field(None, description="数据")


# ==================== 辅助函数 ====================

def get_static_dir() -> Path:
    """获取 static 目录路径"""
    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent.parent
    static_dir = project_root / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    return static_dir


def get_document_system_dir() -> Path:
    """获取 static/document_system 目录路径"""
    static_dir = get_static_dir()
    doc_system_dir = static_dir / "document_system"
    doc_system_dir.mkdir(parents=True, exist_ok=True)
    return doc_system_dir


def get_data_file_path() -> Path:
    """获取默认数据文件路径"""
    return get_document_system_dir() / DEFAULT_DATA_FILE


def load_data() -> List[Dict[str, Any]]:
    """加载 JSON 数据"""
    file_path = get_data_file_path()
    if not file_path.exists():
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data: List[Dict[str, Any]]) -> None:
    """保存 JSON 数据"""
    file_path = get_data_file_path()
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_next_id(data: List[Dict[str, Any]]) -> int:
    """获取下一个可用的 id"""
    if not data:
        return 1
    max_id = max(item.get("id", 0) for item in data)
    return max_id + 1


def find_node_by_id(data: List[Dict[str, Any]], node_id: int) -> Optional[Dict[str, Any]]:
    """根据 id 查找节点"""
    for item in data:
        if item.get("id") == node_id:
            return item
    return None


def get_children_ids(data: List[Dict[str, Any]], parent_id: int) -> List[int]:
    """递归获取所有子孙节点的 id"""
    children_ids = []
    for item in data:
        if item.get("parent_id") == parent_id:
            child_id = item.get("id")
            children_ids.append(child_id)
            # 递归获取子节点的子节点
            children_ids.extend(get_children_ids(data, child_id))
    return children_ids


def get_node_path(data: List[Dict[str, Any]], node_id: int) -> str:
    """获取节点的完整路径"""
    node = find_node_by_id(data, node_id)
    if not node:
        return ""

    path_parts = [node.get("name", "")]
    parent_id = node.get("parent_id")

    while parent_id is not None:
        parent = find_node_by_id(data, parent_id)
        if parent:
            path_parts.insert(0, parent.get("name", ""))
            parent_id = parent.get("parent_id")
        else:
            break

    return "/".join(path_parts)


def build_tree(data: List[Dict[str, Any]], parent_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """将扁平数据构建为树形结构"""
    tree = []

    for item in data:
        if item.get("parent_id") == parent_id:
            node = {
                "id": item.get("id"),
                "parent_id": item.get("parent_id"),
                "code": item.get("code", ""),
                "name": item.get("name", ""),
                "path": get_node_path(data, item.get("id")),
                "content": item.get("content", ""),
                "type": item.get("type", "folder"),  # 默认为 folder
                "children": build_tree(data, item.get("id"))
            }
            tree.append(node)

    return tree


# ==================== 路由接口 ====================

@router.post("/folder/create", response_model=BaseResponse, summary="创建文件夹")
async def create_folder(request: FolderCreateRequest):
    """
    创建文件夹

    Args:
        request: 创建文件夹请求
            - name: 文件夹名称
            - parent_id: 父节点ID（可选），不填则创建根节点

    Returns:
        创建结果
    """
    try:
        # 1. 验证文件夹名称
        if not request.name or not request.name.strip():
            return BaseResponse(
                success=False,
                errCode="FOLDER_001",
                errMsg="文件夹名称不能为空",
                data=None
            )

        # 2. 加载现有数据
        data = load_data()

        # 3. 检查父节点是否存在
        if request.parent_id is not None:
            parent_node = find_node_by_id(data, request.parent_id)
            if not parent_node:
                return BaseResponse(
                    success=False,
                    errCode="FOLDER_004",
                    errMsg=f"父节点 ID={request.parent_id} 不存在",
                    data=None
                )

        # 4. 检查同级是否有重名
        for item in data:
            if item.get("parent_id") == request.parent_id and item.get("name") == request.name:
                return BaseResponse(
                    success=False,
                    errCode="FOLDER_003",
                    errMsg=f"同级目录下已存在名为 '{request.name}' 的文件夹",
                    data=None
                )

        # 5. 创建新节点
        new_id = get_next_id(data)
        new_node = {
            "id": new_id,
            "parent_id": request.parent_id,
            "code": f"folder_{new_id}",
            "name": request.name,
            "content": ""
        }

        # 6. 添加到数据并保存
        data.append(new_node)
        save_data(data)

        # 7. 计算完整路径
        full_path = get_node_path(data, new_id)

        print(f"[Document System] Folder created: {full_path}")

        return BaseResponse(
            success=True,
            errCode=None,
            errMsg=None,
            data={
                "id": new_node["id"],
                "parent_id": new_node["parent_id"],
                "code": new_node["code"],
                "name": new_node["name"],
                "path": full_path,
                "content": ""
            }
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return BaseResponse(
            success=False,
            errCode="FOLDER_006",
            errMsg=f"创建文件夹失败: {str(e)}",
            data=None
        )


@router.post("/folder/delete", response_model=BaseResponse, summary="删除文件夹")
async def delete_folder(request: FolderDeleteRequest):
    """
    删除文件夹

    Args:
        request: 删除文件夹请求
            - id: 要删除的节点ID
            - force: 是否强制删除有子节点的文件夹

    Returns:
        删除结果
    """
    try:
        # 1. 加载数据
        data = load_data()

        # 2. 查找要删除的节点
        target_node = find_node_by_id(data, request.id)
        if not target_node:
            return BaseResponse(
                success=False,
                errCode="FOLDER_007",
                errMsg=f"节点 ID={request.id} 不存在",
                data=None
            )

        # 3. 获取完整路径（删除前）
        full_path = get_node_path(data, request.id)

        # 4. 检查是否有子节点
        children_ids = get_children_ids(data, request.id)
        if children_ids and not request.force:
            return BaseResponse(
                success=False,
                errCode="FOLDER_009",
                errMsg=f"文件夹 '{target_node.get('name')}' 不为空，包含 {len(children_ids)} 个子项。如需强制删除，请设置 force=true",
                data=None
            )

        # 5. 删除节点及其所有子节点
        ids_to_delete = {request.id} | set(children_ids)
        new_data = [item for item in data if item.get("id") not in ids_to_delete]

        # 6. 保存数据
        save_data(new_data)

        print(f"[Document System] Folder deleted: {full_path} (including {len(children_ids)} children)")

        return BaseResponse(
            success=True,
            errCode=None,
            errMsg=None,
            data={
                "id": target_node.get("id"),
                "parent_id": target_node.get("parent_id"),
                "code": target_node.get("code", ""),
                "name": target_node.get("name"),
                "path": full_path,
                "content": target_node.get("content", ""),
                "deleted_children_count": len(children_ids)
            }
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return BaseResponse(
            success=False,
            errCode="FOLDER_010",
            errMsg=f"删除文件夹失败: {str(e)}",
            data=None
        )


@router.post("/folder/update", response_model=BaseResponse, summary="修改文件夹名称")
async def update_folder(request: FolderUpdateRequest):
    """
    修改文件夹名称

    Args:
        request: 修改文件夹请求
            - id: 要修改的节点ID
            - name: 新名称

    Returns:
        修改结果
    """
    try:
        # 1. 验证名称
        if not request.name or not request.name.strip():
            return BaseResponse(
                success=False,
                errCode="FOLDER_001",
                errMsg="文件夹名称不能为空",
                data=None
            )

        # 2. 加载数据
        data = load_data()

        # 3. 查找要修改的节点
        target_node = None
        target_index = -1
        for i, item in enumerate(data):
            if item.get("id") == request.id:
                target_node = item
                target_index = i
                break

        if not target_node:
            return BaseResponse(
                success=False,
                errCode="FOLDER_007",
                errMsg=f"节点 ID={request.id} 不存在",
                data=None
            )

        # 4. 检查同级是否有重名
        parent_id = target_node.get("parent_id")
        for item in data:
            if (item.get("parent_id") == parent_id and
                item.get("name") == request.name and
                item.get("id") != request.id):
                return BaseResponse(
                    success=False,
                    errCode="FOLDER_003",
                    errMsg=f"同级目录下已存在名为 '{request.name}' 的文件夹",
                    data=None
                )

        # 5. 更新名称
        data[target_index]["name"] = request.name

        # 6. 保存数据
        save_data(data)

        # 7. 计算完整路径
        full_path = get_node_path(data, request.id)

        print(f"[Document System] Folder renamed: {full_path}")

        return BaseResponse(
            success=True,
            errCode=None,
            errMsg=None,
            data={
                "id": data[target_index]["id"],
                "parent_id": data[target_index]["parent_id"],
                "code": data[target_index].get("code", ""),
                "name": data[target_index]["name"],
                "path": full_path,
                "content": data[target_index].get("content", "")
            }
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return BaseResponse(
            success=False,
            errCode="FOLDER_012",
            errMsg=f"修改文件夹失败: {str(e)}",
            data=None
        )


@router.get("/folder/list", response_model=BaseResponse, summary="列出文件夹（树形结构）")
async def list_folders(parent_id: Optional[int] = None):
    """
    列出文件夹（返回树形结构）

    Args:
        parent_id: 父节点ID（可选）
            - 不传：返回所有根节点（parent_id=null 的节点）及其子树
            - 传入：返回该节点的直接子节点及其子树

    Returns:
        树形结构数据
    """
    try:
        # 1. 加载数据
        data = load_data()

        if not data:
            return BaseResponse(
                success=True,
                errCode=None,
                errMsg=None,
                data={"dataList": []}
            )

        # 2. 构建树形结构
        if parent_id is not None:
            # 检查父节点是否存在
            parent_node = find_node_by_id(data, parent_id)
            if not parent_node:
                return BaseResponse(
                    success=False,
                    errCode="FOLDER_007",
                    errMsg=f"节点 ID={parent_id} 不存在",
                    data=None
                )
            # 返回该节点的子节点
            tree_data = build_tree(data, parent_id)
        else:
            # 不传参数：返回根节点（parent_id=null）及其子树
            tree_data = build_tree(data, None)

        print(f"[Document System] Folder list loaded, total nodes: {len(data)}")

        return BaseResponse(
            success=True,
            errCode=None,
            errMsg=None,
            data={"dataList": tree_data}
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return BaseResponse(
            success=False,
            errCode="FOLDER_011",
            errMsg=f"列出文件夹失败: {str(e)}",
            data=None
        )


def get_folder_graph_data(folder_ids: List[int]) -> Dict[str, List[Dict[str, Any]]]:
    """
    获取指定文件夹列表对应的图数据（nodes + edges）

    Args:
        folder_ids: 文件夹 ID 列表

    Returns:
        包含 nodes 和 edges 的字典
    """
    all_nodes = []
    all_edges = []
    node_ids_seen = set()  # 用于去重

    doc_dir = get_document_system_dir() / "document"

    if not doc_dir.exists():
        return {"nodes": [], "edges": []}

    # 1. 先加载公共节点 标签节点.json
    label_file = doc_dir / "标签节点.json"
    if label_file.exists():
        try:
            with open(label_file, "r", encoding="utf-8") as f:
                label_data = json.load(f)
                for node in label_data.get("nodes", []):
                    node_id = node.get("id")
                    if node_id and node_id not in node_ids_seen:
                        all_nodes.append(node)
                        node_ids_seen.add(node_id)
                all_edges.extend(label_data.get("edges", []))
        except Exception as e:
            print(f"[Document System] Error loading 标签节点.json: {e}")

    # 2. 遍历所有 *_招标文件.json 文件
    for json_file in doc_dir.glob("*_招标文件.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                file_data = json.load(f)

            # 检查 document_id 是否在目标文件夹列表中
            metadata = file_data.get("metadata", {})
            doc_id = metadata.get("document_id")

            # document_id 可能是字符串或整数
            if doc_id is not None:
                doc_id_int = int(doc_id) if isinstance(doc_id, str) else doc_id
                if doc_id_int in folder_ids:
                    # 添加节点（去重）
                    for node in file_data.get("nodes", []):
                        node_id = node.get("id")
                        if node_id and node_id not in node_ids_seen:
                            all_nodes.append(node)
                            node_ids_seen.add(node_id)
                    # 添加边
                    all_edges.extend(file_data.get("edges", []))
        except Exception as e:
            print(f"[Document System] Error loading {json_file.name}: {e}")

    return {"nodes": all_nodes, "edges": all_edges}


def build_entity_tree(folder_ids: List[int]) -> List[Dict[str, Any]]:
    """
    构建实体树形结构（三层结构）

    层级结构：
    1. label (标签节点.json 中的节点，如 "项目类型")
    2. label_node_entity (中间聚合层，按 label_node_entity 字段值聚合，如 "货物类")
    3. 真实 node (招标文件中的具体节点)

    Args:
        folder_ids: 文件夹 ID 列表

    Returns:
        树形结构的节点列表
    """
    doc_dir = get_document_system_dir() / "document"

    if not doc_dir.exists():
        return []

    # 1. 加载 标签节点.json 作为根节点 (第一层: label)
    root_nodes = {}  # id -> node
    label_file = doc_dir / "标签节点.json"
    if label_file.exists():
        try:
            with open(label_file, "r", encoding="utf-8") as f:
                label_data = json.load(f)
                for node in label_data.get("nodes", []):
                    node_id = node.get("id")
                    if node_id:
                        root_nodes[node_id] = {
                            **node,
                            "children": []
                        }
        except Exception as e:
            print(f"[Document System] Error loading 标签节点.json: {e}")

    # 2. 收集所有子节点和边
    all_child_nodes = {}  # id -> node
    all_edges = []

    # 查找 *_招标文件.json 和 *_合同.json 文件
    file_patterns = ["*_招标文件.json", "*_合同.json"]

    for pattern in file_patterns:
        for json_file in doc_dir.glob(pattern):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    file_data = json.load(f)

                # 检查 document_id 是否在目标文件夹列表中
                metadata = file_data.get("metadata", {})
                doc_id = metadata.get("document_id")

                if doc_id is not None:
                    doc_id_int = int(doc_id) if isinstance(doc_id, str) else doc_id
                    if doc_id_int in folder_ids:
                        # 收集节点
                        for node in file_data.get("nodes", []):
                            node_id = node.get("id")
                            if node_id and node_id not in root_nodes:
                                node_data = {
                                    **node,
                                    "children": []
                                }
                                # 当节点 type 为 attribute 时，添加 metadata 字段
                                if node.get("type") == "attribute":
                                    node_data["metadata"] = metadata
                                all_child_nodes[node_id] = node_data
                        # 收集边
                        all_edges.extend(file_data.get("edges", []))
            except Exception as e:
                print(f"[Document System] Error loading {json_file.name}: {e}")

    # 3. 根据 edges 构建三层结构
    # edge.from 是 label 节点 id (第一层)
    # 子节点的 label_node_entity 用于创建中间聚合层 (第二层)
    # 子节点本身是真实节点 (第三层)

    # 为每个 root_node 创建 label_node_entity 聚合字典
    # 结构: root_node_id -> { label_node_entity_value -> aggregated_node }
    entity_aggregation = {}  # root_id -> { entity_value -> { node_data, children: [real_nodes] } }

    for edge in all_edges:
        from_id = edge.get("from")
        to_id = edge.get("to")

        if from_id and to_id:
            # 找父节点（在 root_nodes 中查找，第一层）
            parent_node = root_nodes.get(from_id)
            # 找子节点（真实节点，第三层）
            child_node = all_child_nodes.get(to_id)

            if parent_node and child_node:
                # 获取 label_node_entity 值用于聚合（第二层）
                entity_value = child_node.get("label_node_entity", "未分类")

                # 初始化聚合结构
                if from_id not in entity_aggregation:
                    entity_aggregation[from_id] = {}

                if entity_value not in entity_aggregation[from_id]:
                    # 创建中间聚合节点 (第二层)
                    entity_aggregation[from_id][entity_value] = {
                        "id": f"{from_id}_{entity_value}",
                        "label": entity_value,
                        "type": "aggregate",
                        "children": []
                    }

                # 将真实节点添加到聚合节点的 children 中（第三层）
                # 检查是否已添加（避免重复）
                exists = any(c.get("id") == to_id for c in entity_aggregation[from_id][entity_value]["children"])
                if not exists:
                    entity_aggregation[from_id][entity_value]["children"].append(child_node)

    # 4. 将聚合节点挂载到根节点的 children 中
    for root_id, entity_dict in entity_aggregation.items():
        if root_id in root_nodes:
            root_nodes[root_id]["children"] = list(entity_dict.values())

    # 5. 返回根节点列表
    return list(root_nodes.values())


@router.get("/folder/entity", response_model=BaseResponse, summary="获取文件夹实体节点（树形结构）")
async def get_folder_entity(folder_id: int):
    """
    获取指定文件夹及其所有子文件夹的实体节点（树形结构）

    以 标签节点.json 中的节点为根节点，
    根据 edges 的 from 字段将其他节点挂载为 children

    Args:
        folder_id: 文件夹ID

    Returns:
        树形结构的节点数据
    """
    try:
        # 1. 加载文件夹数据
        data = load_data()

        # 2. 检查文件夹是否存在
        folder_node = find_node_by_id(data, folder_id)
        if not folder_node:
            return BaseResponse(
                success=False,
                errCode="FOLDER_007",
                errMsg=f"文件夹 ID={folder_id} 不存在",
                data=None
            )

        # 3. 获取所有子文件夹 ID（包括自身）
        children_ids = get_children_ids(data, folder_id)
        all_folder_ids = [folder_id] + children_ids

        # 4. 构建树形结构
        tree_data = build_entity_tree(all_folder_ids)

        print(f"[Document System] Entity tree query for folder {folder_id}: {len(tree_data)} root nodes")

        return BaseResponse(
            success=True,
            errCode=None,
            errMsg=None,
            data={"dataList": tree_data}
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return BaseResponse(
            success=False,
            errCode="ENTITY_001",
            errMsg=f"获取实体节点失败: {str(e)}",
            data=None
        )


@router.get("/folder/graph", response_model=BaseResponse, summary="获取文件夹图数据")
async def get_folder_graph(folder_id: int):
    """
    获取图数据

    直接读取 graph.jsonl 文件返回

    Args:
        folder_id: 文件夹ID

    Returns:
        graph.jsonl 中的图数据
    """
    try:
        # 1. 加载文件夹数据，验证 folder_id 是否存在
        data = load_data()
        folder_node = find_node_by_id(data, folder_id)
        if not folder_node:
            return BaseResponse(
                success=False,
                errCode="FOLDER_007",
                errMsg=f"文件夹 ID={folder_id} 不存在",
                data=None
            )

        # 2. 读取 graph.jsonl 文件
        doc_dir = get_document_system_dir() / "document"
        graph_file = doc_dir / "graph.jsonl"

        if not graph_file.exists():
            return BaseResponse(
                success=True,
                errCode=None,
                errMsg=None,
                data={"elements": {"nodes": [], "edges": []}}
            )

        with open(graph_file, "r", encoding="utf-8") as f:
            content = f.read()

        # 去除 JSON 中的注释 (/* ... */ 和 // ...)
        import re
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        content = re.sub(r'//.*?$', '', content, flags=re.MULTILINE)

        graph_data = json.loads(content)

        print(f"[Document System] Graph query for folder {folder_id}")

        return BaseResponse(
            success=True,
            errCode=None,
            errMsg=None,
            data=graph_data
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return BaseResponse(
            success=False,
            errCode="GRAPH_001",
            errMsg=f"获取图数据失败: {str(e)}",
            data=None
        )


@router.post("/file/upload", response_model=BaseResponse, summary="上传文件")
async def upload_file(
    file: UploadFile = File(..., description="要上传的文件"),
    parent_id: int = Form(..., description="目标文件夹ID")
):
    """
    上传文件到指定文件夹

    Args:
        file: 上传的文件
        parent_id: 目标文件夹ID

    Returns:
        上传结果
    """
    try:
        # 1. 加载数据
        data = load_data()

        # 2. 检查目标文件夹是否存在
        folder_node = find_node_by_id(data, parent_id)
        if not folder_node:
            return BaseResponse(
                success=False,
                errCode="FILE_001",
                errMsg=f"目标文件夹 ID={parent_id} 不存在",
                data=None
            )

        # 3. 获取文件名
        filename = file.filename
        if not filename:
            return BaseResponse(
                success=False,
                errCode="FILE_002",
                errMsg="文件名不能为空",
                data=None
            )

        # 4. 创建文件节点
        new_id = get_next_id(data)
        new_node = {
            "id": new_id,
            "parent_id": parent_id,
            "code": f"file_{new_id}",
            "name": filename,
            "content": "",
            "type": "file"
        }

        # 5. 添加到数据并保存
        data.append(new_node)
        save_data(data)

        # 6. 计算完整路径
        full_path = get_node_path(data, new_id)

        print(f"[Document System] File uploaded: {full_path}")

        return BaseResponse(
            success=True,
            errCode=None,
            errMsg=None,
            data={
                "id": new_node["id"],
                "parent_id": new_node["parent_id"],
                "code": new_node["code"],
                "name": new_node["name"],
                "path": full_path,
                "type": "file"
            }
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return BaseResponse(
            success=False,
            errCode="FILE_003",
            errMsg=f"上传文件失败: {str(e)}",
            data=None
        )