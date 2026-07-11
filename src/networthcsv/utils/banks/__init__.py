# Adding a new bank variant:
# 1. Create utils/banks/<bank>/<variant>.py with a handler class (subclass default or CreditCardHandler).
# 2. Decorate with @register("bank", "variant") or import the module in this package.
# 3. Add the account to user.config.json (bank + variant; optional mail/text_contains overrides).

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from networthcsv.utils.banks.base import BankHandler

_HANDLERS: dict[str, BankHandler] = {}

HandlerT = TypeVar("HandlerT", bound=BankHandler)


def register(
    bank: str, variant: str | None = None
) -> Callable[[type[HandlerT]], type[HandlerT]]:
    def decorator(cls: type[HandlerT]) -> type[HandlerT]:
        key = _handler_key(bank, variant)
        _HANDLERS[key] = cls()
        return cls

    return decorator


def _handler_key(bank: str, variant: str | None) -> str:
    bank_key = bank.strip().lower()
    if variant is None or variant.strip().lower() in {"", "default"}:
        return f"{bank_key}/default"
    return f"{bank_key}/{variant.strip().lower()}"


def get_handler(bank: str, variant: str | None = None) -> BankHandler:
    bank_key = bank.strip().lower()
    if variant:
        exact = _handler_key(bank_key, variant)
        handler = _HANDLERS.get(exact)
        if handler is not None:
            return handler
    default_handler = _HANDLERS.get(_handler_key(bank_key, None))
    if default_handler is not None:
        return default_handler
    known = ", ".join(sorted(_HANDLERS)) or "(none registered)"
    raise KeyError(
        f"no bank handler for {bank_key!r}"
        + (f" variant {variant!r}" if variant else "")
        + f" (known: {known})"
    )


def list_handlers() -> tuple[str, ...]:
    return tuple(sorted(_HANDLERS))


# Import bank modules for registration side effects.
from networthcsv.utils.banks import (  # noqa: E402, F401
    bob,
    csb,
    federal,
    hdfc,
    icici,
    idfc,
    indusind,
    pnb,
    yes,
)

__all__ = ["BankHandler", "get_handler", "list_handlers", "register"]
