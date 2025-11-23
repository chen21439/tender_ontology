"""
Application settings and configuration.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Application
    app_name: str = "Tender Ontology API"
    app_version: str = "0.1.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = "sqlite:///./tender_ontology.db"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()