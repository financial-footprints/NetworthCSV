from pathlib import Path

from src.cli import load_context
from src.core.accounts import iter_accounts
from src.pipeline.cleanup import run as cleanup_run
from src.pipeline.parse import run as parse_run
from src.core.paths import resolve_fy_limit
from src.pipeline.text_extract import run as text_extract_run
from src.pipeline.thunderbird import run_account as thunderbird_run_account
from src.settings import ResolvedAccount, account_download_path


def main() -> None:
    ctx = load_context()

    def run_pipeline(_download_dir: Path, account: ResolvedAccount, _settings: object) -> None:
        account_dir = account_download_path(ctx.settings, account)
        thunderbird_run_account(ctx, account)
        print()
        cleanup_run(account_dir, account)
        print()
        text_extract_run(account_dir, account, ctx)
        print()
        fy_limit = resolve_fy_limit(account_dir, ctx.settings.run.fy)
        parse_run(account_dir, account, ctx, fy_limit=fy_limit)

    iter_accounts(ctx.settings, run_pipeline)
    ctx.alerts.flush()


if __name__ == "__main__":
    main()
