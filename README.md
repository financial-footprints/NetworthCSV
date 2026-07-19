# NetworthCSV

Parse credit card and bank statement PDFs from email into CSV files. The pipeline extracts statement attachments from Thunderbird local mail or live IMAP, decrypts PDFs, extracts text, writes metadata, and writes per-period `transactions-YYYY-MM.csv` / `transactions-YYYY.csv` files.

## Setup

The application is not ready for usage yet.

## Configuration

NetworthCSV uses two files:

| File            | Purpose                                              |
| --------------- | ---------------------------------------------------- |
| `.env`          | Paths, email source, download directory, log level, alerts |
| `accounts.json` | Bank accounts (passwords, opening dates, matchers)   |

Copy the sample files from the repository:

- [`.env.example`](.env.example) → `.env`
- [`accounts.example.json`](accounts.example.json) → `accounts.json`

Edit `.env` with your download path, email/Thunderbird source, and optional alert settings. Edit `accounts.json` with your account entries.

Point NetworthCSV at your accounts file via `.env`:

```bash
ACCOUNT_CONFIG_PATH=./accounts.json
```

Or pass `--config /path/to/accounts.json` on the command line.

**Env file chaining** — by default NetworthCSV loads `<repo>/.env`. To start elsewhere, export `ENV_NETWORTHCSV=/path/to/.env`. To chain additional files, set `ENV_PATH=/path/to/other.env` inside an env file (up to 10 hops). Chained files merge additively: later files override only the keys they define.

Each account needs a `bank`, an `account_number` (globally unique — shown in the UI and used for routing), and a `passwords` list.

**IMAP source** — set `SOURCE_TYPE=email` in `.env`:

- `IMAP_HOST`, `IMAP_USERNAME`, `IMAP_PASSWORD`, etc.
- For Gmail, use `IMAP_FOLDER=[Gmail]/All Mail` and an [App Password](https://myaccount.google.com/apppasswords).

**Thunderbird source** — set `SOURCE_TYPE=thunderbird` and `THUNDERBIRD_PROFILE` in `.env`. Close Thunderbird before running.

**Run scope** — limit which account a run processes via CLI (`--identifier`) or NetworthSync.

```bash
networthcsv --identifier 5678
```

`identifier` matches the account's `account_number`. Quote the value if it contains special characters.

**Alerts** — set `ALERTS_TYPE=console` or `ALERTS_TYPE=email` in `.env` (with `SMTP_*` vars for email notifications). See `.env.example`.

## Usage

Full pipeline (extract → cleanup → metadata → parse) for all configured accounts:

```bash
networthcsv
```

Full pipeline for one account with a custom accounts file:

```bash
uv run networthcsv \
  --identifier '3841' \
  --config /path/to/accounts.json
```

Use the account's exact `account_number` from `accounts.json` as the identifier.

Or run stages individually:

```bash
python -m networthcsv.pipeline.get_statements   # extract PDFs from email
python -m networthcsv.pipeline.cleanup          # decrypt PDFs, extract text
python -m networthcsv.pipeline.metadata         # write metadata.json
python -m networthcsv.pipeline.parse            # write transactions-*.csv
```

Delete cleanup, metadata, and parse outputs for a single account:

```bash
python -m networthcsv.pipeline.delete_statements --identifier 5678
```

Output layout:

```bash
{download_path}/FY23-2024/{account_type}/{account_number}/2024-01.pdf
{download_path}/FY23-2024/{account_type}/{account_number}/2024-01.txt
{download_path}/FY23-2024/{account_type}/{account_number}/2024-01.csv
{download_path}/FY23-2024/{account_type}/{account_number}/transactions-2024-01.csv
{download_path}/FY23-2024/{account_type}/{account_number}/2024.pdf
{download_path}/FY23-2024/{account_type}/{account_number}/transactions-2024.csv
```

Unprocessed period files use `YYYY-MM.*` (monthly) or `YYYY.*` (annual). Parse adds `transactions-` prefixed CSVs and never removes the unprocessed originals.

## Development

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for setup, testing, and contribution guidelines.
