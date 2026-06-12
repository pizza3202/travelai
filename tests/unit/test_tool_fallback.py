"""Test 7: tool failure uses fallback."""

import pytest

from app.services.travel_tools import search_hotels


@pytest.mark.asyncio
async def test_hotel_tool_fallback_on_failure():
    result = await search_hotels("Nowhere", 100, force_fail=True)
    assert len(result) >= 1
    assert "fallback" in result[0].get("note", "").lower() or result[0].get("name")
