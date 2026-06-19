# CCParser — run commands

## Setup

```bash
pip install -e .
# edit user.config.json — paths and passwords
```

Requires Python 3.11+. Each account must use a `passwords` array (legacy `password` field removed).

Close Thunderbird before running against a live profile.

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
python -m src.pipeline.thunderbird
python -m src.pipeline.cleanup
python -m src.pipeline.text_extract
python -m src.pipeline.parse
```

Run `text_extract` before `parse`.

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

| Stage        | Output                                                                                 |
| ------------ | -------------------------------------------------------------------------------------- |
| Extract      | `{download_path}/{bank}/*.pdf` or `{download_path}/{bank}/{variant}/*.pdf` (raw)       |
| Cleanup      | `{download_path}/{bank}/FY*/YYYY-MM.pdf` or `{download_path}/{bank}/{variant}/FY*/...` |
| Text extract | `.../txt/FY*/YYYY-MM.txt` under the same account folder                                |
| Parse        | `.../FY*/transactions.csv` (+ optional `combined_transactions.csv`)                    |
