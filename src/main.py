from pathlib import Path

from src.cli import load_context
from src.utils.accounts import iter_accounts
from src.pipeline.cleanup.cleanup import run as cleanup_run
from src.pipeline.get_statements.extract import run_all as extract_run_all
from src.pipeline.parse.parse import run as parse_run
from src.utils.paths import resolve_fy_limit
from src.settings import ResolvedAccount, account_download_path


def main() -> None:
    ctx = load_context()
    extract_run_all(ctx)
    print()

    def run_pipeline(_download_dir: Path, account: ResolvedAccount, _settings: object) -> None:
        account_dir = account_download_path(ctx.settings, account)
        cleanup_run(account_dir, account, ctx)
        print()
        fy_limit = resolve_fy_limit(account_dir, ctx.settings.run.fy)
        parse_run(account_dir, account, ctx, fy_limit=fy_limit)

    iter_accounts(ctx.settings, run_pipeline)
    ctx.alerts.flush()


if __name__ == "__main__":
    main()
