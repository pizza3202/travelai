"""LangSmith tracing helpers (M2+ full integration)."""

from contextlib import contextmanager
from typing import Any, Generator

from app.config import get_settings


@contextmanager
def trace_run(name: str, metadata: dict[str, Any] | None = None) -> Generator[None, None, None]:
    settings = get_settings()
    if not settings.langsmith_api_key or not settings.langsmith_tracing:
        yield
        return
    # M2: wrap langsmith traceable
    _ = (name, metadata)
    yield


def configure_langsmith() -> None:
    settings = get_settings()
    if settings.langsmith_api_key:
        import os

        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langsmith_project)
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key)
