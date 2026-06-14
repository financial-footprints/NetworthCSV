from pathlib import Path

from src.cli import parse_args_with_config
from src.core.accounts import iter_accounts
from src.logging_config import configure_logging
from src.pipeline.cleanup import run as cleanup_run
from src.pipeline.parse import run as parse_run
from src.pipeline.text_extract import run as text_extract_run
from src.pipeline.thunderbird import run_account as thunderbird_run_account
from src.settings import AccountSettings, Settings, account_download_path, load_settings, parser_bank


def main() -> None:
    configure_logging()
    config_path, _ = parse_args_with_config("Run the full CCParser pipeline.")
    settings = load_settings(config_path)

    def run_pipeline(_download_dir: Path, account: AccountSettings, settings: Settings) -> None:
        account_dir = account_download_path(settings, account)
        thunderbird_run_account(settings, account)
        print()
        cleanup_run(account_dir, account.passwords, bank=account.bank)
        print()
        text_extract_run(account_dir, account.passwords, bank=account.bank)
        print()
        parse_run(
            account_dir,
            parser_bank(account),
            settings.create_combined_csv,
        )

    iter_accounts(settings, run_pipeline)


if __name__ == "__main__":
    main()
