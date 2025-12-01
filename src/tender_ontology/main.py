"""
FastAPI application entry point for tender ontology service.
"""

from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from tender_ontology.routers import health, ontology, pdf_upload, knowledge_graph
from tender_ontology.utils.db.local_storage import is_local_mode


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理

    启动时初始化数据库连接池（仅在 MySQL 模式），关闭时释放
    """
    if is_local_mode():
        # 本地模式：使用 JSON 文件存储，不需要数据库
        print("[Startup] Running in LOCAL storage mode (using JSON file)")
        from tender_ontology.utils.db.local_storage import get_local_storage
        get_local_storage()  # 初始化本地存储
    else:
        # MySQL 模式：初始化数据库连接池
        print("[Startup] Running in MySQL storage mode")
        from tender_ontology.utils.db.mysql import init_db, close_db
        init_db()

    yield

    # 关闭时：释放数据库连接池（仅在 MySQL 模式）
    if not is_local_mode():
        from tender_ontology.utils.db.mysql import close_db
        close_db()


app = FastAPI(
    title="Tender Ontology API",
    description="API for managing tender/bid ontology and knowledge graph",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers - 直接路径
app.include_router(health.router, tags=["health"])
app.include_router(ontology.router, tags=["ontology"])
app.include_router(pdf_upload.router, prefix="/api/pdf", tags=["PDF上传"])
app.include_router(knowledge_graph.router, prefix="/api/knowledge", tags=["知识图谱"])

# 兼容 nginx 转发路径 /python/...
# 所有 API 都可以通过 /python/... 访问
app.include_router(health.router, prefix="/python", tags=["health(兼容)"])
app.include_router(ontology.router, prefix="/python", tags=["ontology(兼容)"])
app.include_router(pdf_upload.router, prefix="/python/api/pdf", tags=["PDF上传(兼容)"])
app.include_router(knowledge_graph.router, prefix="/python/api/knowledge", tags=["知识图谱(兼容)"])

# Mount static files
# Get project root (tender_ontology directory where pyproject.toml is located)
# Path: src/tender_ontology/main.py -> src/tender_ontology -> src -> tender_ontology (project root)
PROJECT_ROOT = Path(__file__).parent.parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
STATIC_DIR.mkdir(exist_ok=True)
FRONT_DIR = STATIC_DIR / "AI-document"

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
# 挂载前端目录（可通过 /AI-document/... 访问，不带 static 前缀）
if FRONT_DIR.exists():
    app.mount("/AI-document", StaticFiles(directory=str(FRONT_DIR), html=True), name="frontend")


@app.get("/")
async def root():
    """
    根路径 - 返回前端页面或 API 信息

    如果 static/AI-document/index.html 存在，返回前端页面
    否则返回 API 信息
    """
    index_file = FRONT_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))

    return {
        "message": "Welcome to Tender Ontology API",
        "version": "0.1.0",
        "docs": "/docs",
        "static_files": "/static",
    }


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """
    SPA 路由回退

    对于前端路由（如 /task/123），返回 index.html 由前端 JS 处理
    排除 API、静态文件、文档等路径
    """
    # 排除后端路径
    excluded_prefixes = ("api/", "static/", "docs", "openapi", "redoc", "health", "AI-document/", "python/")
    if full_path.startswith(excluded_prefixes):
        # 返回 None 会导致 404，让 FastAPI 继续匹配其他路由
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not found")

    # 返回前端入口文件
    index_file = FRONT_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))

    # 前端文件不存在，返回 404
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Not found")