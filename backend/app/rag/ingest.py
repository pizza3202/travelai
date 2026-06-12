"""
RAG ingest pipeline.

Usage:
  python -m app.rag.ingest
  python -m app.rag.ingest --guides-path ../datasets/destination_guides
"""

from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path

from sqlalchemy import delete, select

from app.config import get_settings
from app.db.models import Document
from app.db.session import async_session_factory, init_db
from app.rag.embeddings import embed_texts


def chunk_markdown(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
    return chunks


def destination_key_from_filename(path: Path) -> str:
    return path.stem.replace("_", " ").lower()


async def ingest_guides(guides_path: Path, *, clear_existing: bool = True) -> int:
    await init_db()
    guide_files = sorted(guides_path.glob("*.md"))
    if not guide_files:
        print(f"No .md guides found in {guides_path}")
        return 0

    total = 0
    async with async_session_factory() as db:
        for guide_file in guide_files:
            dest_key = destination_key_from_filename(guide_file)
            text = guide_file.read_text(encoding="utf-8")
            chunks = chunk_markdown(text)
            if clear_existing:
                await db.execute(
                    delete(Document).where(Document.destination_key == dest_key)
                )

            vectors = await embed_texts(chunks)
            for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
                db.add(
                    Document(
                        destination_key=dest_key,
                        source_file=guide_file.name,
                        chunk_index=idx,
                        content=chunk,
                        embedding=vector,
                        metadata_={"char_count": len(chunk)},
                    )
                )
                total += 1
            print(f"Ingested {len(chunks)} chunks for {dest_key} ({guide_file.name})")

        await db.commit()
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest destination guides into pgvector")
    parser.add_argument(
        "--guides-path",
        type=Path,
        default=None,
        help="Path to destination_guides directory",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Do not delete existing chunks for each destination before ingest",
    )
    args = parser.parse_args()
    settings = get_settings()
    guides_path = args.guides_path or settings.guides_path
    if not guides_path.exists():
        print(f"Guides path not found: {guides_path}")
        return
    count = asyncio.run(ingest_guides(guides_path, clear_existing=not args.no_clear))
    print(f"Done — {count} chunks stored.")


if __name__ == "__main__":
    main()
