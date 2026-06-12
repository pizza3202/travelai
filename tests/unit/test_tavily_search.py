"""Tavily web search helpers — no API key required."""

from app.services.tavily_search import (
    build_search_query,
    search_travel_web,
    should_use_web_search,
    snippets_as_context,
)


def test_should_not_search_without_api_key(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "")
    from app.config.settings import get_settings

    get_settings.cache_clear()
    assert should_use_web_search("latest events in Tokyo", rag_chunk_count=0) is False
    get_settings.cache_clear()


def test_should_search_on_freshness_keyword(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("TAVILY_ENABLED", "true")
    from app.config.settings import get_settings

    get_settings.cache_clear()
    assert should_use_web_search("latest festivals in Paris", rag_chunk_count=5) is True
    get_settings.cache_clear()


def test_snippets_format():
    chunks = snippets_as_context(
        [{"title": "Event", "snippet": "A local festival this month."}]
    )
    assert chunks[0].startswith("[Web]")


def test_build_search_query():
    q = build_search_query("Japan", ["food", "culture"], "Plan a 5-day trip")
    assert "Japan" in q
    assert "food" in q


async def test_search_returns_empty_without_key():
    from app.config.settings import get_settings

    get_settings.cache_clear()
    results = await search_travel_web("Tokyo", ["food"], "latest food events")
    assert results == []
    get_settings.cache_clear()
