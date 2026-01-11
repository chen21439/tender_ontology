"""
PDF 上传路由

只提供 PDF 文件上传和数据库记录管理功能
表格提取和向量化由 Docling 处理

存储模式：
- STORAGE_MODE=mysql (默认): 使用 MySQL 数据库
- STORAGE_MODE=local: 使用本地 JSON 文件
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from typing import Optional
from pathlib import Path
import uuid
from datetime import datetime
import shutil
import asyncio

from tender_ontology.models.pdf_task import (
    PDFProcessResponse,
    TaskStatusResponse,
    PageRequest,
    PageResponse,
    PageDataResponse,
    ConstructUpdateRequest
)
from tender_ontology.utils.db.local_storage import is_local_mode, get_local_storage

# 创建路由
router = APIRouter(tags=["PDF上传"])


# ==================== 辅助函数 ====================

def generate_task_id() -> str:
    """
    生成任务ID (20位字符串)

    Returns:
        任务ID (格式: 时间戳12位 + 随机数8位)
    """
    timestamp = datetime.now().strftime("%y%m%d%H%M%S")  # 12位
    random_part = str(uuid.uuid4().int)[:8]  # 8位随机数
    return timestamp + random_part


def get_static_upload_dir() -> Path:
    """
    获取 static/upload 目录路径

    Returns:
        static/upload 目录的 Path 对象
    """
    # 获取项目根目录 (tender_ontology/)
    current_file = Path(__file__)  # .../routers/pdf_upload.py
    project_root = current_file.parent.parent.parent.parent  # 向上4级
    static_upload = project_root / "static" / "upload"
    static_upload.mkdir(parents=True, exist_ok=True)
    return static_upload


def get_task_upload_dir(task_id: str) -> Path:
    """
    获取指定任务的上传目录路径

    Args:
        task_id: 任务ID

    Returns:
        static/upload/{task_id} 目录的 Path 对象
    """
    static_upload = get_static_upload_dir()
    task_dir = static_upload / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


# ==================== 路由接口 ====================

@router.post("/upload_pdf", response_model=PDFProcessResponse, summary="上传PDF/DOCX文件")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF或DOCX文件"),
    project_name: Optional[str] = Form(None, description="项目名称"),
    project_code: Optional[str] = Form(None, description="项目编号"),
    procurement_method: Optional[str] = Form(None, description="采购方式"),
    project_type: Optional[str] = Form(None, description="项目类型"),
    overview: Optional[str] = Form(None, description="项目概述"),
    app_id: Optional[str] = Form(None, description="租户ID"),
    create_user: Optional[str] = Form(None, description="创建用户ID"),
    create_user_name: Optional[str] = Form(None, description="创建用户名称"),
    enable_docling: bool = Form(True, description="是否启用 Docling 自动处理，默认True")
):
    """
    上传 PDF 或 DOCX 文件

    功能:
    1. 接收 PDF/DOCX 文件上传
    2. 生成唯一任务ID
    3. 保存文件到 static/upload/{task_id}/{原文件名}
    4. 创建任务记录（本地存储或MySQL）
    5. 根据文件类型自动分发到不同处理器:
       - PDF: Docling 处理
       - DOCX: Unstructured + 二次判定处理

    返回:
        任务ID和处理结果
    """
    try:
        # 1. 验证文件类型
        filename_lower = file.filename.lower()
        if not (filename_lower.endswith('.pdf') or filename_lower.endswith('.docx')):
            return PDFProcessResponse(
                success=False,
                errCode="FILE_001",
                errMsg="只支持 PDF 和 DOCX 文件",
                data=None
            )

        # 判断文件类型
        file_type = "pdf" if filename_lower.endswith('.pdf') else "docx"

        print(f"[File Upload] ========== Start ==========")
        print(f"[File Upload] Filename: {file.filename}")
        print(f"[File Upload] Type: {file_type}")
        print(f"[File Upload] Project: {project_name or 'None'}")
        print(f"[File Upload] ================================")

        # 2. 创建任务记录，获取任务ID（作为唯一标识）
        task_id = None
        db_task_id = None

        if is_local_mode():
            # 本地存储模式
            try:
                storage = get_local_storage()
                task = storage.create_task(
                    file_name=file.filename,
                    file_path=None,  # 稍后更新
                    project_name=project_name,
                    project_code=project_code,
                    procurement_method=procurement_method,
                    project_type=project_type,
                    overview=overview,
                    app_id=app_id,
                    create_user=create_user,
                    create_user_name=create_user_name
                )
                db_task_id = task["id"]
                task_id = str(db_task_id)
                print(f"[PDF Upload] Local storage record created, task_id: {task_id}")
            except Exception as e:
                print(f"[PDF Upload] Local storage save failed: {e}")
                import traceback
                traceback.print_exc()
                task_id = generate_task_id()
                print(f"[PDF Upload] Using generated task_id: {task_id}")
        else:
            # MySQL 模式
            try:
                from tender_ontology.utils.db.mysql import get_db, ComplianceService

                # 使用全局数据库连接池
                mysql = get_db()

                # 创建合规审查任务（状态：解析中 = 3）
                service = ComplianceService(mysql)
                db_task = service.create_task_from_pdf(
                    pdf_path=None,  # 稍后更新
                    file_id=None,  # 自动生成
                    project_name=project_name,
                    project_code=project_code,
                    procurement_method=procurement_method,
                    project_type=project_type,
                    overview=overview,
                    app_id=app_id,
                    create_user=create_user,
                    create_user_name=create_user_name
                )

                db_task_id = db_task.id
                task_id = str(db_task_id)  # 使用数据库ID作为任务ID
                print(f"[PDF Upload] DB record created, task_id: {task_id}")

            except Exception as e:
                print(f"[PDF Upload] DB save failed: {e}")
                import traceback
                traceback.print_exc()
                # 如果数据库创建失败，使用生成的ID
                task_id = generate_task_id()
                print(f"[PDF Upload] Using generated task_id: {task_id}")

        # 3. 保存 PDF 文件到 static/upload/{task_id}/ 目录
        task_dir = get_task_upload_dir(task_id)
        pdf_filename = file.filename  # 保留原始文件名
        pdf_path = task_dir / pdf_filename

        with open(pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        print(f"[PDF Upload] PDF saved: {pdf_path}")

        # 4. 更新任务记录的文件路径
        if db_task_id:
            if is_local_mode():
                # 本地存储模式
                try:
                    storage = get_local_storage()
                    relative_path = str(pdf_path.relative_to(task_dir.parent.parent))
                    storage.update_task_file_path(db_task_id, relative_path, file.filename)
                    print(f"[PDF Upload] Local storage file path updated")
                except Exception as e:
                    print(f"[PDF Upload] Local storage update failed: {e}")
            else:
                # MySQL 模式
                try:
                    from tender_ontology.utils.db.mysql import get_db
                    from tender_ontology.utils.db.mysql.models import ComplianceFileTask

                    # 使用全局数据库连接池
                    mysql = get_db()

                    # 更新任务的文件路径和文件名
                    with mysql.get_session() as session:
                        task = session.query(ComplianceFileTask).filter(
                            ComplianceFileTask.id == db_task_id
                        ).first()

                        if task:
                            # 更新文件路径（相对路径 static/upload/{task_id}/{filename}）
                            task.file_path = str(pdf_path.relative_to(task_dir.parent.parent))
                            # 更新文件名
                            if not task.file_name:
                                task.file_name = file.filename
                            session.commit()
                            print(f"[PDF Upload] DB file path updated")

                except Exception as e:
                    print(f"[PDF Upload] DB update failed: {e}")

        # 5. 触发后台处理（如果启用）
        # 使用 FileService 统一入口，根据文件类型自动分发
        if enable_docling:
            from tender_ontology.services.file_service import get_file_service

            # 获取文件服务
            file_service = get_file_service()

            # 异步处理（后台线程）
            file_service.process_file(
                file_path=pdf_path,
                task_id=task_id,
                db_task_id=db_task_id,
                output_dir=task_dir,
                async_mode=True
            )

            print(f"[File Upload] Background processing started for task_id: {task_id}")
            print(f"[File Upload] File type: {file_type}")
            print(f"[File Upload] Output directory: {task_dir}")

        # 6. 构建响应
        response_data = {
            "taskId": task_id,
            "docId": task_id,  # 使用相同的ID
            "dbTaskId": db_task_id,
            "filePath": str(pdf_path),
            "fileName": file.filename,
            "fileType": file_type,
            "projectName": project_name,
            "savedToDb": db_task_id is not None,
            "processingEnabled": enable_docling,
            "message": f"{file_type.upper()} 上传成功" + (f", 后台处理中..." if enable_docling else "")
        }

        return PDFProcessResponse(
            success=True,
            errCode=None,
            errMsg=None,
            data=response_data
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return PDFProcessResponse(
            success=False,
            errCode="PDF_002",
            errMsg=f"处理失败: {str(e)}",
            data=None
        )


@router.get("/task/{task_id}", response_model=TaskStatusResponse, summary="查询任务状态")
async def get_task_status(task_id: str):
    """
    查询任务状态

    Args:
        task_id: 任务ID (数据库中的主键)

    Returns:
        任务状态信息
    """
    try:
        if is_local_mode():
            # 本地存储模式
            storage = get_local_storage()
            task = storage.get_task(task_id)

            if not task:
                return TaskStatusResponse(
                    success=False,
                    errCode="TASK_001",
                    errMsg=f"任务 {task_id} 不存在",
                    data=None
                )

            return TaskStatusResponse(
                success=True,
                errCode=None,
                errMsg=None,
                data={
                    "taskId": task["id"],
                    "status": "completed" if task["review_status"] == 2 else "processing",
                    "reviewStatus": task["review_status"],
                    "reviewResult": task["review_result"],
                    "fileName": task["file_name"],
                    "projectName": task["project_name"],
                    "createdAt": task["create_time"]
                }
            )
        else:
            # MySQL 模式
            from tender_ontology.utils.db.mysql import get_db, ComplianceService

            # 使用全局数据库连接池
            mysql = get_db()

            # 查询任务
            service = ComplianceService(mysql)
            task = service.get_task(task_id)

            if not task:
                return TaskStatusResponse(
                    success=False,
                    errCode="TASK_001",
                    errMsg=f"任务 {task_id} 不存在",
                    data=None
                )

            return TaskStatusResponse(
                success=True,
                errCode=None,
                errMsg=None,
                data={
                    "taskId": task.id,
                    "status": "completed" if task.review_status == 2 else "processing",
                    "reviewStatus": task.review_status,
                    "reviewResult": task.review_result,
                    "fileName": task.file_name,
                    "projectName": task.project_name,
                    "createdAt": task.create_time.strftime("%Y-%m-%d %H:%M:%S") if task.create_time else None
                }
            )

    except Exception as e:
        return TaskStatusResponse(
            success=False,
            errCode="TASK_002",
            errMsg=f"查询失败: {str(e)}",
            data=None
        )


@router.post("/page", response_model=PageResponse, summary="分页查询任务列表")
async def get_tasks_by_page(request: PageRequest):
    """
    分页查询任务列表

    Args:
        request: 分页请求参数
            - pageNum: 页码（从1开始）
            - pageSize: 每页数量

    Returns:
        分页数据
    """
    try:
        # 参数验证
        page_num = max(1, request.pageNum)
        page_size = min(max(1, request.pageSize), 100)  # 限制最大100条

        if is_local_mode():
            # 本地存储模式
            storage = get_local_storage()
            page_data = storage.get_tasks_page(page_num, page_size)

            return PageResponse(
                success=True,
                errCode=None,
                errMsg=None,
                data=PageDataResponse(
                    total=str(page_data["total"]),
                    pageSize=str(page_data["pageSize"]),
                    pageTotal=str(page_data["pageTotal"]),
                    pageNum=str(page_data["pageNum"]),
                    dataList=page_data["dataList"]
                )
            )
        else:
            # MySQL 模式
            from tender_ontology.utils.db.mysql import get_db
            from tender_ontology.utils.db.mysql.models import ComplianceFileTask
            from sqlalchemy import func

            # 使用全局数据库连接池
            mysql = get_db()

            # 使用 get_session() 进行查询
            with mysql.get_session() as session:
                # 查询总数
                total = session.query(func.count(ComplianceFileTask.id)).scalar()

                # 分页查询
                offset = (page_num - 1) * page_size
                tasks = session.query(ComplianceFileTask)\
                    .order_by(ComplianceFileTask.create_time.desc())\
                    .limit(page_size)\
                    .offset(offset)\
                    .all()

                # 计算总页数
                pages = (total + page_size - 1) // page_size if total > 0 else 1

                # 转换为字典列表（驼峰命名）
                data_list = []
                for task in tasks:
                    # 计算审查进度
                    review_progress = 100 if task.review_status == 2 else 0

                    data_list.append({
                        "taskId": task.id,
                        "fileId": task.file_id,
                        "fileName": task.file_name,
                        "projectName": task.project_name,
                        "projectCode": task.project_code,
                        "reviewStatus": task.review_status,
                        "reviewResult": task.review_result,
                        "createTime": task.create_time.strftime("%Y-%m-%d %H:%M:%S") if task.create_time else None,
                        "createUserName": task.create_user_name,
                        "reviewProgress": review_progress
                    })

            return PageResponse(
                success=True,
                errCode=None,
                errMsg=None,
                data=PageDataResponse(
                    total=str(total),
                    pageSize=str(page_size),
                    pageTotal=str(pages),
                    pageNum=str(page_num),
                    dataList=data_list
                )
            )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return PageResponse(
            success=False,
            errCode="PAGE_001",
            errMsg=f"分页查询失败: {str(e)}",
            data=PageDataResponse(
                total="0",
                pageSize=str(request.pageSize),
                pageTotal="0",
                pageNum=str(request.pageNum),
                dataList=[]
            )
        )


@router.get("/task/{task_id}/pdf", summary="下载任务PDF文件")
async def download_task_pdf(task_id: str):
    """
    根据任务ID下载对应的PDF文件

    Args:
        task_id: 任务ID

    Returns:
        PDF 文件流
    """
    try:
        # 构建PDF文件路径 - 从 static/upload/{task_id}/ 目录查找
        task_dir = get_task_upload_dir(task_id)

        # 查找目录中的PDF文件（假设每个任务目录只有一个PDF）
        pdf_files = list(task_dir.glob("*.pdf"))

        if not pdf_files:
            raise HTTPException(status_code=404, detail=f"任务 {task_id} 的PDF文件不存在")

        pdf_path = pdf_files[0]  # 取第一个PDF文件

        # 返回文件
        return FileResponse(
            path=str(pdf_path),
            filename=pdf_path.name,  # 使用原始文件名
            media_type="application/pdf"
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")


@router.get("/task/{task_id}/result", summary="获取任务处理结果")
async def get_task_result(
    task_id: str,
    result_type: str = "markdown"
):
    """
    获取任务的 Docling 处理结果

    Args:
        task_id: 任务ID
        result_type: 结果类型，支持: pdf, markdown, markdown_json, json, labeled, headers, model, fulltext, agent, level12, forward, ontology

    Returns:
        处理结果文件内容
    """
    try:
        # 构建任务目录路径
        task_dir = get_task_upload_dir(task_id)

        # 根据类型查找对应的文件
        file_patterns = {
            "pdf": "*.pdf",
            "markdown": "*.md",
            "markdown_json": "*_markdown.json",
            "json": "*_[0-9]*.json",  # 匹配带时间戳的 JSON 文件（排除 labeled 和 headers）
            "labeled": "*_labeled.json",
            "headers": "*_headers.json",
            "model": "*_model.json",
            "fulltext": "*_fulltext.json",
            "agent": "*_agent.json",  # 内部调用生成的结构化数据
            "level12": "*_level12.json",
            "forward": "*_forward.json",
            "ontology": "*_ontology.json",  # extract_onto API 返回的结果
            "construct": "*_construct.json"  # 知识图谱构建结果
        }

        if result_type not in file_patterns:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的结果类型: {result_type}，支持的类型: {', '.join(file_patterns.keys())}"
            )

        pattern = file_patterns[result_type]
        result_files = list(task_dir.glob(pattern))

        # 对于 json 类型，需要排除 labeled 和 headers
        if result_type == "json":
            result_files = [
                f for f in result_files
                if not (f.name.endswith("_labeled.json") or f.name.endswith("_headers.json"))
            ]

        # 对于 agent 类型，如果 _agent.json 不存在，回退到 _forward.json
        if result_type == "agent" and not result_files:
            result_files = list(task_dir.glob("*_forward.json"))

        if not result_files:
            raise HTTPException(
                status_code=404,
                detail=f"任务 {task_id} 的 {result_type} 结果文件不存在"
            )

        # 取最新的文件（按修改时间排序）
        result_file = sorted(result_files, key=lambda f: f.stat().st_mtime, reverse=True)[0]

        # 根据类型返回不同的响应
        if result_type == "pdf":
            # 返回 PDF 文件（文件下载，不使用统一格式）
            return FileResponse(
                path=str(result_file),
                filename=result_file.name,
                media_type="application/pdf"
            )
        elif result_type == "markdown":
            # 返回 markdown 文本（纯文本，不使用统一格式）
            from fastapi.responses import PlainTextResponse
            content = result_file.read_text(encoding='utf-8')
            return PlainTextResponse(content=content, media_type="text/markdown")
        else:
            # 返回 JSON 数据（使用统一格式）
            import json
            content = result_file.read_text(encoding='utf-8')
            json_data = json.loads(content)

            # ontology 类型特殊处理：提取 data 数组
            if result_type == "ontology" and isinstance(json_data, dict) and "data" in json_data:
                json_data = {"dataList": json_data["data"]}
            # construct 类型特殊处理：提取 predictions 数组
            elif result_type == "construct" and isinstance(json_data, dict) and "predictions" in json_data:
                json_data = {"dataList": json_data["predictions"]}
            # 如果 json_data 是数组（如 agent、model、markdown_json），包装成字典
            elif isinstance(json_data, list):
                json_data = {"dataList": json_data}

            return PDFProcessResponse(
                success=True,
                errCode=None,
                errMsg=None,
                data=json_data
            )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"获取结果失败: {str(e)}")




@router.put("/task/{task_id}/ontology", response_model=PDFProcessResponse, summary="上传替换ontology文件")
async def upload_ontology(
    task_id: str,
    file: UploadFile = File(..., description="ontology JSON文件")
):
    """
    上传并替换任务的 ontology.json 文件

    Args:
        task_id: 任务ID
        file: 新的 ontology JSON 文件

    Returns:
        替换结果
    """
    try:
        # 验证文件类型
        if not file.filename.endswith('.json'):
            return PDFProcessResponse(
                success=False,
                errCode="FILE_001",
                errMsg="只支持 JSON 文件",
                data=None
            )

        # 获取任务目录
        task_dir = get_task_upload_dir(task_id)

        # 查找现有的 ontology 文件
        ontology_files = list(task_dir.glob("*_ontology.json"))

        if not ontology_files:
            return PDFProcessResponse(
                success=False,
                errCode="FILE_002",
                errMsg=f"任务 {task_id} 的 ontology 文件不存在",
                data=None
            )

        # 获取最新的 ontology 文件路径（用于替换）
        target_file = sorted(ontology_files, key=lambda f: f.stat().st_mtime, reverse=True)[0]

        # 读取上传的文件内容并验证是否为有效 JSON
        import json
        content = await file.read()
        try:
            json_data = json.loads(content.decode('utf-8'))
        except json.JSONDecodeError as e:
            return PDFProcessResponse(
                success=False,
                errCode="FILE_003",
                errMsg=f"无效的 JSON 文件: {str(e)}",
                data=None
            )

        # 写入文件（替换原有内容）
        with open(target_file, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        return PDFProcessResponse(
            success=True,
            errCode=None,
            errMsg=None,
            data={
                "taskId": task_id,
                "fileName": target_file.name,
                "message": "ontology 文件替换成功"
            }
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return PDFProcessResponse(
            success=False,
            errCode="FILE_004",
            errMsg=f"替换失败: {str(e)}",
            data=None
        )


@router.post("/task/{task_id}/construct", response_model=PDFProcessResponse, summary="修改construct条目")
async def update_construct_item(
    task_id: str,
    request: ConstructUpdateRequest
):
    """
    修改任务的 construct.json 中的条目

    通过 line_id 查找对应元素，更新 class、parent_id、relation 字段

    Args:
        task_id: 任务ID
        request: 修改请求
            - lineId: 通过 line_id 查找元素（必填）
            - className: 要修改的 class（可选）
            - parentId: 要修改的 parent_id（可选）
            - relation: 要修改的 relation（可选）

    Returns:
        修改结果
    """
    try:
        import json

        # 获取任务目录
        task_dir = get_task_upload_dir(task_id)

        # 查找 construct 文件
        construct_files = list(task_dir.glob("*_construct.json"))

        if not construct_files:
            return PDFProcessResponse(
                success=False,
                errCode="FILE_001",
                errMsg=f"任务 {task_id} 的 construct 文件不存在",
                data=None
            )

        # 获取最新的 construct 文件
        target_file = sorted(construct_files, key=lambda f: f.stat().st_mtime, reverse=True)[0]

        # 读取文件内容
        with open(target_file, 'r', encoding='utf-8') as f:
            json_data = json.load(f)

        # 查找 predictions 数组中 line_id 匹配的元素
        predictions = json_data.get("predictions", [])

        # 构建 line_id -> item 的映射，便于快速查找
        line_id_map = {item.get("line_id"): item for item in predictions}

        # 查找目标元素
        if request.lineId not in line_id_map:
            return PDFProcessResponse(
                success=False,
                errCode="ITEM_001",
                errMsg=f"未找到 line_id={request.lineId} 的条目",
                data=None
            )

        target_item = line_id_map[request.lineId]

        # 校验 parent_id
        if request.parentId is not None:
            # 校验1: parent_id 不能指向自身
            if request.parentId == request.lineId:
                return PDFProcessResponse(
                    success=False,
                    errCode="VALID_001",
                    errMsg=f"parent_id 不能指向自身 (line_id={request.lineId})",
                    data=None
                )

            # 校验2: 检测循环引用
            # 从新的 parent_id 开始，沿着 parent 链向上查找，如果遇到当前 line_id 则存在循环
            visited = set()
            current_id = request.parentId

            while current_id is not None and current_id != 0:
                # 如果回到了当前要修改的元素，说明存在循环
                if current_id == request.lineId:
                    return PDFProcessResponse(
                        success=False,
                        errCode="VALID_002",
                        errMsg=f"检测到循环引用: 设置 parent_id={request.parentId} 会导致循环",
                        data=None
                    )

                # 防止无限循环（数据本身已有循环的情况）
                if current_id in visited:
                    break
                visited.add(current_id)

                # 查找当前元素的 parent
                current_item = line_id_map.get(current_id)
                if current_item is None:
                    break
                current_id = current_item.get("parent_id")

        # 更新字段（只更新传递了值的字段）
        if request.className is not None:
            target_item["class"] = request.className
        if request.parentId is not None:
            target_item["parent_id"] = request.parentId
        if request.relation is not None:
            target_item["relation"] = request.relation

        updated_item = target_item

        # 保存修改后的文件
        with open(target_file, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        return PDFProcessResponse(
            success=True,
            errCode=None,
            errMsg=None,
            data={
                "taskId": task_id,
                "lineId": request.lineId,
                "updatedItem": updated_item,
                "message": "construct 条目修改成功"
            }
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return PDFProcessResponse(
            success=False,
            errCode="UPDATE_001",
            errMsg=f"修改失败: {str(e)}",
            data=None
        )


# 训练数据目录
TRAIN_DATA_DIR = Path("/data/LLM_group/layoutlmft/data/tender_document/train")


@router.get("/train/search", response_model=PDFProcessResponse, summary="搜索训练数据文件")
async def search_train_files(keyword: str):
    """
    根据关键词模糊搜索训练数据文件

    Args:
        keyword: 搜索关键词

    Returns:
        匹配的文件名列表
    """
    try:
        if not TRAIN_DATA_DIR.exists():
            return PDFProcessResponse(
                success=False,
                errCode="DIR_001",
                errMsg=f"训练数据目录不存在: {TRAIN_DATA_DIR}",
                data=None
            )

        # 搜索所有 json 文件，模糊匹配文件名
        matched_files = []
        for json_file in TRAIN_DATA_DIR.glob("*.json"):
            if keyword in json_file.stem:  # stem 是不带扩展名的文件名
                matched_files.append(json_file.name)

        return PDFProcessResponse(
            success=True,
            errCode=None,
            errMsg=None,
            data={
                "keyword": keyword,
                "total": len(matched_files),
                "dataList": matched_files
            }
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return PDFProcessResponse(
            success=False,
            errCode="SEARCH_001",
            errMsg=f"搜索失败: {str(e)}",
            data=None
        )


@router.delete("/task/{task_id}", response_model=PDFProcessResponse, summary="删除任务")
async def delete_task(task_id: str):
    """
    删除任务及其所有相关文件

    Args:
        task_id: 任务ID

    Returns:
        删除结果
    """
    try:
        # 1. 删除数据库/存储记录
        db_deleted = False
        if is_local_mode():
            # 本地存储模式
            try:
                storage = get_local_storage()
                db_deleted = storage.delete_task(task_id)
            except Exception as e:
                print(f"[Task Delete] Local storage delete failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            # MySQL 模式
            try:
                from tender_ontology.utils.db.mysql import get_db
                from tender_ontology.utils.db.mysql.models import ComplianceFileTask

                # 使用全局数据库连接池
                mysql = get_db()

                with mysql.get_session() as session:
                    task = session.query(ComplianceFileTask).filter(
                        ComplianceFileTask.id == task_id
                    ).first()

                    if task:
                        session.delete(task)
                        session.commit()
                        db_deleted = True
                        print(f"[Task Delete] DB record deleted for task_id: {task_id}")

            except Exception as e:
                print(f"[Task Delete] DB delete failed: {e}")
                import traceback
                traceback.print_exc()

        # 2. 删除文件目录
        files_deleted = False
        try:
            task_dir = get_task_upload_dir(task_id)

            if task_dir.exists():
                shutil.rmtree(task_dir)
                files_deleted = True
                print(f"[Task Delete] Files deleted: {task_dir}")

        except Exception as e:
            print(f"[Task Delete] Files delete failed: {e}")
            import traceback
            traceback.print_exc()

        # 3. 构建响应
        if not db_deleted and not files_deleted:
            return PDFProcessResponse(
                success=False,
                errCode="DELETE_001",
                errMsg=f"任务 {task_id} 不存在或已被删除",
                data=None
            )

        return PDFProcessResponse(
            success=True,
            errCode=None,
            errMsg=None,
            data={
                "taskId": task_id,
                "dbDeleted": db_deleted,
                "filesDeleted": files_deleted,
                "message": "任务删除成功"
            }
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return PDFProcessResponse(
            success=False,
            errCode="DELETE_002",
            errMsg=f"删除失败: {str(e)}",
            data=None
        )