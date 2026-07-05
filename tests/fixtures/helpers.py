"""Shared paths and manifest loader for metadata sample fixtures."""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = FIXTURES_ROOT / "metadata_manifest.json"
REQUIRED_MANIFEST_KEYS = ("statement_month", "opening", "closing")


def load_manifest() -> dict[str, dict[str, str | None]]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def list_fixture_paths() -> list[str]:
    """Relative paths to all bank statement text fixtures (excludes helpers/manifest)."""
    paths: list[str] = []
    for path in sorted(FIXTURES_ROOT.rglob("*.txt")):
        rel = path.relative_to(FIXTURES_ROOT).as_posix()
        parts = rel.split("/")
        if len(parts) < 3:
            continue
        paths.append(rel)
    return paths
