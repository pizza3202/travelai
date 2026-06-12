"""Load mock JSON datasets."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.config import get_settings


def _mock_dir() -> Path:
    return Path(get_settings().datasets_path) / "mock"


@lru_cache(maxsize=32)
def _load_json(name: str) -> dict:
    path = _mock_dir() / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_key(destination: str) -> str:
    key = destination.lower().strip().replace(" ", "_")
    aliases = {
        "tokyo": "japan",
        "kyoto": "japan",
        "japan": "japan",
        "sf": "san_francisco",
        "san_francisco": "san_francisco",
        "nyc": "new_york",
        "new_york": "new_york",
        "paris": "paris",
        "london": "london",
    }
    return aliases.get(key, key)


def load_mock_flights(departure: str, destination: str) -> list[dict]:
    data = _load_json("flights.json")
    route_key = f"{departure.lower()}_{_normalize_key(destination)}"
    return data.get(route_key) or data.get("default", [])


def load_mock_hotels(destination: str) -> list[dict]:
    data = _load_json("hotels.json")
    key = _normalize_key(destination)
    return data.get(key) or data.get("default", [])


def load_mock_activities(destination: str) -> list[dict]:
    data = _load_json("activities.json")
    key = _normalize_key(destination)
    return data.get(key) or data.get("default", [])
