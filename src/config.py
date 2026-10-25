"""
Configuration settings for JARVIS Conversation Service.
"""
from __future__ import annotations

import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    HOST: str = "0.0.0.0"
    PORT: int = 8002
    LOG_LEVEL: str = "INFO"

    # Azure Cosmos DB settings
    COSMOS_ENDPOINT: Optional[str] = None
    COSMOS_KEY: Optional[str] = None
    COSMOS_DATABASE: str = "jarvis-conversations"
    COSMOS_CONVERSATIONS_CONTAINER: str = "conversations"
    COSMOS_MESSAGES_CONTAINER: str = "messages"

    FALLBACK_STORAGE_DIR: str = ".data"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
