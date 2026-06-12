"""SQLAlchemy ORM models — M1 placeholders, M2+ migrations."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

try:
    from pgvector.sqlalchemy import Vector

    _VECTOR_DIM = 384
    _EmbeddingType = Vector(_VECTOR_DIM)
except ImportError:
    _EmbeddingType = None  # type: ignore[misc, assignment]


class Base(DeclarativeBase):
    pass


class AgentRun(Base):
    """LangGraph execution trace per step."""

    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    agent_name: Mapped[str] = mapped_column(String(64), index=True)
    node_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="started")
    input_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    graph_mode: Mapped[str] = mapped_column(String(32), default="optimized")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LLMUsageLog(Base):
    """Per LLM call cost and token accounting."""

    __tablename__ = "llm_usage_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    agent_name: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(128))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Document(Base):
    """RAG chunks with pgvector embedding (M2+ populate)."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    destination_key: Mapped[str] = mapped_column(String(64), index=True)
    source_file: Mapped[str] = mapped_column(String(256))
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    embedding = (
        mapped_column(_EmbeddingType, nullable=True)
        if _EmbeddingType is not None
        else mapped_column(JSONB, nullable=True)
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
