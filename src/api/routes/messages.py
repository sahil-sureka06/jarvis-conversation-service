"""
Messages API routes (Soft Delete Only).
"""
from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query

from src.models.message import MessageCreate
from src.services.conversation_service import ConversationService

router = APIRouter(prefix="/api/conversations/{conversation_id}/messages", tags=["messages"])


def get_service() -> ConversationService:
    from src.app import service
    return service


@router.get("", summary="Get all messages for a conversation")
async def list_messages(
    conversation_id: str,
    include_deleted: bool = Query(default=False, description="Whether to include soft-deleted messages"),
    service: ConversationService = Depends(get_service),
) -> List[Dict[str, Any]]:
    return service.list_messages(conversation_id=conversation_id, include_deleted=include_deleted)


@router.post("", summary="Write a message to a conversation")
async def create_message(
    conversation_id: str,
    payload: MessageCreate,
    service: ConversationService = Depends(get_service),
) -> Dict[str, Any]:
    return service.create_message(conversation_id=conversation_id, payload=payload)


@router.delete("/{message_id}", summary="Soft delete a single message")
async def delete_message(
    conversation_id: str,
    message_id: str,
    service: ConversationService = Depends(get_service),
) -> Dict[str, Any]:
    """
    Soft delete a message document.
    NEVER hard deletes. Retains document in Cosmos DB for analytics.
    """
    success = service.delete_message(conversation_id=conversation_id, message_id=message_id)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "soft_deleted", "message_id": message_id}
