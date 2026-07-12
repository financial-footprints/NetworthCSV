"""Shared private validators for settings and bank matching."""

from __future__ import annotations

from collections.abc import Callable


def optional_normalizer(
    normalizer: Callable[[object], object],
) -> Callable[[object], object]:
    def wrap(value: object) -> object:
        if value is None or value == "":
            return None
        return normalizer(value)

    return wrap
