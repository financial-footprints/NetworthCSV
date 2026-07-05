# NetworthCSV

Parse credit card and bank statement PDFs from email into CSV files. The pipeline extracts statement attachments from Thunderbird local mail or live IMAP, decrypts PDFs, extracts text, writes metadata, and writes `transactions.csv` per financial year folder.

## Setup

The application is not ready for usage yet.

## Configuration

NetworthCSV uses two JSON files:

| File               | Purpose                 |
| ------------------ | ----------------------- |
| `app.config.json`  | Bank defaults           |
| `user.config.json` | Secrets and local paths |

Create a config directory on your machine, then copy the sample files from the repository:

- [`user.config.sample.json`](https://github.com/financial-footprints/NetworthCSV/blob/main/user.config.sample.json) → `user.config.json`
- [`app.config.json`](https://github.com/financial-footprints/NetworthCSV/blob/main/app.config.json)

Edit `user.config.json` with your paths, passwords, and accounts. In `app.config.json`, set `user_config` to the path of your `user.config.json` (relative paths are resolved from the directory that contains `app.config.json`).

Point NetworthCSV at your `app.config.json`:

```bash
export NETWORTHCSV_CONFIG=/path/to/app.config.json
```

Or pass `--config /path/to/app.config.json` on the command line.

Each app-config variant may set an optional `type`: `credit_card` (default) or `bank_account`. Non-default variants inherit `type` from `default` when omitted. The resolved account carries this as metadata and determines the on-disk folder layout.

Each account needs a `bank`, an `account_number` (globally unique — shown in the UI and used for routing), and a `passwords` list.

**Email source** — set `source.type` in user config:

- `thunderbird` — reads locally cached mail from a Thunderbird profile. Close Thunderbird before running.
- `email` — read-only IMAP (Gmail, Outlook, etc.). For Gmail, use folder `[Gmail]/All Mail` and an [App Password](https://myaccount.google.com/apppasswords).

**Run scope** — optional `run` block in user config limits which account or FY folders a run processes:

```json
"run": {
  "identifier": "5678",
  "financial_year": "FY23-2024"
}
```

`identifier` matches the account's `account_number`. You can also pass `--identifier` / `-i` on the command line without editing config:

```bash
networthcsv --identifier 5678
```

**Alerts** — optional `alerts` block (`"console"` or `"email"`) for pipeline validation failures. See the sample config.

## Usage

Full pipeline (extract → cleanup → metadata → parse) for all configured accounts:

```bash
networthcsv
```

Full pipeline for one account with a local app config:

```bash
uv run networthcsv \
  --identifier '5298' \
  --config /path/to/app.config.json
```

Use the account's exact `account_number` from `user.config.json` as the identifier. Quote the value if it contains special characters.

Or run stages individually:

```bash
python -m networthcsv.pipeline.get_statements   # extract PDFs from email
python -m networthcsv.pipeline.cleanup          # decrypt PDFs, extract text
python -m networthcsv.pipeline.metadata         # write metadata.json
python -m networthcsv.pipeline.parse            # write transactions.csv
```

Delete cleanup, metadata, and parse outputs for a single account:

```bash
python -m networthcsv.pipeline.delete_statements --identifier 5678
```

Output layout:

```bash
{download_path}/FY23-2024/{account_type}/{account_number}/2024-01.pdf
{download_path}/FY23-2024/{account_type}/{account_number}/2024-01.txt
{download_path}/FY23-2024/{account_type}/{account_number}/transactions.csv
```

Example: `{download_path}/FY23-2024/credit_card/5678/2024-01.pdf`

## Development

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for setup, testing, and contribution guidelines.
