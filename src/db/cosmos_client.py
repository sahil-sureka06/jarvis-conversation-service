"""
Cosmos DB Client Manager.

Manages connection to Azure Cosmos DB with two containers:
  1. conversations (partition key: /user_id)
  2. messages (partition key: /conversation_id)

Guarantees SOFT DELETE ONLY for both conversations and messages:
  - When deleted, documents remain stored in Cosmos DB with `is_deleted = True` and `deleted_at = <epoch_ms>`.
  - Soft-deleted items are excluded from normal application and UI queries.
  - Retains all historical and telemetry data for analytics dashboards.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("conversation-service.db")


class LocalFallbackStore:
    """
    Local JSON file-backed partition store that mimics Cosmos DB containers.
    Enforces soft delete and stores rich analytics metadata.
    """

    def __init__(self, base_dir: str = ".data"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.conv_file = self.base_dir / "conversations.json"
        self.msg_file = self.base_dir / "messages.json"
        self._lock = threading.Lock()
        self._init_files()

    def _init_files(self):
        with self._lock:
            if not self.conv_file.exists():
                self.conv_file.write_text("{}", encoding="utf-8")
            if not self.msg_file.exists():
                self.msg_file.write_text("{}", encoding="utf-8")

    def _read(self, path: Path) -> Dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8") or "{}")
        except Exception:
            return {}

    def _write(self, path: Path, data: Dict[str, Any]):
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ── Conversations ────────────────────────────────────────────────────────

    def upsert_conversation(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            data = self._read(self.conv_file)
            user_id = doc.get("user_id", "default_user")
            user_bucket = data.setdefault(user_id, {})
            # Ensure soft-delete defaults
            if "is_deleted" not in doc:
                doc["is_deleted"] = False
            user_bucket[doc["id"]] = doc
            self._write(self.conv_file, data)
            return doc

    def get_conversation(self, user_id: str, conv_id: str, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        with self._lock:
            data = self._read(self.conv_file)
            doc = data.get(user_id, {}).get(conv_id)
            if doc and not include_deleted and doc.get("is_deleted", False):
                return None
            return doc

    def list_conversations(self, user_id: str, include_deleted: bool = False) -> List[Dict[str, Any]]:
        with self._lock:
            data = self._read(self.conv_file)
            items = list(data.get(user_id, {}).values())
            if not include_deleted:
                items = [it for it in items if not it.get("is_deleted", False)]
            items.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
            return items

    def soft_delete_conversation(self, user_id: str, conv_id: str) -> bool:
        """Soft delete conversation and all its messages. NEVER hard deletes."""
        now = int(time.time() * 1000)
        with self._lock:
            data = self._read(self.conv_file)
            user_bucket = data.get(user_id, {})
            if conv_id in user_bucket:
                # Mark conversation soft-deleted
                user_bucket[conv_id]["is_deleted"] = True
                user_bucket[conv_id]["deleted_at"] = now
                user_bucket[conv_id]["updated_at"] = now
                self._write(self.conv_file, data)

                # Mark all associated messages soft-deleted
                msg_data = self._read(self.msg_file)
                if conv_id in msg_data:
                    for m in msg_data[conv_id].values():
                        m["is_deleted"] = True
                        m["deleted_at"] = now
                    self._write(self.msg_file, msg_data)
                return True
            return False

    # ── Messages ─────────────────────────────────────────────────────────────

    def upsert_message(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            data = self._read(self.msg_file)
            conv_id = doc.get("conversation_id", "default_conv")
            conv_bucket = data.setdefault(conv_id, {})
            if "is_deleted" not in doc:
                doc["is_deleted"] = False
            conv_bucket[doc["id"]] = doc
            self._write(self.msg_file, data)
            return doc

    def list_messages(self, conv_id: str, include_deleted: bool = False) -> List[Dict[str, Any]]:
        with self._lock:
            data = self._read(self.msg_file)
            items = list(data.get(conv_id, {}).values())
            if not include_deleted:
                items = [it for it in items if not it.get("is_deleted", False)]
            items.sort(key=lambda x: x.get("seq_number", 0))
            return items

    def soft_delete_message(self, conv_id: str, msg_id: str) -> bool:
        """Soft delete a single message document. NEVER hard deletes."""
        now = int(time.time() * 1000)
        with self._lock:
            data = self._read(self.msg_file)
            conv_bucket = data.get(conv_id, {})
            if msg_id in conv_bucket:
                conv_bucket[msg_id]["is_deleted"] = True
                conv_bucket[msg_id]["deleted_at"] = now
                self._write(self.msg_file, data)
                return True
            return False

    def get_all_data(self) -> Dict[str, Any]:
        with self._lock:
            conv_data = self._read(self.conv_file)
            msg_data = self._read(self.msg_file)
            all_convs = []
            for u_id, bucket in conv_data.items():
                all_convs.extend(bucket.values())
            all_convs.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
            all_msgs = []
            for c_id, bucket in msg_data.items():
                all_msgs.extend(bucket.values())
            all_msgs.sort(key=lambda x: (x.get("conversation_id", ""), x.get("seq_number", 0)))
            return {
                "conversations": all_convs,
                "messages": all_msgs,
            }


class CosmosClientManager:
    """
    Coordinates access to Azure Cosmos DB or local fallback store.
    All deletion operations are strictly SOFT DELETE.
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        key: Optional[str] = None,
        database_name: str = "jarvis-conversations",
        conversations_container: str = "conversations",
        messages_container: str = "messages",
        fallback_dir: str = ".data",
    ):
        self.endpoint = endpoint
        self.key = key
        self.database_name = database_name
        self.conversations_container_name = conversations_container
        self.messages_container_name = messages_container
        self.fallback_dir = fallback_dir

        self.client = None
        self.db = None
        self.conv_container = None
        self.msg_container = None
        self.is_connected = False
        self.fallback = LocalFallbackStore(base_dir=fallback_dir)

    def connect(self):
        """Initialise connection to Cosmos DB if credentials provided."""
        if self.endpoint and self.key:
            try:
                from azure.cosmos import CosmosClient, PartitionKey
                logger.info(f"Connecting to Azure Cosmos DB at {self.endpoint}...")
                self.client = CosmosClient(self.endpoint, credential=self.key)
                self.db = self.client.create_database_if_not_exists(id=self.database_name)
                self.conv_container = self.db.create_container_if_not_exists(
                    id=self.conversations_container_name,
                    partition_key=PartitionKey(path="/user_id"),
                )
                self.msg_container = self.db.create_container_if_not_exists(
                    id=self.messages_container_name,
                    partition_key=PartitionKey(path="/conversation_id"),
                )
                self.is_connected = True
                logger.info("Successfully connected to Azure Cosmos DB!")
                return
            except Exception as e:
                logger.warning(f"Could not connect to Azure Cosmos DB: {e}. Using local storage fallback.")
                self.is_connected = False
        else:
            logger.info("No Azure Cosmos DB credentials provided. Using local storage fallback.")
            self.is_connected = False

    # ── Conversation Operations (Soft Delete Only) ───────────────────────────

    def upsert_conversation(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        if "is_deleted" not in doc:
            doc["is_deleted"] = False
        if self.is_connected and self.conv_container:
            try:
                return self.conv_container.upsert_item(body=doc)
            except Exception as e:
                logger.error(f"Cosmos DB upsert_conversation error: {e}")
        return self.fallback.upsert_conversation(doc)

    def get_conversation(self, user_id: str, conv_id: str, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        if self.is_connected and self.conv_container:
            try:
                doc = self.conv_container.read_item(item=conv_id, partition_key=user_id)
                if doc and not include_deleted and doc.get("is_deleted", False):
                    return None
                return doc
            except Exception:
                pass
        return self.fallback.get_conversation(user_id, conv_id, include_deleted=include_deleted)

    def list_conversations(self, user_id: str, include_deleted: bool = False) -> List[Dict[str, Any]]:
        if self.is_connected and self.conv_container:
            try:
                if include_deleted:
                    query = "SELECT * FROM c WHERE c.user_id = @user_id ORDER BY c.updated_at DESC"
                else:
                    query = "SELECT * FROM c WHERE c.user_id = @user_id AND (NOT IS_DEFINED(c.is_deleted) OR c.is_deleted = false) ORDER BY c.updated_at DESC"
                params = [{"name": "@user_id", "value": user_id}]
                items = list(self.conv_container.query_items(
                    query=query,
                    parameters=params,
                    enable_cross_partition_query=False,
                    partition_key=user_id,
                ))
                return items
            except Exception as e:
                logger.error(f"Cosmos DB query error: {e}")
        return self.fallback.list_conversations(user_id, include_deleted=include_deleted)

    def soft_delete_conversation(self, user_id: str, conv_id: str) -> bool:
        """Soft delete conversation. NEVER executes a hard delete."""
        now = int(time.time() * 1000)
        if self.is_connected and self.conv_container:
            try:
                doc = self.get_conversation(user_id, conv_id, include_deleted=True)
                if doc:
                    doc["is_deleted"] = True
                    doc["deleted_at"] = now
                    doc["updated_at"] = now
                    self.conv_container.upsert_item(body=doc)

                # Soft delete all messages in container
                if self.msg_container:
                    msgs = self.list_messages(conv_id, include_deleted=True)
                    for m in msgs:
                        m["is_deleted"] = True
                        m["deleted_at"] = now
                        self.msg_container.upsert_item(body=m)
                return True
            except Exception as e:
                logger.error(f"Cosmos DB soft delete error: {e}")
        return self.fallback.soft_delete_conversation(user_id, conv_id)

    # Alias delete_conversation to soft_delete_conversation (No hard delete allowed)
    delete_conversation = soft_delete_conversation

    # ── Message Operations (Soft Delete Only) ─────────────────────────────────

    def upsert_message(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        if "is_deleted" not in doc:
            doc["is_deleted"] = False
        if self.is_connected and self.msg_container:
            try:
                return self.msg_container.upsert_item(body=doc)
            except Exception as e:
                logger.error(f"Cosmos DB upsert_message error: {e}")
        return self.fallback.upsert_message(doc)

    def list_messages(self, conv_id: str, include_deleted: bool = False) -> List[Dict[str, Any]]:
        if self.is_connected and self.msg_container:
            try:
                if include_deleted:
                    query = "SELECT * FROM c WHERE c.conversation_id = @conv_id ORDER BY c.seq_number ASC"
                else:
                    query = "SELECT * FROM c WHERE c.conversation_id = @conv_id AND (NOT IS_DEFINED(c.is_deleted) OR c.is_deleted = false) ORDER BY c.seq_number ASC"
                params = [{"name": "@conv_id", "value": conv_id}]
                items = list(self.msg_container.query_items(
                    query=query,
                    parameters=params,
                    enable_cross_partition_query=False,
                    partition_key=conv_id,
                ))
                return items
            except Exception as e:
                logger.error(f"Cosmos DB list_messages query error: {e}")
        return self.fallback.list_messages(conv_id, include_deleted=include_deleted)

    def soft_delete_message(self, conv_id: str, msg_id: str) -> bool:
        """Soft delete message document. NEVER hard deletes."""
        now = int(time.time() * 1000)
        if self.is_connected and self.msg_container:
            try:
                query = "SELECT * FROM c WHERE c.id = @msg_id AND c.conversation_id = @conv_id"
                params = [{"name": "@msg_id", "value": msg_id}, {"name": "@conv_id", "value": conv_id}]
                items = list(self.msg_container.query_items(
                    query=query, parameters=params, partition_key=conv_id
                ))
                if items:
                    m = items[0]
                    m["is_deleted"] = True
                    m["deleted_at"] = now
                    self.msg_container.upsert_item(body=m)
                    return True
            except Exception as e:
                logger.error(f"Cosmos DB soft_delete_message error: {e}")
        return self.fallback.soft_delete_message(conv_id, msg_id)

    def get_all_data(self) -> Dict[str, Any]:
        """Fetch all documents across collections for the Cosmos DB Data Explorer."""
        if self.is_connected and self.conv_container and self.msg_container:
            try:
                convs = list(self.conv_container.query_items(
                    query="SELECT * FROM c ORDER BY c.updated_at DESC",
                    enable_cross_partition_query=True
                ))
                msgs = list(self.msg_container.query_items(
                    query="SELECT * FROM c ORDER BY c.created_at ASC",
                    enable_cross_partition_query=True
                ))
                return {
                    "database": self.database_name,
                    "is_connected": True,
                    "endpoint": self.endpoint,
                    "conversations": convs,
                    "messages": msgs,
                }
            except Exception as e:
                logger.error(f"Cosmos DB get_all_data error: {e}")
        fallback_data = self.fallback.get_all_data()
        return {
            "database": self.database_name,
            "is_connected": self.is_connected,
            "endpoint": self.endpoint or "Local Storage (No Azure credentials set)",
            "conversations": fallback_data["conversations"],
            "messages": fallback_data["messages"],
        }
