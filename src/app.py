"""
FastAPI application setup for Conversation Service.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.db.cosmos_client import CosmosClientManager
from src.services.conversation_service import ConversationService
from src.api.routes import conversations, messages, health, explorer, analytics

logger = logging.getLogger("conversation-service")

# Initialize database manager & service singleton
db_manager = CosmosClientManager(
    endpoint=settings.COSMOS_ENDPOINT,
    key=settings.COSMOS_KEY,
    database_name=settings.COSMOS_DATABASE,
    conversations_container=settings.COSMOS_CONVERSATIONS_CONTAINER,
    messages_container=settings.COSMOS_MESSAGES_CONTAINER,
    fallback_dir=settings.FALLBACK_STORAGE_DIR,
)
service = ConversationService(db=db_manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting JARVIS Conversation Service...")
    db_manager.connect()
    yield
    logger.info("Shutting down JARVIS Conversation Service.")


app = FastAPI(
    title="JARVIS Conversation Service",
    description="Cosmos DB conversation tracking and history persistence for JARVIS",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(explorer.router)
app.include_router(health.router)
app.include_router(conversations.router)
app.include_router(messages.router)
app.include_router(analytics.router)
