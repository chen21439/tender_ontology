"""
FastAPI application entry point for tender ontology service.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from tender_ontology.routers import health, ontology

app = FastAPI(
    title="Tender Ontology API",
    description="API for managing tender/bid ontology and knowledge graph",
    version="0.1.0",
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