"""Reusable statement date extraction mixins for bank handlers."""

from __future__ import annotations

from datetime import date

from networthcsv.utils.banks.helpers.dates import (
    context_range_end,
    context_range_period,
    first_not_none_date,
    label_range_end,
    label_range_period,
    label_single_date_end,
    top_range_end,
    top_range_period,
)


class ContextRangePeriodMixin:
    def period_context(self) -> str:
        raise NotImplementedError

    def period_joiner(self) -> str:
        raise NotImplementedError

    def get_statement_date(self, text: str) -> date | None:
        return context_range_end(text, self.period_context(), self.period_joiner())

    def get_statement_period(self, text: str) -> tuple[date | None, date | None]:
        period_start, period_end = context_range_period(
            text, self.period_context(), self.period_joiner()
        )
        if period_start is not None and period_end is not None:
            return period_start, period_end
        end = self.get_statement_date(text)
        if end is not None:
            return None, end
        return None, None


class TopRangeDateMixin:
    def top_range_joiner(self) -> str:
        return " - "

    def top_range_search_chars(self) -> int:
        return 2000

    def get_statement_date(self, text: str) -> date | None:
        return top_range_end(
            text,
            self.top_range_joiner(),
            search_chars=self.top_range_search_chars(),
        )

    def get_statement_period(self, text: str) -> tuple[date | None, date | None]:
        period_start, period_end = top_range_period(
            text,
            self.top_range_joiner(),
            search_chars=self.top_range_search_chars(),
        )
        if period_start is not None and period_end is not None:
            return period_start, period_end
        end = self.get_statement_date(text)
        if end is not None:
            return None, end
        return None, None


class BobDateMixin:
    def get_statement_date(self, text: str) -> date | None:
        return first_not_none_date(
            label_single_date_end(text, "Statement Date :"),
            label_range_end(text, "Statement Period :", " to "),
            top_range_end(text, " To ", search_chars=500),
        )

    def get_statement_period(self, text: str) -> tuple[date | None, date | None]:
        period_start, period_end = label_range_period(
            text, "Statement Period :", " to "
        )
        if period_start is not None and period_end is not None:
            return period_start, period_end
        period_start, period_end = top_range_period(text, " To ", search_chars=500)
        if period_start is not None and period_end is not None:
            return period_start, period_end
        end = self.get_statement_date(text)
        if end is not None:
            return None, end
        return None, None
