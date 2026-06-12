"""RAG retriever — pgvector search with file-based fallback."""

from __future__ import annotations

import re

from sqlalchemy import select, text

from app.config import get_settings
from app.db.models import Document
from app.db.session import async_session_factory
from app.rag.embeddings import embed_query
from app.services.travel_tools import get_destination_facts


def _normalize_destination(destination: str) -> str:
    return re.sub(r"\s+", " ", destination.strip().lower())


def _destination_aliases(destination: str) -> list[str]:
    key = _normalize_destination(destination)
    aliases = {key.replace(" ", "_"), key}
    if "tokyo" in key:
        aliases.add("japan")
    if "japan" in key:
        aliases.add("japan")
    if "paris" in key:
        aliases.add("paris")
    if "london" in key:
        aliases.add("london")
    if "new york" in key or key == "nyc":
        aliases.update({"new york", "new_york"})
    if "san francisco" in key or key == "sf":
        aliases.update({"san francisco", "san_francisco"})
    return list(aliases)


async def _retrieve_from_db(
    destination: str,
    interests: list[str] | None,
    top_k: int,
) -> list[str]:
    aliases = _destination_aliases(destination)
    query_text = destination + (" " + " ".join(interests) if interests else "")
    query_vec = await embed_query(query_text)

    async with async_session_factory() as db:
        try:
            result = await db.execute(
                text(
                    """
                    SELECT content
                    FROM documents
                    WHERE destination_key = ANY(:keys)
                      AND embedding IS NOT NULL
                    ORDER BY embedding <=> CAST(:query_vec AS vector)
                    LIMIT :top_k
                    """
                ),
                {"keys": aliases, "query_vec": str(query_vec), "top_k": top_k},
            )
            rows = [row[0] for row in result.fetchall()]
            if rows:
                return rows

            orm_result = await db.execute(
                select(Document.content)
                .where(Document.destination_key.in_(aliases))
                .order_by(Document.chunk_index)
                .limit(top_k)
            )
            return [row[0] for row in orm_result.fetchall()]
        except Exception:
            return []


async def retrieve_destination_context(
    destination: str,
    interests: list[str] | None = None,
    top_k: int | None = None,
) -> list[str]:
    settings = get_settings()
    k = top_k or settings.rag_top_k

    db_chunks = await _retrieve_from_db(destination, interests, k)
    if db_chunks:
        if interests:
            interest_set = {i.lower() for i in interests}
            scored = [
                (sum(1 for i in interest_set if i in c.lower()), c) for c in db_chunks
            ]
            scored.sort(key=lambda x: x[0], reverse=True)
            return [c for _, c in scored[:k]]
        return db_chunks[:k]

    facts = await get_destination_facts(destination)
    if not facts.get("guide_available"):
        return []

    excerpt = facts.get("excerpt", "")
    paragraphs = [p.strip() for p in excerpt.split("\n\n") if p.strip()]
    if interests:
        interest_set = {i.lower() for i in interests}
        scored = []
        for c in paragraphs:
            score = sum(1 for i in interest_set if i in c.lower())
            scored.append((score, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:k] if c]
    return paragraphs[:k]
