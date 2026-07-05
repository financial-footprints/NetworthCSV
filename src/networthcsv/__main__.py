from networthcsv.cli import argv_requests_delete, cli_main, load_context, parse_run_args
from networthcsv.pipeline.reporter import ConsoleRunReporter
from networthcsv.runtime import process


def main() -> None:
    if argv_requests_delete():
        from networthcsv.pipeline.delete_statements.delete import main as delete_main

        delete_main()
        return

    def _run() -> None:
        cli_options = parse_run_args()
        ctx = load_context(
            config_path=cli_options.config_path,
            run_overrides=cli_options.run_overrides,
            reporter=ConsoleRunReporter(),
        )
        _ = process(ctx)
        ctx.alerts.flush()

    cli_main(_run)


if __name__ == "__main__":
    main()
