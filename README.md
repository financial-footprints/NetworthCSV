## CCParser

A tool to parse credit card statements from Thunderbird profile to CSV files.

### Configuration

The configuration is stored in the `extractor.config.json` file like:

```json
{
  "profile": "thunderbird/your-profile-name",
  "subject": "SUBJECT LINE",
  "download_path": "/home/your-username/Downloads/statements",
  "bank": "pnb"
}
```

Paths in `profile` and `download_path` may be relative to the script directory. Optional `mbox` limits scanning to a single mbox file instead of discovering folders in the profile.

`bank` selects the PDF parser. Options: `pnb`, `bob`, `idfc`

Statement PDFs are password-protected. [`src/config.py`](src/config.py) loads the shared password for cleanup and parsing (env wins over JSON):

```bash
export PDF_PASSWORD='your-password'
```

## Usage

Install dependencies from the repo root:

```bash
pip install -r requirements.txt
```

Full pipeline (extract attachments, clean PDFs, parse to CSV):

```bash
python -m src.main
```

Cleanup only (non-PDF removal, decrypt, dedupe, rename to `YYYY-MM.pdf`, then organize into India FY folders such as `FY23-2024/` for Apr 2023–Mar 2024; recursive, so existing PDFs anywhere under the download path are migrated too):

```bash
python -m src.cleanup
```

Parse only (all `FY*` folders under `download_path` → one `transactions.csv` per folder):

```bash
python -m src.parse
```

Optional: limit to a single FY folder:

```bash
python -m src.parse FY23-2024
```

CSV columns: `Date`, `Description`, `Ref`, `Credited`, `Debited`, `File`. `Ref` is populated for BoB rows that include a reference number (e.g. `R00935`); otherwise empty.

Extract only:

```bash
python -m src.extractor
```
