"""Parse sanitized statement text files into transactions."""

from __future__ import annotations

from networthcsv.errors import StageError
from networthcsv.pipeline.parse.banks import get_parser
from networthcsv.settings import ResolvedAccount
from networthcsv.utils.transactions import Transaction


def parse_statement_text(
    text: str,
    *,
    account: ResolvedAccount,
    source_file: str,
) -> list[Transaction]:
    """Parse a sanitized statement .txt file into transaction rows."""
    try:
        parser = get_parser(account.bank, account.variant)
    except KeyError as exc:
        raise StageError(
            f"no statement parser registered for bank {account.bank!r}"
            + (f" variant {account.variant!r}" if account.variant else "")
        ) from exc
    return parser.parse(text, account=account, source_file=source_file)
