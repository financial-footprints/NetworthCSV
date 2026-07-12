"""Bank-specific statement parsers."""

from __future__ import annotations

from networthcsv.pipeline.parse.banks.base import StatementParser
from networthcsv.pipeline.parse.banks.stub import StubStatementParser
from networthcsv.utils.registry import Registry

_DEFAULT_PARSER = StubStatementParser()
_BANK_PARSERS: Registry[StatementParser] = Registry(default=_DEFAULT_PARSER)


def register_parser(bank: str, variant: str | None = None):
    def decorator(parser_cls: type[StatementParser]) -> type[StatementParser]:
        _BANK_PARSERS.register(bank, variant, parser_cls())
        return parser_cls

    return decorator


def get_parser(bank: str, variant: str | None = None) -> StatementParser:
    if variant:
        try:
            return _BANK_PARSERS.get(bank, variant)
        except KeyError:
            pass
    return _BANK_PARSERS.get(bank, None)


from networthcsv.pipeline.parse.banks import hdfc as _hdfc  # noqa: E402, F401
from networthcsv.pipeline.parse.banks import idfc as _idfc  # noqa: E402, F401
