"""Metadata stage: build per-account metadata from canonical statement files."""

from networthcsv.pipeline.metadata.build import (
    build_account_metadata,
    build_yearly_statement_summaries,
)
from networthcsv.pipeline.metadata.coverage import (
    build_period_covered,
    compute_balance_gaps,
    covered_month,
    months_between_exclusive,
    statement_date_for_covered_month,
)
from networthcsv.pipeline.metadata.models import (
    AccountMetadata,
    BalanceGap,
    StatementMetadata,
)
from networthcsv.pipeline.metadata.persist import (
    load_account_metadata,
    read_account_metadata,
    refresh_account_metadata,
)
from networthcsv.pipeline.metadata.run import main, run, run_account

__all__ = [
    "AccountMetadata",
    "BalanceGap",
    "StatementMetadata",
    "build_account_metadata",
    "build_period_covered",
    "build_yearly_statement_summaries",
    "compute_balance_gaps",
    "covered_month",
    "load_account_metadata",
    "main",
    "months_between_exclusive",
    "read_account_metadata",
    "refresh_account_metadata",
    "run",
    "run_account",
    "statement_date_for_covered_month",
]
