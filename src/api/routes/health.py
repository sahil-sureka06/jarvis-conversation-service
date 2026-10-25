"""
Health check route.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/api/health", summary="Health check")
async def health_check():
    from src.app import db_manager
    return {
        "status": "ok",
        "service": "jarvis-conversation-service",
        "cosmos_connected": db_manager.is_connected,
        "database": db_manager.database_name,
        "collections": [
            db_manager.conversations_container_name,
            db_manager.messages_container_name,
        ],
    }
