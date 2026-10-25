# JARVIS Conversation Service

Microservice responsible for tracking conversations, messages, token economics, cost analytics, and Cosmos DB telemetry in the JARVIS AI platform.

## Features
- **Azure Cosmos DB Persistence:**
  - `conversations` container: tracks session metadata, tokens, spend, status, and turn counts.
  - `messages` container: records questions, assistant answers, latency, citations, and model attribution.
- **Strict Soft-Delete Architecture:**
  - Conversations and messages are marked `is_deleted = True` and preserved for compliance and analytics.
- **Standalone Admin Analytics Portal:**
  - Real-time operational dashboard accessible at `http://localhost:8002/analytics`.
  - Visual Cosmos DB Document Explorer at `http://localhost:8002/explorer`.
- **FastAPI Core:**
  - Full OpenAPI documentation at `http://localhost:8002/docs`.

## Getting Started

### Installation
```bash
poetry install
```

### Configuration
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Configure your Azure Cosmos DB endpoint and key (or leave empty to use local fallback storage):
```env
COSMOS_ENDPOINT=https://your-cosmos-account.documents.azure.com:443/
COSMOS_KEY=your_primary_key
COSMOS_DATABASE=jarvis-conversations
COSMOS_CONVERSATIONS_CONTAINER=conversations
COSMOS_MESSAGES_CONTAINER=messages
PORT=8002
```

### Running Locally
```bash
PYTHONPATH=src uvicorn main:app --host 0.0.0.0 --port 8002 --reload
```
