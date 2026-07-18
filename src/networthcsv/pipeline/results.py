"""Structured results returned by pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExtractAccountResult:
    bank: str
    download_dir: Path
    messages_matched: int
    attachments_saved: int


@dataclass(frozen=True)
class ExtractStageResult:
    accounts: tuple[ExtractAccountResult, ...]


@dataclass(frozen=True)
class CleanupAccountResult:
    bank: str
    download_dir: Path
    unsupported_staging_removed: int
    decrypted: int
    prepared: int
    rejected: int
    orphans_removed: int
    skipped: bool = False


@dataclass(frozen=True)
class MetadataAccountResult:
    bank: str
    download_dir: Path
    output: Path
    statement_count: int


@dataclass(frozen=True)
class DeleteAccountResult:
    bank: str
    download_dir: Path
    files_removed: int
    dirs_removed: int
    metadata_path: Path


@dataclass(frozen=True)
class ParseStatementResult:
    txt_name: str
    transaction_count: int


@dataclass(frozen=True)
class ParseFyResult:
    fy_name: str
    statements: tuple[ParseStatementResult, ...]
    transaction_count: int
    outputs: tuple[Path, ...] = ()
    skipped: bool = False

    @property
    def output(self) -> Path | None:
        """First output path, if any (compat for single-file callers)."""
        return self.outputs[0] if self.outputs else None


@dataclass(frozen=True)
class ParseAccountResult:
    bank: str
    download_dir: Path
    fy_results: tuple[ParseFyResult, ...]
    total_transactions: int
    total_txts: int
    skipped: bool = False


@dataclass(frozen=True)
class PipelineResult:
    extract: ExtractStageResult
    cleanup: tuple[CleanupAccountResult, ...]
    metadata: tuple[MetadataAccountResult, ...]
    parse: tuple[ParseAccountResult, ...]
