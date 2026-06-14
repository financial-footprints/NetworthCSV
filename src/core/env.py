"""Environment variable helpers."""

from __future__ import annotations

import os

_TRUTHY = frozenset({"1", "true", "yes"})


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY
