"""Unified LLM client: OpenRouter (primary) + optional Ollama fallback."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from pydantic import BaseModel

from app.config import get_settings
from app.observability.usage_logger import log_llm_usage

logger = logging.getLogger(__name__)


class LLMUnavailableError(Exception):
    """No API keys and Ollama fallback disabled."""


@dataclass
class LLMResult:
    content: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int


def llm_available() -> bool:
    s = get_settings()
    if s.llm_provider == "openrouter":
        return bool(s.openrouter_api_key) or s.use_ollama_fallback
    if s.llm_provider == "ollama" or s.use_ollama_fallback:
        return True
    if s.llm_provider == "auto" and s.openrouter_api_key:
        return True
    return bool(s.openrouter_api_key)


def _resolve_provider() -> str:
    s = get_settings()
    if s.llm_provider == "openrouter" and s.openrouter_api_key:
        return "openrouter"
    if s.llm_provider == "auto" and s.openrouter_api_key:
        return "openrouter"
    if s.openrouter_api_key:
        return "openrouter"
    if s.use_ollama_fallback or s.llm_provider == "ollama":
        return "ollama"
    raise LLMUnavailableError(
        "Set OPENROUTER_API_KEY in backend/.env (LLM_PROVIDER=openrouter) or enable USE_OLLAMA_FALLBACK"
    )


def llm_judge_rater_label() -> str:
    """Eval rater B label for the active LLM provider (e.g. openrouter_judge)."""
    return f"{_resolve_provider()}_judge"


def _parse_json_content(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


async def complete_text(
    *,
    agent_name: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    session_id: str | None = None,
    conversation_id: str | None = None,
    temperature: float = 0.2,
) -> LLMResult:
    """Chat completion; logs usage when session ids provided."""
    provider = _resolve_provider()
    start = time.perf_counter()

    if provider == "openrouter":
        result = await _openrouter_complete(model, system, user, max_tokens, temperature)
    else:
        result = await _ollama_complete(model, system, user, max_tokens)

    result.latency_ms = int((time.perf_counter() - start) * 1000)
    result.provider = provider

    if session_id and conversation_id:
        try:
            await log_llm_usage(
                UUID(session_id),
                UUID(conversation_id),
                agent_name,
                result.model,
                result.prompt_tokens,
                result.completion_tokens,
                result.latency_ms,
            )
        except (ValueError, TypeError):
            pass

    return result


async def complete_json(
    *,
    agent_name: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    output_model: type[BaseModel],
    session_id: str | None = None,
    conversation_id: str | None = None,
) -> BaseModel:
    """Request JSON and validate against a Pydantic model."""
    system_json = (
        system
        + "\nRespond with valid JSON only, no markdown. "
        + f"Schema: {output_model.model_json_schema()}"
    )
    result = await complete_text(
        agent_name=agent_name,
        model=model,
        system=system_json,
        user=user,
        max_tokens=max_tokens,
        session_id=session_id,
        conversation_id=conversation_id,
        temperature=0.1,
    )
    data = _parse_json_content(result.content)
    return output_model.model_validate(data)


async def _openrouter_complete(
    model: str, system: str, user: str, max_tokens: int, temperature: float
) -> LLMResult:
    settings = get_settings()
    url = f"{settings.openrouter_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/travelai",
        "X-Title": "TravelAI",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = None
        for attempt in range(4):
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 429 and attempt < 3:
                await asyncio.sleep(2**attempt)
                continue
            break
        assert resp is not None
        if resp.is_error:
            detail = resp.text[:500] if resp.text else resp.reason_phrase
            logger.warning(
                "OpenRouter error %s for model %s: %s",
                resp.status_code,
                model,
                detail,
            )
        resp.raise_for_status()
        data = resp.json()
    choice = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return LLMResult(
        content=choice or "",
        model=data.get("model", model),
        provider="openrouter",
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        latency_ms=0,
    )


async def _ollama_complete(model: str, system: str, user: str, max_tokens: int) -> LLMResult:
    settings = get_settings()
    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
    payload = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"num_predict": max_tokens},
        "format": "json",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    msg = data.get("message", {}).get("content", "")
    return LLMResult(
        content=msg,
        model=settings.ollama_model,
        provider="ollama",
        prompt_tokens=data.get("prompt_eval_count", 0),
        completion_tokens=data.get("eval_count", 0),
        latency_ms=0,
    )


def model_for_agent(agent_name: str) -> str:
    s = get_settings()
    if agent_name == "synthesizer":
        return s.model_synthesizer
    if agent_name == "validator":
        return s.model_validator
    return s.model_planner


def max_tokens_for_agent(agent_name: str) -> int:
    s = get_settings()
    if agent_name == "eval_judge":
        return min(s.agent_max_tokens_planner, 1024)
    if agent_name == "synthesizer":
        return s.agent_max_tokens_synthesizer
    if agent_name == "validator":
        return min(s.agent_max_tokens_planner, 512)
    return s.agent_max_tokens_planner
