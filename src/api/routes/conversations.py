"""
Conversation API routes (Soft Delete Only).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from src.models.conversation import ConversationCreate
from src.services.conversation_service import ConversationService

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def get_service() -> ConversationService:
    from src.app import service
    return service


@router.get("", summary="List conversations for a user")
async def list_conversations(
    user_id: str = Query(default="default_user", description="Owner user ID"),
    include_deleted: bool = Query(default=False, description="Whether to include soft-deleted conversations"),
    service: ConversationService = Depends(get_service),
) -> List[Dict[str, Any]]:
    return service.list_conversations(user_id=user_id, include_deleted=include_deleted)


@router.get("/{conversation_id}", summary="Get conversation by ID")
async def get_conversation(
    conversation_id: str,
    user_id: str = Query(default="default_user", description="Owner user ID"),
    include_deleted: bool = Query(default=False, description="Whether to include if soft-deleted"),
    service: ConversationService = Depends(get_service),
) -> Dict[str, Any]:
    conv = service.get_conversation(user_id=user_id, conversation_id=conversation_id, include_deleted=include_deleted)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.post("", summary="Create or register a conversation")
async def create_conversation(
    payload: ConversationCreate,
    service: ConversationService = Depends(get_service),
) -> Dict[str, Any]:
    return service.create_conversation(payload)


@router.delete("/{conversation_id}", summary="Soft delete conversation and its messages")
async def delete_conversation(
    conversation_id: str,
    user_id: str = Query(default="default_user", description="Owner user ID"),
    service: ConversationService = Depends(get_service),
) -> Dict[str, Any]:
    """
    Soft delete a conversation and its messages.
    NEVER hard deletes. Retains document in Cosmos DB for analytics.
    """
    success = service.delete_conversation(user_id=user_id, conversation_id=conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "soft_deleted", "conversation_id": conversation_id}
