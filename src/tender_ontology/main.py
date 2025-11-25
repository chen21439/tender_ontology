"""
FastAPI application entry point for tender ontology service.
"""

from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from tender_ontology.routers import health, ontology, pdf_upload
from tender_ontology.utils.db.mysql import init_db, close_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理

    启动时初始化数据库连接池，关闭时释放
    """
    # 启动时：初始化数据库连接池
    init_db()

    yield

    # 关闭时：释放数据库连接池
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

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(ontology.router, tags=["ontology"])
app.include_router(pdf_upload.router, prefix="/api/pdf", tags=["PDF上传"])

# Mount static files
# Get project root (tender_ontology directory where pyproject.toml is located)
# Path: src/tender_ontology/main.py -> src/tender_ontology -> src -> tender_ontology (project root)
PROJECT_ROOT = Path(__file__).parent.parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to Tender Ontology API",
        "version": "0.1.0",
        "docs": "/docs",
        "static_files": "/static",
    }