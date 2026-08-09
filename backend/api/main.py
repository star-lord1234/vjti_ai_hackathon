"""
FastAPI Main Application for Maharashtra GR Intelligence Backend.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict

# Offline-first: must run before any Hugging Face / embedding imports on request paths.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from offline import configure_offline_mode

configure_offline_mode()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import settings
from api.routes import chat, documents, drafts, forum, graph, reasoning, search, template
from database.db import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gr_api")

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Pre-loading embedding model on startup...")
    try:
        from embeddings.embed import get_model

        get_model()
    except Exception as e:
        logger.warning(f"Failed to pre-load embedding model: {e}")
    yield


app = FastAPI(
    title="Maharashtra GR Intelligence API",
    version="1.0.0",
    description="HTTP API backend for hybrid search, graph visualization, document management, and AI reasoning over Maharashtra Government Resolutions.",
    lifespan=lifespan,
)

# Configure CORS
origins = [origin.strip() for origin in settings.frontend_origin.split(",") if origin.strip()]
for default_origin in ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"]:
    if default_origin not in origins:
        origins.append(default_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error on {request.url}: {exc}", exc_info=True)
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
        },
    )


# Include Routers
app.include_router(search.router)
app.include_router(documents.router)
app.include_router(graph.router)
app.include_router(reasoning.router)
app.include_router(drafts.router)
app.include_router(forum.router)
app.include_router(chat.router)
app.include_router(template.router)



@app.get("/health", tags=["health"])
def health_check() -> Dict[str, Any]:
    """
    Health check with Postgres and Neo4j connectivity.
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

    neo4j_status: Dict[str, Any] = {"ok": False, "error": "not checked"}
    try:
        from graph.neo4j_query import check_neo4j_health

        neo4j_status = check_neo4j_health()
    except Exception as e:
        neo4j_status = {"ok": False, "error": str(e)}

    embeddings_health: Dict[str, Any] = {
        "ok": False,
        "count": 0,
        "total_documents": 0,
        "coverage": 0.0,
    }
    try:
        db = Database()
        db.cur.execute("SELECT COUNT(*) FROM gr_documents")
        total_docs = int(db.cur.fetchone()[0])
        db.cur.execute(
            "SELECT COUNT(*) FROM gr_documents WHERE embedding IS NOT NULL"
        )
        embedded = int(db.cur.fetchone()[0])
        db.close()
        coverage = (embedded / total_docs) if total_docs else 0.0
        embeddings_health = {
            "ok": embedded > 0 and coverage >= 0.5,
            "count": embedded,
            "total_documents": total_docs,
            "coverage": round(coverage, 4),
        }
    except Exception as e:
        embeddings_health["error"] = str(e)

    store_sync: Dict[str, Any] = {"in_sync": True, "warnings": []}
    try:
        from database.sync_status import check_store_sync

        store_sync = check_store_sync()
    except Exception as e:
        store_sync = {"in_sync": False, "warnings": [str(e)]}

    overall_ok = (
        db_ok
        and neo4j_status.get("ok", False)
        and embeddings_health.get("ok", False)
        and store_sync.get("in_sync", False)
    )

    return {
        "status": "ok" if overall_ok else "degraded",
        "db": db_ok,
        "neo4j": neo4j_status.get("ok", False),
        "neo4j_error": neo4j_status.get("error"),
        "embeddings": embeddings_health,
        "store_sync": store_sync,
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
