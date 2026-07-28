"""
FastAPI Main Application for Maharashtra GR Intelligence Backend.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.config import settings
from api.routes import documents, graph, reasoning, search
from database.db import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gr_api")

app = FastAPI(
    title="Maharashtra GR Intelligence API",
    version="1.0.0",
    description="HTTP API backend for hybrid search, graph visualization, document management, and AI reasoning over Maharashtra Government Resolutions.",
)

# Configure CORS
origins = [origin.strip() for origin in settings.frontend_origin.split(",") if origin.strip()]
if not origins:
    origins = ["http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(search.router)
app.include_router(documents.router)
app.include_router(graph.router)
app.include_router(reasoning.router)


@app.get("/health", tags=["health"])
def health_check() -> Dict[str, Any]:
    """
    Lightweight health check endpoint with database connectivity check.
    """
    db_ok = False
    try:
        db = Database()
        db.cur.execute("SELECT 1")
        db_ok = db.cur.fetchone()[0] == 1
        db.close()
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        db_ok = False

    return {
        "status": "ok",
        "db": db_ok,
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch unhandled exceptions, log server-side traceback, and return clean JSON response.
    """
    logger.exception(f"Unhandled server exception on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": str(exc)},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
