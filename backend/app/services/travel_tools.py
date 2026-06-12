"""Shared read-only travel tools — used by LangGraph agents and MCP server."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.tools.mock_loader import load_mock_activities, load_mock_flights, load_mock_hotels

ESTIMATE_NOTE = "estimate only — not a booking"


def _datasets_root() -> Path:
    return Path(get_settings().datasets_path)


async def search_hotels(
    destination: str,
    budget_per_night: float,
    dates: str | None = None,
    *,
    force_fail: bool = False,
) -> list[dict[str, Any]]:
    """Search hotel estimates (mock)."""
    try:
        if force_fail:
            raise RuntimeError("simulated tool failure")
        hotels = load_mock_hotels(destination)
        filtered = [
            h
            for h in hotels
            if h.get("price_per_night_usd", 9999) <= budget_per_night * 1.2
        ]
        if not filtered:
            filtered = hotels[:2]
        for h in filtered:
            h["note"] = ESTIMATE_NOTE
        return filtered
    except Exception:
        fallback = load_mock_hotels("_fallback")
        for h in fallback:
            h["note"] = ESTIMATE_NOTE + " (fallback)"
        return fallback


async def search_activities(
    destination: str,
    interests: list[str],
    budget: float,
    *,
    force_fail: bool = False,
) -> list[dict[str, Any]]:
    """Search activity estimates (mock; RAG enriches activity agent)."""
    try:
        if force_fail:
            raise RuntimeError("simulated tool failure")
        activities = load_mock_activities(destination)
        interest_set = {i.lower() for i in interests}
        if interest_set:
            activities = [
                a
                for a in activities
                if a.get("category", "").lower() in interest_set
                or not interest_set
            ] or activities
        total = sum(a.get("estimated_cost_usd", 0) for a in activities)
        if total > budget:
            activities = activities[: max(3, len(activities) // 2)]
        for a in activities:
            a["note"] = ESTIMATE_NOTE
        return activities
    except Exception:
        return load_mock_activities("_fallback")


async def estimate_transport(destination: str, days: int) -> list[dict[str, Any]]:
    """Estimate transportation (mock)."""
    path = _datasets_root() / "mock" / "transport.json"
    if path.exists():
        data = json.loads(path.read_text())
        key = destination.lower().replace(" ", "_")
        plans = data.get(key) or data.get("default", [])
    else:
        plans = [
            {
                "mode": "transit_pass",
                "description": f"Multi-day transit pass in {destination}",
                "estimated_cost_usd": 45 + days * 8,
            }
        ]
    for p in plans:
        p["note"] = ESTIMATE_NOTE
    return plans


async def get_destination_facts(destination: str) -> dict[str, Any]:
    """Load destination guide metadata and facts (file-based fallback)."""
    settings = get_settings()
    guides = settings.guides_path
    mapping = {
        "japan": "japan.md",
        "tokyo": "japan.md",
        "kyoto": "japan.md",
        "san francisco": "san_francisco.md",
        "sf": "san_francisco.md",
        "new york": "new_york.md",
        "nyc": "new_york.md",
        "paris": "paris.md",
        "london": "london.md",
    }
    key = destination.lower().strip()
    filename = mapping.get(key)
    if not filename:
        for k, f in mapping.items():
            if k in key:
                filename = f
                break
    if not filename:
        return {"destination": destination, "facts": [], "guide_available": False}
    guide_path = guides / filename
    if not guide_path.exists():
        return {"destination": destination, "facts": [], "guide_available": False}
    content = guide_path.read_text(encoding="utf-8")
    return {
        "destination": destination,
        "guide_file": filename,
        "guide_available": True,
        "excerpt": content[:1500],
        "note": ESTIMATE_NOTE,
    }


async def search_flights(
    departure_city: str,
    destination: str,
    budget: float,
    *,
    force_fail: bool = False,
) -> list[dict[str, Any]]:
    """Flight estimates from mock dataset."""
    try:
        if force_fail:
            raise RuntimeError("simulated tool failure")
        flights = load_mock_flights(departure_city, destination)
        flights = [f for f in flights if f.get("estimated_cost_usd", 0) <= budget * 0.5]
        if not flights:
            flights = load_mock_flights(departure_city, destination)[:2]
        for f in flights:
            f["note"] = ESTIMATE_NOTE
        return flights
    except Exception:
        return load_mock_flights("_default", "_fallback")
