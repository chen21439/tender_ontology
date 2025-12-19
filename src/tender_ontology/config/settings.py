"""
Application settings and configuration.

支持多环境配置：
- 通过 ENV 环境变量指定环境：dev / test / uat / prod
- 配置文件加载顺序：.env.{ENV} -> .env（后者覆盖前者）
- 环境变量优先级最高，会覆盖配置文件中的值

使用方式：
    # Linux/Mac
    ENV=prod python -m uvicorn tender_ontology.main:app

    # Windows PowerShell
    $env:ENV="prod"; python -m uvicorn tender_ontology.main:app
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_env_file() -> str | list[str]:
    """
    根据 ENV 环境变量返回要加载的配置文件

    优先级：环境变量 > .env.{ENV} > .env
    """
    env = os.getenv("ENV", "dev").lower()
    env_file = f".env.{env}"

    # 如果环境特定文件存在，同时加载 .env 和 .env.{ENV}
    if os.path.exists(env_file):
        return [".env", env_file]  # 后面的覆盖前面的
    return ".env"


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=get_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略未定义的环境变量
    )

    # Environment
    env: str = "dev"  # dev / test / uat / prod

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

    # External API - Tender Extract Ontology
    tender_extract_api_url: str = "http://112.111.20.89:8902/tender/extract_onto"
    tender_extract_api_timeout: int = 600  # 10分钟超时

    # Internal Qwen API
    qwen_api_url: str = "http://175.42.62.118:9102/v1/chat/completions"
    qwen_api_timeout: int = 120

    # DeepSeek R1 API (外部)
    deepseek_api_url: str = "http://112.111.20.89:8909/v1/chat/completions"
    deepseek_api_key: str = "ai-0lXtWLDkRImSEtwXorLiUjzFWaWcWALu"
    deepseek_model: str = "deepseek-r1"
    deepseek_api_timeout: int = 120

    # Neo4j Database
    neo4j_uri: str = "neo4j://175.42.62.118:9094"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "12345678"
    neo4j_database: str = "neo4j"

    # DOCX 转 PDF 服务
    docx_pdf_service_url: str = "http://localhost:8080"

    # Aspose Cloud API (DOCX 转 PDF)
    # 直接使用 Bearer Token，无需 OAuth 流程
    aspose_access_token: str = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJuYmYiOjE3NjQ0ODcxOTYsImV4cCI6MTc2NTA5MTk5NiwiaXNzIjoiaHR0cHM6Ly9hcGkuYXNwb3NlLmNsb3VkIiwiYXVkIjpbImh0dHBzOi8vYXBpLmFzcG9zZS5jbG91ZC9yZXNvdXJjZXMiLCJhcGkuYmlsbGluZyIsImFwaS5pZGVudGl0eSIsImFwaS5wcm9kdWN0cyIsImFwaS5zdG9yYWdlIl0sImNsaWVudF9pZCI6ImMzMzhlZTYxLWY4MjItNDFhMy04ZjA2LTRmMTBmMTRkMTFiMyIsImNsaWVudF9kZWZhdWx0X3N0b3JhZ2UiOiI3NWY4MTBlOC1jZTZmLTRjOGMtYTc4ZC00ZTQ1ZDAwZDVmNzgiLCJjbGllbnRfaWRlbnRpdHlfdXNlcl9pZCI6IjEwNDkxMDYiLCJzY29wZSI6WyJhcGkuYmlsbGluZyIsImFwaS5pZGVudGl0eSIsImFwaS5wcm9kdWN0cyIsImFwaS5zdG9yYWdlIl19.AEJKl5lV7wCaNyNp6D25FJfaYsr8HS9fmZcIJTRL8RDgW908d4KUhZRU2nmESz9CmYFgikriyXkXw8soYFQb5TKS_ItsrETDIOURIYvyYEkDV9zDtQ8PqWh_jMZJ79ZwP7YWuT9rdXalTUKErvKXREntwau2SVrXSbYnJ8ejDXqawdq2Q3KXf27_E5pPql7nfFPZhB7Sr69ZdP_wlWiVmKtUZ0X8KmX4NANYdYW7MzDeeUgYE_wJx_JR7m04rOGB1mLJh3WxuWRxmE4XejOzi1wdSKUJFEUOAfZAVv8oNpsTsQbGc1J13ZBHHPVHNGhpxYry7CBxYyetau4DZ1czRg"


settings = Settings()

# 启动时打印当前环境
print(f"[Settings] 当前环境: {settings.env}, 配置文件: {get_env_file()}")