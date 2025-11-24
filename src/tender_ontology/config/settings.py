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

    # MySQL Database (for PDF upload tasks)
    mysql_host: str = "172.16.0.116"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "123456"
    mysql_database: str = "tender_compliance"
    mysql_charset: str = "utf8mb4"

    # File Storage
    file_storage_base: str = "static"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()