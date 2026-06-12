"""Pytest configuration — add backend to Python path."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

# Ensure datasets resolve for tests
import os

os.environ.setdefault(
    "DATASETS_PATH",
    str(ROOT / "datasets"),
)
