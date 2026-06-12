"""TravelAI FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.config import get_settings
from app.db.session import init_db
from app.observability.langsmith_tracer import configure_langsmith


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_langsmith()
    try:
        await init_db()
    except Exception:
        # Allow local dev without Postgres
        pass
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="TravelAI API",
        description="Multi-agent travel planner — capstone backend",
        version="0.2.0-m2",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(chat_router, tags=["chat"])

    @app.get("/")
    async def root():
        return {
            "service": "TravelAI API",
            "status": "running",
            "docs": "/docs",
            "health": "/health",
            "chat": "POST /chat (Accept: text/event-stream)",
        }

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.2.0-m2"}

    return app


app = create_app()
