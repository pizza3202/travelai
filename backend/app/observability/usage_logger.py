"""LLM usage logging to llm_usage_logs table."""

from __future__ import annotations

import logging
from uuid import UUID

from app.config import get_settings
from app.db.models import LLMUsageLog
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

MODEL_COST_PER_1M = {
    "openai/gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "openai/gpt-4o": {"prompt": 2.50, "completion": 10.00},
    "poolside/laguna-xs.2": {"prompt": 0.0, "completion": 0.0},
    "poolside/laguna-m.1": {"prompt": 0.0, "completion": 0.0},
    ":free": {"prompt": 0.0, "completion": 0.0},
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates = MODEL_COST_PER_1M.get(model)
    if not rates:
        for key, val in MODEL_COST_PER_1M.items():
            if key in model:
                rates = val
                break
    rates = rates or {"prompt": 1.0, "completion": 3.0}
    return (prompt_tokens * rates["prompt"] + completion_tokens * rates["completion"]) / 1_000_000


async def log_llm_usage(
    session_id: UUID,
    conversation_id: UUID,
    agent_name: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int | None = None,
) -> None:
    _ = get_settings()
    cost = estimate_cost(model, prompt_tokens, completion_tokens)
    try:
        async with async_session_factory() as db:
            db.add(
                LLMUsageLog(
                    session_id=session_id,
                    conversation_id=conversation_id,
                    agent_name=agent_name,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    estimated_cost=cost,
                    latency_ms=latency_ms,
                )
            )
            await db.commit()
    except Exception as exc:
        logger.debug("llm_usage log skipped (db unavailable): %s", exc)
