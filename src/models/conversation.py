"""
Conversation document schema for Azure Cosmos DB.
Partition Key: /user_id
Primary Key: id (conversation_id)

Supports soft delete and rich telemetry fields for analytics dashboards.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    conversation_id: str = Field(..., description="Unique conversation UUID")
    user_id: str = Field(default="default_user", description="Owner user ID (partition key)")
    title: Optional[str] = Field(default="New conversation", description="Title or summary of conversation")
    repository_ids: List[str] = Field(default_factory=list, description="Associated repositories/clusters")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata")


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    repository_ids: Optional[List[str]] = None
    turn_count: Optional[int] = None
    is_deleted: Optional[bool] = None
    deleted_at: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class Conversation(BaseModel):
    id: str = Field(..., description="Document primary key in Cosmos DB (equals conversation_id)")
    conversation_id: str = Field(..., description="Conversation identifier")
    user_id: str = Field(..., description="Partition key (/user_id)")
    title: str = Field(default="New conversation")
    repository_ids: List[str] = Field(default_factory=list)
    created_at: int = Field(default_factory=lambda: int(time.time() * 1000))
    updated_at: int = Field(default_factory=lambda: int(time.time() * 1000))
    turn_count: int = Field(default=0)
    
    # Soft delete flags
    is_deleted: bool = Field(default=False, description="True if conversation is soft-deleted")
    deleted_at: Optional[int] = Field(default=None, description="Epoch ms when deleted")
    
    # Analytics & Telemetry attributes for dashboard
    status: str = Field(default="active", description="'active' | 'completed' | 'archived'")
    total_input_tokens: int = Field(default=0, description="Cumulative input tokens for all turns")
    total_output_tokens: int = Field(default=0, description="Cumulative output tokens for all turns")
    total_tokens: int = Field(default=0, description="Cumulative total tokens")
    total_cost: float = Field(default=0.0, description="Cumulative cost in USD")
    first_message_at: Optional[int] = Field(default=None)
    last_message_at: Optional[int] = Field(default=None)
    duration_ms: Optional[int] = Field(default=0, description="Active session duration in ms")
    metadata: Dict[str, Any] = Field(default_factory=dict)
