"""
Tavily web search — supplementary to RAG (destination guides stay primary).

Chain: RAG (pgvector + guides) → Tavily (optional live search) → mock fallback.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"

# User asks for timely / event-style info → use web search in addition to RAG
_FRESHNESS_KEYWORDS = re.compile(
    r"\b(latest|current|recent|today|this year|202[4-9]|events?|festival|opening|news)\b",
    re.I,
)


def should_use_web_search(user_message: str, rag_chunk_count: int) -> bool:
    """Decide if Tavily should run (RAG always runs regardless)."""
    settings = get_settings()
    if not settings.tavily_api_key or not settings.tavily_enabled:
        return False
    if _FRESHNESS_KEYWORDS.search(user_message):
        return True
    return rag_chunk_count < settings.tavily_min_rag_chunks


def build_search_query(destination: str, interests: list[str], user_message: str) -> str:
    interest_part = " ".join(interests[:3]) if interests else "travel"
    return (
        f"{destination} {interest_part} activities things to do — "
        f"context: {user_message[:200]}"
    ).strip()


async def search_travel_web(
    destination: str,
    interests: list[str],
    user_message: str,
    *,
    max_results: int | None = None,
) -> list[dict[str, Any]]:
    """
    Search the web via Tavily. Returns snippets for agent context (not bookings).

    Each item: {title, snippet, url, source: "tavily"}
    """
    settings = get_settings()
    if not settings.tavily_api_key or not settings.tavily_enabled:
        return []

    query = build_search_query(destination, interests, user_message)
    limit = max_results or settings.tavily_max_results
    payload = {
        "api_key": settings.tavily_api_key,
        "query": query,
        "search_depth": settings.tavily_search_depth,
        "max_results": limit,
        "include_answer": False,
    }

    try:
        async with httpx.AsyncClient(timeout=settings.tavily_timeout_seconds) as client:
            resp = await client.post(TAVILY_API_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Tavily search failed, skipping web context: %s", exc)
        return []

    results: list[dict[str, Any]] = []
    for item in data.get("results", [])[:limit]:
        snippet = (item.get("content") or item.get("snippet") or "")[:500]
        if not snippet:
            continue
        results.append(
            {
                "title": item.get("title", "Web result"),
                "snippet": snippet,
                "url": item.get("url"),
                "source": "tavily",
            }
        )
    return results


def snippets_as_context(web_results: list[dict[str, Any]]) -> list[str]:
    """Format Tavily hits as text chunks for Synthesizer / Activity (separate from RAG)."""
    chunks: list[str] = []
    for r in web_results:
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        chunks.append(f"[Web] {title}: {snippet}")
    return chunks
