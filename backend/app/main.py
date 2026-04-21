"""FastAPI application — main entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import dispose_engine, init_engine
from app.deps import set_redis
from app.routes import admin, installer, result, session, submit, ws

logger = logging.getLogger("cluezero")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Connecting to Redis at %s", settings.redis_url)
    conn = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    conn.ping()
    set_redis(conn)
    logger.info("Redis connected")

    logger.info("Initialising DB engine")
    init_engine()
    logger.info("DB engine ready")

    yield

    conn.close()
    await dispose_engine()
    logger.info("Shutdown complete")


app = FastAPI(
    title="ClueZero API",
    description="Background Screenshot → AI Processing System",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(submit.router)
app.include_router(result.router)
app.include_router(ws.router)
app.include_router(session.router)
app.include_router(admin.router)
app.include_router(installer.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
