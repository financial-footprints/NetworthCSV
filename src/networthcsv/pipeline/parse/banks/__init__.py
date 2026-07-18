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
    return _BANK_PARSERS.get(bank, variant)


from networthcsv.pipeline.parse.banks import hdfc as _hdfc  # noqa: E402, F401
from networthcsv.pipeline.parse.banks import icici as _icici  # noqa: E402, F401
from networthcsv.pipeline.parse.banks import idfc as _idfc  # noqa: E402, F401
from networthcsv.pipeline.parse.banks import indusind as _indusind  # noqa: E402, F401
from networthcsv.pipeline.parse.banks import bob as _bob  # noqa: E402, F401
from networthcsv.pipeline.parse.banks import yes as _yes  # noqa: E402, F401
from networthcsv.pipeline.parse.banks import pnb as _pnb  # noqa: E402, F401
from networthcsv.pipeline.parse.banks import federal as _federal  # noqa: E402, F401
from networthcsv.pipeline.parse.banks import csb as _csb  # noqa: E402, F401
