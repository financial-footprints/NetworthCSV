from networthcsv.cli import cli_main, load_context
from networthcsv.pipeline.reporter import ConsoleRunReporter
from networthcsv.runtime import process


def main() -> None:
    def _run() -> None:
        ctx = load_context(reporter=ConsoleRunReporter())
        _ = process(ctx)
        ctx.alerts.flush()

    cli_main(_run)


if __name__ == "__main__":
    main()
