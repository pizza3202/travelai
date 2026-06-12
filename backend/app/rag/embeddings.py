"""Text embeddings for RAG — OpenRouter API with deterministic fallback."""

from __future__ import annotations

import hashlib
import math
from typing import Sequence

import httpx

from app.config import get_settings

EMBED_DIM = 384


def _hash_embed(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Deterministic local embedding for dev without API keys."""
    vec = [0.0] * dim
    for token in text.lower().split():
        digest = hashlib.sha256(token.encode()).digest()
        for i in range(dim):
            vec[i] += (digest[i % len(digest)] / 255.0) - 0.5
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


async def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    settings = get_settings()
    if settings.openrouter_api_key:
        return await _openrouter_embed(texts, settings)
    return [_hash_embed(t) for t in texts]


async def embed_query(text: str) -> list[float]:
    vectors = await embed_texts([text])
    return vectors[0]


async def _openrouter_embed(texts: Sequence[str], settings) -> list[list[float]]:
    url = f"{settings.openrouter_base_url.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": "openai/text-embedding-3-small", "input": list(texts)}
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()["data"]
        return [item["embedding"] for item in sorted(data, key=lambda x: x["index"])]
