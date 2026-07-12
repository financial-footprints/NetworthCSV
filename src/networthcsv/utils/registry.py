"""Shared bank/variant registry helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

T = TypeVar("T")


def normalize_bank_key(bank: str) -> str:
    return bank.strip().lower()


def normalize_variant_segment(variant: str | None) -> str | None:
    if variant is None:
        return None
    cleaned = variant.strip().lower()
    if cleaned in {"", "default"}:
        return None
    return cleaned


def bank_variant_key(bank: str, variant: str | None) -> str:
    bank_key = normalize_bank_key(bank)
    variant_key = normalize_variant_segment(variant)
    if variant_key is None:
        return bank_key
    return f"{bank_key}/{variant_key}"


def handler_registry_key(bank: str, variant: str | None) -> str:
    bank_key = normalize_bank_key(bank)
    variant_key = normalize_variant_segment(variant)
    if variant_key is None:
        return f"{bank_key}/default"
    return f"{bank_key}/{variant_key}"


class Registry(Generic[T]):
    def __init__(
        self,
        *,
        default: T | None = None,
        key_for: Callable[[str, str | None], str] = bank_variant_key,
    ) -> None:
        self._items: dict[str, T] = {}
        self._default = default
        self._key_for = key_for

    def register(self, bank: str, variant: str | None, value: T) -> None:
        self._items[self._key_for(bank, variant)] = value

    def get(self, bank: str, variant: str | None = None) -> T:
        bank_key = normalize_bank_key(bank)
        variant_key = normalize_variant_segment(variant)
        if variant_key is not None:
            exact = self._items.get(self._key_for(bank_key, variant_key))
            if exact is not None:
                return exact
        fallback = self._items.get(self._key_for(bank_key, None))
        if fallback is not None:
            return fallback
        if self._default is not None:
            return self._default
        known = ", ".join(sorted(self._items)) or "(none registered)"
        raise KeyError(
            f"no registry entry for {bank_key!r}"
            + (f" variant {variant!r}" if variant else "")
            + f" (known: {known})"
        )

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._items))
