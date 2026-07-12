# Adding a new bank variant:
# 1. Create utils/banks/<bank>/<variant>.py with a handler class (subclass default or CreditCardHandler).
# 2. Decorate with @register("bank", "variant") or import the module in this package.
# 3. Add the account to user.config.json (bank + variant; optional mail/text_contains overrides).

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from networthcsv.utils.banks.base import BankHandler
from networthcsv.utils.registry import Registry, handler_registry_key

_HANDLERS: Registry[BankHandler] = Registry(key_for=handler_registry_key)

HandlerT = TypeVar("HandlerT", bound=BankHandler)


def register(
    bank: str, variant: str | None = None
) -> Callable[[type[HandlerT]], type[HandlerT]]:
    def decorator(cls: type[HandlerT]) -> type[HandlerT]:
        _HANDLERS.register(bank, variant, cls())
        return cls

    return decorator


def get_handler(bank: str, variant: str | None = None) -> BankHandler:
    return _HANDLERS.get(bank, variant)


def list_handlers() -> tuple[str, ...]:
    return _HANDLERS.keys()


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

__all__ = ["get_handler", "list_handlers", "register"]
