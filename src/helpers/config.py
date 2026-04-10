from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional

import os

# Calculate the absolute path to the root directory where .env lives
# Assuming config.py is inside src/helpers/
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.dirname(CURRENT_DIR)
ENV_PATH = os.path.join(SRC_DIR, ".env")

class Settings(BaseSettings):
    """Settings for the application."""
    
    app_name: str = "AI Orchestrator Service"
    app_version: str = "1.0.0"
    
    # Database settings
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: Optional[str] = None
    db_user: Optional[str] = None
    db_password: Optional[str] = None
    
    # Redis settings
    redis_password: Optional[str] = None
    redis_host: str = "localhost"
    redis_port: int = 6379
    
    # LLM settings
    gemini_api_key: Optional[str] = None
    llm_max_rag_tool_retries: int = 3
    chat_history_limit: int = 10
    
    # Google Cloud settings
    gcp_project_id: str = "agents-platform-490417"
    
    # API URLs to other services (CORE API, RAG API) 
    rag_api_url: str | None = None 
    
    # Core API URL
    core_api_url: str | None = None
    
    # Internal Secret for service-to-service communication (must match the key expected by the other services)
    internal_secret_between_services: str | None = None
    
    # GCP Pub/Sub Push Authentication
    pubsub_audience: str | None = None
    pubsub_invoker_email: str | None = None
    
    class Config:
        env_file = ENV_PATH
        env_file_encoding = "utf-8"
        extra = "ignore" 
            

settings = Settings()

def get_settings():
    return settings