"""
Message document schema for Azure Cosmos DB.
Partition Key: /conversation_id
Primary Key: id (msg_id)

Supports soft delete and detailed telemetry for analytics dashboards.
"""
from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MessageStats(BaseModel):
    """Execution statistics kept only for assistant answer messages."""
    input_tokens: int = Field(default=0, description="Prompt / input tokens consumed")
    output_tokens: int = Field(default=0, description="Completion / output tokens generated")
    total_tokens: int = Field(default=0, description="Total tokens consumed")
    cost: float = Field(default=0.0, description="Cost in USD for this message")


class MessageMetadata(BaseModel):
    citations_count: int = Field(default=0, description="Count of cited source code elements")
    tool_calls_count: int = Field(default=0, description="Count of tools executed in this turn")
    latency_ms: Optional[int] = Field(default=None, description="Latency in ms")
    model: Optional[str] = Field(default=None, description="LLM model used (e.g. gpt-4o)")
    citations: Optional[List[Dict[str, Any]]] = Field(default=None)
    tool_calls: Optional[List[Dict[str, Any]]] = Field(default=None)
    thinking: Optional[str] = Field(default=None)


class MessagePayload(BaseModel):
    content: str = Field(..., description="The message payload / text")
    metadata: MessageMetadata = Field(default_factory=MessageMetadata, description="Telemetry metadata")
    stats: Optional[MessageStats] = Field(default=None, description="Stats for answer message (tokens, cost)")


class MessageCreate(BaseModel):
    msg_id: Optional[str] = Field(default=None, description="Optional message ID. Generated if not provided.")
    user_id: Optional[str] = Field(default="default_user", description="User ID for auto-creating conversation if needed")
    turn_id: str = Field(..., description="Shared turn ID for a question & answer pair")
    seq_number: Optional[int] = Field(default=None, description="Sequence number in conversation. Auto-calculated if omitted.")
    role: str = Field(..., description="'user' or 'assistant'")
    
    # Support both nested payload or flat fields
    payload: Optional[MessagePayload] = Field(default=None, description="Nested payload")
    content: Optional[str] = Field(default=None, description="The message text")
    stats: Optional[MessageStats] = Field(default=None, description="Stats for answer message (tokens, cost)")
    citations: Optional[List[Dict[str, Any]]] = Field(default=None, description="Code citations")
    thinking: Optional[str] = Field(default=None, description="Agent reasoning thoughts")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(default=None, description="Tool calls made")
    title: Optional[str] = Field(default=None, description="Optional title override (e.g. for first question)")
    repository_ids: Optional[List[str]] = Field(default=None, description="Optional connected repositories")
    
    # Optional telemetry fields
    latency_ms: Optional[int] = Field(default=None, description="Latency in ms to produce this turn")
    model: Optional[str] = Field(default=None, description="Model used (e.g. gpt-4o)")


class Message(BaseModel):
    id: str = Field(..., description="Primary key in Cosmos DB (equals msg_id)")
    msg_id: str = Field(..., description="Message identifier")
    conversation_id: str = Field(..., description="Partition key (/conversation_id)")
    turn_id: str = Field(..., description="Turn ID connecting question & answer")
    seq_number: int = Field(..., description="Ordered sequence number")
    role: str = Field(..., description="'user' or 'assistant'")
    is_deleted: bool = Field(default=False, description="True if message is soft-deleted")
    deleted_at: Optional[int] = Field(default=None, description="Epoch ms when deleted")
    created_at: int = Field(default_factory=lambda: int(time.time() * 1000))
    payload: MessagePayload = Field(..., description="Message payload containing content, metadata, and stats")
