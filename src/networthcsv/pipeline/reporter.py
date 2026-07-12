"""Format pipeline progress and results for CLI output."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from networthcsv.pipeline.results import (
    CleanupAccountResult,
    ExtractAccountResult,
    ExtractStageResult,
    MetadataAccountResult,
    ParseAccountResult,
    ParseFyResult,
)
from networthcsv.settings import ResolvedAccount, account_label, format_account_date


def format_run_settings_lines(
    *,
    bank: str | None,
    subjects: list[str],
    from_filters: list[str],
    body_contains: list[str],
    download_dir: Path,
    start_date: date | None,
    end_date: date | None = None,
    extras: tuple[tuple[str, str], ...] = (),
) -> list[str]:
    lines = ["settings:"]
    if bank:
        lines.append(f"  bank:          {bank}")
    for label, value in extras:
        lines.append(f"  {label + ':':14s}{value}")
    lines.append(f"  subjects:      {subjects!r}")
    if from_filters:
        lines.append(f"  from:          {from_filters!r}")
    if body_contains:
        lines.append(f"  body_contains: {body_contains!r}")
    lines.append(f"  download_path: {download_dir}")
    if start_date is None:
        lines.append("  start_date:    (all emails)")
    else:
        lines.append(f"  start_date:    {format_account_date(start_date)}")
    if end_date is None:
        lines.append("  end_date:      (no limit)")
    else:
        lines.append(f"  end_date:      {format_account_date(end_date)}")
    return lines


class RunReporter:
    def blank_line(self) -> None:
        pass

    def account_banner(
        self, account: ResolvedAccount, *, index: int, total: int
    ) -> None:
        pass

    def extract_settings(
        self,
        *,
        bank: str | None,
        subjects: list[str],
        from_filters: list[str],
        body_contains: list[str],
        download_dir: Path,
        start_date: date | None,
        end_date: date | None = None,
        extras: tuple[tuple[str, str], ...] = (),
    ) -> None:
        pass

    def extract_search(self, candidate_count: int, folder: str) -> None:
        pass

    def extract_scanning_mbox(self, mbox_path: Path) -> None:
        pass

    def extract_mbox_progress(self, matched: int, saved: int) -> None:
        pass

    def extract_account_done(self, result: ExtractAccountResult) -> None:
        pass

    def cleanup_started(self, result_bank: str, download_dir: Path) -> None:
        pass

    def cleanup_skipped(self, bank: str, download_dir: Path) -> None:
        pass

    def cleanup_done(self, result: CleanupAccountResult) -> None:
        pass

    def metadata_started(self, bank: str, download_dir: Path) -> None:
        pass

    def metadata_done(self, result: MetadataAccountResult) -> None:
        pass

    def parse_started(self, bank: str, download_dir: Path) -> None:
        pass

    def parse_skipped(self, bank: str, download_dir: Path) -> None:
        pass

    def parse_fy_started(self, fy_name: str) -> None:
        pass

    def parse_fy_skipped(self, fy_name: str) -> None:
        pass

    def parse_statement(self, txt_name: str, transaction_count: int) -> None:
        pass

    def parse_fy_done(self, result: ParseFyResult) -> None:
        pass

    def parse_account_done(self, result: ParseAccountResult) -> None:
        pass


class NullRunReporter(RunReporter):
    """No-op reporter for library embedders."""


class ConsoleRunReporter(RunReporter):
    def blank_line(self) -> None:
        print()

    def account_banner(
        self, account: ResolvedAccount, *, index: int, total: int
    ) -> None:
        if total > 1:
            print(f"=== {account_label(account)} ===")
            print()

    def extract_settings(
        self,
        *,
        bank: str | None,
        subjects: list[str],
        from_filters: list[str],
        body_contains: list[str],
        download_dir: Path,
        start_date: date | None,
        end_date: date | None = None,
        extras: tuple[tuple[str, str], ...] = (),
    ) -> None:
        for line in format_run_settings_lines(
            bank=bank,
            subjects=subjects,
            from_filters=from_filters,
            body_contains=body_contains,
            download_dir=download_dir,
            start_date=start_date,
            end_date=end_date,
            extras=extras,
        ):
            print(line)

    def extract_search(self, candidate_count: int, folder: str) -> None:
        print(f"search: {candidate_count} candidate message(s) in {folder}")

    def extract_scanning_mbox(self, mbox_path: Path) -> None:
        print(f"scanning: {mbox_path}")

    def extract_mbox_progress(self, matched: int, saved: int) -> None:
        if matched:
            print(f"  {matched} message(s), {saved} attachment(s)")

    def extract_account_done(self, result: ExtractAccountResult) -> None:
        print()
        print(
            "done: "
            f"{result.messages_matched} message(s) matched, "
            f"{result.attachments_saved} attachment(s) saved to {result.download_dir}"
        )

    def cleanup_started(self, bank: str, download_dir: Path) -> None:
        print(f"cleanup: {bank} {download_dir}")
        print()

    def cleanup_skipped(self, bank: str, download_dir: Path) -> None:
        print(f"skip (not found): {download_dir}")

    def cleanup_done(self, result: CleanupAccountResult) -> None:
        if result.skipped:
            return
        print()
        rejected_hint = " (see warnings above)" if result.rejected else ""
        print(
            f"done: {result.non_pdf_removed} non-pdf removed, "
            f"{result.decrypted} decrypted, {result.prepared} prepared, "
            f"{result.rejected} rejected{rejected_hint}, "
            f"{result.orphans_removed} orphan(s) removed"
        )

    def metadata_started(self, bank: str, download_dir: Path) -> None:
        print(f"metadata: {bank} {download_dir}")
        print()

    def metadata_done(self, result: MetadataAccountResult) -> None:
        print()
        print(f"done: wrote {result.output} ({result.statement_count} statement(s))")

    def parse_started(self, bank: str, download_dir: Path) -> None:
        print(f"parse: {bank} {download_dir}")
        print()

    def parse_skipped(self, bank: str, download_dir: Path) -> None:
        print(f"skip (not found): {download_dir}")

    def parse_fy_started(self, fy_name: str) -> None:
        print(f"folder: {fy_name}")

    def parse_fy_skipped(self, fy_name: str) -> None:
        print(f"skip (no pdfs): {fy_name}")

    def parse_statement(self, txt_name: str, transaction_count: int) -> None:
        print(f"  {txt_name}: {transaction_count} transaction(s)")

    def parse_fy_done(self, result: ParseFyResult) -> None:
        if result.skipped or result.output is None:
            return
        print(
            f"wrote: {result.output} "
            f"({result.transaction_count} transaction(s) from "
            f"{len(result.statements)} txt(s))"
        )

    def parse_account_done(self, result: ParseAccountResult) -> None:
        if result.skipped:
            return
        print()
        print(
            f"done: {result.total_transactions} transaction(s) from "
            f"{result.total_txts} txt(s) in {len(result.fy_results)} folder(s)"
        )
