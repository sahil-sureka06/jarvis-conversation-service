"""
JARVIS Conversation Service — Entry Point.

Run with:
    PYTHONPATH=src uvicorn main:app --host 0.0.0.0 --port 8002 --reload
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure src is in sys.path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from src.app import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn
    from src.config import settings
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
