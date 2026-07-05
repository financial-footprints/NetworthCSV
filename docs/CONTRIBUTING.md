# Contributing

**Developers:** this guide covers local setup, testing, and contribution workflow for NetworthCSV. End-user setup, configuration, and usage are in [README.md](../README.md).

For workspace-wide setup (clone layout, shared scripts), see the [Financial Footprints contributing guide](https://github.com/financial-footprints/.github/blob/main/docs/CONTRIBUTING.md).

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- [make](https://www.gnu.org/software/make/)

## Getting Started

```bash
cd NetworthCSV
make install
```

This creates the virtual environment, locks dependencies, and installs dev tools (basedpyright, ruff).

## Development Workflow

Run the full pipeline for all configured accounts:

```bash
make dev
```

Limit to a single account without editing config:

```bash
make dev IDENTIFIER=5678
```

Pipeline stages live under `src/networthcsv/pipeline/` and can be run individually:

```bash
python -m networthcsv.pipeline.get_statements
python -m networthcsv.pipeline.cleanup
python -m networthcsv.pipeline.metadata
python -m networthcsv.pipeline.parse
```

## Project Layout

| Path                        | Purpose                              |
| --------------------------- | ------------------------------------ |
| `src/networthcsv/`          | Application source                   |
| `src/networthcsv/pipeline/` | Pipeline stage modules               |
| `tests/`                    | Unit tests                           |
| `pyproject.toml`            | Dependencies and basedpyright config |
| `.editorconfig`             | Editor formatting rules              |

## Makefile Reference

Run `make help` for a short list.

| Command        | Description                                                                                 |
| -------------- | ------------------------------------------------------------------------------------------- |
| `make help`    | Print available targets                                                                     |
| `make install` | Create the venv, run `uv lock`, and `uv sync --group dev`                                   |
| `make dev`     | Run the full pipeline (`uv run python -m networthcsv`)                                      |
| `make upgrade` | Upgrade locked dependencies and sync the dev group                                          |
| `make test`    | Run unit tests (`uv run python -m unittest discover -s tests`)                              |
| `make lint`    | Type-check with [basedpyright](https://docs.basedpyright.com/) (config in `pyproject.toml`) |
| `make format`  | Format `src/` and `tests/` with [ruff](https://docs.astral.sh/ruff/)                        |
| `make ci`      | Run format, lint, then test                                                                 |
| `make clean`   | Remove build artifacts, `__pycache__`, `.pyc` files, egg-info dirs, and `.ruff_cache`       |

## Before Submitting

Run the full CI target locally:

```bash
make ci
```

If you use the shared workspace scripts, you can also run from the workspace root:

```bash
./scripts/ci.sh csv
```

## Cross-Repo Note

[NetworthSync](https://github.com/financial-footprints/NetworthSync) depends on this package. When changing public behavior, verify the sibling NetworthSync checkout still works with your changes.

## Commit Messages

This project follows the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification. Read the spec for format, types, and breaking-change notation.
