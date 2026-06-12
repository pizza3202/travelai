"""LLM planner — fallback to rules without API keys."""

import pytest

from app.config.settings import get_settings
from app.services.llm_client import llm_available
from app.services.planner_service import extract_travel_brief, extract_travel_brief_async


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_llm_unavailable_without_keys(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("USE_OLLAMA_FALLBACK", "false")
    get_settings.cache_clear()
    assert llm_available() is False


@pytest.mark.asyncio
async def test_async_planner_falls_back_to_rules(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("USE_OLLAMA_FALLBACK", "false")
    get_settings.cache_clear()

    msg = "Plan a 5-day Japan trip under $2500. I like food."
    brief = await extract_travel_brief_async(msg, "San Francisco")
    rule_brief = extract_travel_brief(msg, "San Francisco")

    assert brief.duration_days == rule_brief.duration_days == 5
    assert brief.budget_usd == rule_brief.budget_usd == 2500.0
    assert not brief.needs_clarification
