# CCParser — run commands

## Setup

```bash
pip install -e .
# edit user.config.json — source, paths, and passwords
```

Requires Python 3.11+. Each account must use a `passwords` array (legacy `password` field removed).

Set `source.type` to `thunderbird` (local Thunderbird cache) or `email` (live IMAP). See [README — Email sources](README.md#email-sources).

Close Thunderbird before running when using `source.type: thunderbird`.

## Config

| Method  | Example                                                                                       |
| ------- | --------------------------------------------------------------------------------------------- |
| Default | `app.config.json` (repo root)                                                                 |
| Env var | `export CCPARSER_CONFIG=/path/to/app.config.json`                                             |

There are no CLI flags. Account scope, FY limits, force re-extract, and combined CSV are set in the user config `run` block. See [README — Configuration](README.md#configuration).

Copy [`user.config.sample.json`](user.config.sample.json) to `user.config.json` and edit.

The app config points to the user/secrets file via `user_config` (default: `user.config.json`).

Production:

```bash
export CCPARSER_CONFIG=/invar/secret-manager/c05/financial-footprints/app.config.json
```

Production user config: `/invar/secret-manager/c05/financial-footprints/user.config.json`

---

## Full pipeline

```bash
ccparser
python -m src
```

---

## One stage only

```bash
python -m src.pipeline.get_statements
python -m src.pipeline.get_statements.thunderbird
python -m src.pipeline.cleanup
python -m src.pipeline.parse
```

Run `cleanup` before `parse`. `python -m src.pipeline.cleanup.text_extract` is an alias for cleanup.

---

## Limit to one account or FY

Edit `user.config.json`:

```json
"run": {
  "bank": "idfc",
  "variant": "wow",
  "fy": "FY23-2024",
  "force_text_extract": false,
  "create_combined_csv": false
}
```

Then run the stage command as usual (no extra CLI args).

---

## Tests

```bash
python -m unittest discover -s tests
```

---

## Outputs

| Stage   | Output                                                                                          |
| ------- | ----------------------------------------------------------------------------------------------- |
| Extract | `{download_path}/{bank}/*.pdf` or `{download_path}/{bank}/{variant}/*.pdf` (raw staging)        |
| Cleanup | paired `FY*/YYYY-MM.pdf` + `FY*/YYYY-MM.txt` as sibling files under the account folder         |
| Parse   | `FY*/transactions.csv` (+ optional `combined_transactions.csv` at account root)               |
