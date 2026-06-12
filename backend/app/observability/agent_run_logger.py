"""Agent run logging to agent_runs table."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.db.models import AgentRun
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


async def log_agent_run(
    session_id: UUID,
    conversation_id: UUID,
    agent_name: str,
    status: str,
    *,
    node_name: str | None = None,
    input_snapshot: dict[str, Any] | None = None,
    output_snapshot: dict[str, Any] | None = None,
    error_message: str | None = None,
    latency_ms: int | None = None,
    graph_mode: str = "optimized",
) -> None:
    try:
        async with async_session_factory() as db:
            db.add(
                AgentRun(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    agent_name=agent_name,
                    node_name=node_name or agent_name,
                    status=status,
                    input_snapshot=input_snapshot,
                    output_snapshot=output_snapshot,
                    error_message=error_message,
                    latency_ms=latency_ms,
                    graph_mode=graph_mode,
                )
            )
            await db.commit()
    except Exception as exc:
        logger.debug("agent_run log skipped (db unavailable): %s", exc)
