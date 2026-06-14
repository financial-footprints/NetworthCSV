# CCParser — run commands

## Setup

```bash
pip install -e .
cp extractor.config.sample.json extractor.config.json   # edit paths/passwords
```

Requires Python 3.12+. Each account must use a `passwords` array (legacy `password` field removed).

Close Thunderbird before running against a live profile.

## Config (pick one)

| Method  | Example                                                 |
| ------- | ------------------------------------------------------- |
| Default | `extractor.config.json` (repo root)                     |
| Env var | `export CCPARSER_CONFIG=/path/to/extractor.config.json` |
| Flag    | `-c /path/to/extractor.config.json`                     |

Production: `/invar/secret-manager/c05/financial-footprints/extractor.config.json`

All commands accept `-c PATH`.

---

## Full pipeline (all accounts)

```bash
ccparser
python -m src
python -m src -c /path/to/extractor.config.json
```

---

## One stage only (all accounts)

```bash
python -m src.pipeline.thunderbird      # extract PDFs from mbox
python -m src.pipeline.cleanup          # decrypt, dedupe, rename, FY folders
python -m src.pipeline.text_extract     # PDF → txt/
python -m src.pipeline.parse            # txt → transactions.csv
```

Run `text_extract` before `parse`.

---

## Single account

Replace `idfc` with your bank folder (`pnb`, `bob`, `idfc`).

```bash
python -m src.pipeline.cleanup      /path/to/statements/idfc
python -m src.pipeline.text_extract /path/to/statements/idfc
python -m src.pipeline.parse --account /path/to/statements/idfc
```

With custom config:

```bash
python -m src.pipeline.cleanup -c /path/to/extractor.config.json /path/to/statements/idfc
```

---

## Parse: limit to one FY folder

```bash
python -m src.pipeline.parse --fy FY23-2024
python -m src.pipeline.parse --account /path/to/statements/idfc --fy FY23-2024
```

---

## Tests

```bash
python -m unittest discover -s tests
```

---

## Outputs

| Stage        | Output                                                                                 |
| ------------ | -------------------------------------------------------------------------------------- |
| Extract      | `{download_path}/{bank}/*.pdf` (raw)                                                   |
| Cleanup      | `{download_path}/{bank}/FY*/YYYY-MM.pdf`                                               |
| Text extract | `{download_path}/{bank}/txt/FY*/YYYY-MM.txt`                                           |
| Parse        | `{download_path}/{bank}/FY*/transactions.csv` (+ optional `combined_transactions.csv`) |
