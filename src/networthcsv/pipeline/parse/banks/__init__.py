"""Bank-specific statement parsers."""

from __future__ import annotations

from networthcsv.pipeline.parse.banks.base import StatementParser
from networthcsv.pipeline.parse.banks.stub import StubStatementParser

_DEFAULT_PARSER = StubStatementParser()

_BANK_PARSERS: dict[str, StatementParser] = {}


def register_parser(bank: str, variant: str | None = None):
    def decorator(parser_cls: type[StatementParser]) -> type[StatementParser]:
        key = bank.strip().lower()
        if variant:
            key = f"{key}/{variant.strip().lower()}"
        _BANK_PARSERS[key] = parser_cls()
        return parser_cls

    return decorator


def get_parser(bank: str, variant: str | None = None) -> StatementParser:
    bank_key = bank.strip().lower()
    if variant:
        variant_key = f"{bank_key}/{variant.strip().lower()}"
        parser = _BANK_PARSERS.get(variant_key)
        if parser is not None:
            return parser
    return _BANK_PARSERS.get(bank_key, _DEFAULT_PARSER)


from networthcsv.pipeline.parse.banks import hdfc as _hdfc  # noqa: E402, F401
from networthcsv.pipeline.parse.banks import idfc as _idfc  # noqa: E402, F401
