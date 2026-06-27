# NetworthCSV

Parse credit card and bank statement PDFs from email into CSV files. The pipeline extracts statement attachments from Thunderbird local mail or live IMAP, decrypts PDFs, extracts text, and writes `transactions.csv` per financial year folder.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
cd NetworthCSV
make install
```

## Configuration

NetworthCSV uses two JSON files:

| File               | Purpose                 |
| ------------------ | ----------------------- |
| `app.config.json`  | Bank defaults.          |
| `user.config.json` | Secrets and local paths |

Copy [`user.config.sample.json`](user.config.sample.json) to `user.config.json` and edit paths, passwords, and accounts. Supported banks and product variants are defined in [`app.config.json`](app.config.json).

Each app-config variant may set an optional `type`: `credit_card` (default) or `bank_account`. Non-default variants inherit `type` from `default` when omitted. The resolved account carries this as metadata and determines the on-disk folder layout.

Each account needs a `bank`, an `account_number` (globally unique — shown in the UI and used for routing), and a `passwords` list.

**Email source** — set `source.type` in user config:

- `thunderbird` — reads locally cached mail from a Thunderbird profile. Close Thunderbird before running.
- `email` — read-only IMAP (Gmail, Outlook, etc.). For Gmail, use folder `[Gmail]/All Mail` and an [App Password](https://myaccount.google.com/apppasswords).

**Run scope** — optional `run` block in user config limits which accounts or FY folders a run processes:

```json
"run": {
  "bank": "hdfc",
  "variant": "swiggy",
  "financial_year": "FY23-2024"
}
```

**Alerts** — optional `alerts` block (`"console"` or `"email"`) for pipeline validation failures. See the sample config.

Config path: repo-root `app.config.json` by default, or set `NETWORTHCSV_CONFIG` to override.

## Usage

Full pipeline (extract → cleanup → parse) for all configured accounts:

```bash
make dev
```

Or run stages individually:

```bash
python -m networthcsv.pipeline.get_statements   # extract PDFs from email
python -m networthcsv.pipeline.cleanup          # decrypt PDFs, extract text
python -m networthcsv.pipeline.metadata         # write metadata.json
python -m networthcsv.pipeline.parse            # write transactions.csv
```

Output layout:

```bash
{download_path}/FY23-2024/{account_type}/{account_number}/2024-01.pdf
{download_path}/FY23-2024/{account_type}/{account_number}/2024-01.txt
{download_path}/FY23-2024/{account_type}/{account_number}/transactions.csv
```

Example: `{download_path}/FY23-2024/credit_card/5678/2024-01.pdf`

## Development

The repo includes a `Makefile` that wraps common tasks. Run `make help` for a short list.

| Command        | Description                                                                                  |
| -------------- | -------------------------------------------------------------------------------------------- |
| `make help`    | Print available targets.                                                                     |
| `make install` | Create the venv, run `uv lock`, and `uv sync --group dev`.                                   |
| `make dev`     | Run the full pipeline (`uv run python -m networthcsv`).                                      |
| `make upgrade` | Upgrade locked dependencies and sync the dev group.                                          |
| `make test`    | Run unit tests (`uv run python -m unittest discover -s tests`).                              |
| `make lint`    | Type-check with [basedpyright](https://docs.basedpyright.com/) (config in `pyproject.toml`). |
| `make format`  | Format `src/` and `tests/` with [ruff](https://docs.astral.sh/ruff/).                        |
| `make cleanup` | Remove build artifacts, `__pycache__`, `.pyc` files, egg-info dirs, and `.ruff_cache`.       |
