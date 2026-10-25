"""
Business service for managing conversations and messages in Cosmos DB.
Enforces soft delete and accumulates deep analytics telemetry for dashboards.
"""
from __future__ import annotations

import time
import uuid
import logging
from typing import Any, Dict, List, Optional

from src.db.cosmos_client import CosmosClientManager
from src.models.conversation import Conversation, ConversationCreate, ConversationUpdate
from src.models.message import Message, MessageCreate

logger = logging.getLogger("conversation-service.service")


class ConversationService:
    def __init__(self, db: CosmosClientManager):
        self.db = db

    # ── Conversation Operations ──────────────────────────────────────────────

    def list_conversations(self, user_id: str, include_deleted: bool = False) -> List[Dict[str, Any]]:
        return self.db.list_conversations(user_id=user_id, include_deleted=include_deleted)

    def get_conversation(self, user_id: str, conversation_id: str, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        return self.db.get_conversation(user_id=user_id, conv_id=conversation_id, include_deleted=include_deleted)

    def create_conversation(self, payload: ConversationCreate) -> Dict[str, Any]:
        now = int(time.time() * 1000)
        doc = {
            "id": payload.conversation_id,
            "conversation_id": payload.conversation_id,
            "user_id": payload.user_id,
            "title": payload.title or "New conversation",
            "repository_ids": payload.repository_ids or [],
            "created_at": now,
            "updated_at": now,
            "turn_count": 0,
            "is_deleted": False,
            "deleted_at": None,
            "status": "active",
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "first_message_at": now,
            "last_message_at": now,
            "duration_ms": 0,
            "metadata": payload.metadata or {},
        }
        return self.db.upsert_conversation(doc)

    def delete_conversation(self, user_id: str, conversation_id: str) -> bool:
        """Soft deletes conversation and its messages. No hard deletion."""
        return self.db.soft_delete_conversation(user_id=user_id, conv_id=conversation_id)

    # ── Message Operations ───────────────────────────────────────────────────

    def list_messages(self, conversation_id: str, include_deleted: bool = False) -> List[Dict[str, Any]]:
        return self.db.list_messages(conv_id=conversation_id, include_deleted=include_deleted)

    def delete_message(self, conversation_id: str, message_id: str) -> bool:
        """Soft deletes a message. No hard deletion."""
        return self.db.soft_delete_message(conv_id=conversation_id, msg_id=message_id)

    def create_message(self, conversation_id: str, payload: MessageCreate) -> Dict[str, Any]:
        now = int(time.time() * 1000)
        msg_id = payload.msg_id or str(uuid.uuid4())

        # Determine sequence number if not explicitly specified
        existing_msgs = self.db.list_messages(conversation_id, include_deleted=True)
        if payload.seq_number is not None:
            seq_num = payload.seq_number
        else:
            if existing_msgs:
                max_seq = max(m.get("seq_number", 0) for m in existing_msgs)
                seq_num = max_seq + 1
            else:
                seq_num = 1

        user_id = payload.user_id or "default_user"
        conv = self.db.get_conversation(user_id, conversation_id, include_deleted=True)

        # Extract content text (from content or payload.content)
        content_text = payload.content if payload.content is not None else (payload.payload.content if payload.payload else "")

        # Extract stats
        raw_stats = payload.stats or (payload.payload.stats if payload.payload else None)
        if raw_stats:
            input_toks = getattr(raw_stats, "input_tokens", 0) if not isinstance(raw_stats, dict) else raw_stats.get("input_tokens", 0)
            output_toks = getattr(raw_stats, "output_tokens", 0) if not isinstance(raw_stats, dict) else raw_stats.get("output_tokens", 0)
            total_toks = getattr(raw_stats, "total_tokens", 0) if not isinstance(raw_stats, dict) else raw_stats.get("total_tokens", 0)
            cost = getattr(raw_stats, "cost", 0.0) if not isinstance(raw_stats, dict) else raw_stats.get("cost", 0.0)
        else:
            input_toks = 0
            output_toks = 0
            total_toks = 0
            cost = 0.0

        if not conv:
            # First message creates the conversation document in Cosmos DB
            title = payload.title
            if not title:
                title = content_text[:60] + ("…" if len(content_text) > 60 else "")
            repo_ids = payload.repository_ids if payload.repository_ids is not None else []
            conv_doc = {
                "id": conversation_id,
                "conversation_id": conversation_id,
                "user_id": user_id,
                "title": title or "New conversation",
                "repository_ids": repo_ids,
                "created_at": now,
                "updated_at": now,
                "turn_count": 1,
                "is_deleted": False,
                "deleted_at": None,
                "status": "active",
                "total_input_tokens": input_toks,
                "total_output_tokens": output_toks,
                "total_tokens": total_toks,
                "total_cost": round(cost, 6),
                "first_message_at": now,
                "last_message_at": now,
                "duration_ms": 0,
                "metadata": {},
            }
            self.db.upsert_conversation(conv_doc)
        else:
            # Update conversation timestamp, turn count, and cumulative analytics
            conv["updated_at"] = now
            conv["last_message_at"] = now
            first_at = conv.get("first_message_at") or conv.get("created_at") or now
            conv["duration_ms"] = max(0, now - first_at)

            if payload.title and conv.get("title") == "New conversation":
                conv["title"] = payload.title
            if payload.repository_ids is not None:
                conv["repository_ids"] = payload.repository_ids

            conv["turn_count"] = max(conv.get("turn_count", 0), (seq_num + 1) // 2)

            # Cumulative tokens & cost
            conv["total_input_tokens"] = conv.get("total_input_tokens", 0) + input_toks
            conv["total_output_tokens"] = conv.get("total_output_tokens", 0) + output_toks
            conv["total_tokens"] = conv.get("total_tokens", 0) + total_toks
            conv["total_cost"] = round(conv.get("total_cost", 0.0) + cost, 6)

            self.db.upsert_conversation(conv)

        # Extract telemetry & metadata
        citations_list = payload.citations or (payload.payload.metadata.citations if payload.payload and payload.payload.metadata else []) or []
        tools_list = payload.tool_calls or (payload.payload.metadata.tool_calls if payload.payload and payload.payload.metadata else []) or []
        latency_val = payload.latency_ms if payload.latency_ms is not None else (payload.payload.metadata.latency_ms if payload.payload and payload.payload.metadata else None)
        model_val = payload.model if payload.model is not None else (payload.payload.metadata.model if payload.payload and payload.payload.metadata else ("gpt-4o" if payload.role == "assistant" else None))
        thinking_val = payload.thinking or (payload.payload.metadata.thinking if payload.payload and payload.payload.metadata else None)

        metadata_dict: Dict[str, Any] = {
            "citations_count": len(citations_list),
            "tool_calls_count": len(tools_list),
            "latency_ms": latency_val,
            "model": model_val,
        }
        if citations_list:
            metadata_dict["citations"] = citations_list
        if tools_list:
            metadata_dict["tool_calls"] = tools_list
        if thinking_val:
            metadata_dict["thinking"] = thinking_val

        payload_dict: Dict[str, Any] = {
            "content": content_text,
            "metadata": metadata_dict,
        }

        # Keep stats ONLY for assistant answer message under payload -> stats
        if payload.role == "assistant":
            if raw_stats is not None:
                if hasattr(raw_stats, "model_dump"):
                    payload_dict["stats"] = raw_stats.model_dump()
                elif isinstance(raw_stats, dict):
                    payload_dict["stats"] = raw_stats
                else:
                    payload_dict["stats"] = dict(raw_stats)
            else:
                payload_dict["stats"] = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "cost": 0.0,
                }

        msg_doc = {
            "id": msg_id,
            "msg_id": msg_id,
            "conversation_id": conversation_id,
            "turn_id": payload.turn_id,
            "seq_number": seq_num,
            "role": payload.role,
            "is_deleted": False,
            "deleted_at": None,
            "created_at": now,
            "payload": payload_dict,
        }

        saved = self.db.upsert_message(msg_doc)
        return saved
