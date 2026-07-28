"""
Ingest metadata/*.json + matching fulltext OCR into PostgreSQL.

Usage:
    .venv/bin/python scripts/ingest.py
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from parser.normalize import normalize_metadata
from database.db import Database

TEXT_FOLDER = ROOT / "maha_grs 2" / "maha_grs" / "fulltext"
META_FOLDER = ROOT / "metadata"
ERROR_LOG = ROOT / "failed_ingest.txt"
COMMIT_EVERY = 100


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_row(meta: dict, ocr_text: str) -> dict:
    """Normalize JSON metadata and attach OCR text for DB insert."""

    # normalize_references expects list[dict]
    refs = meta.get("references") or []
    cleaned_refs = []
    for item in refs:
        if isinstance(item, str):
            cleaned_refs.append({"raw": item, "date": None})
        elif isinstance(item, dict):
            cleaned_refs.append(item)
    meta = {**meta, "references": cleaned_refs}

    # Prefer already-normalised GR number from extractor JSON
    if meta.get("gr_normalised") and not meta.get("gr_number_normalized"):
        meta["gr_number_normalized"] = meta["gr_normalised"]

    row = normalize_metadata(meta)

    # Keep original JSON department name (normalize does not set this)
    row["department"] = meta.get("department")

    # If normalize wiped normalised number, fall back to JSON field
    if not row.get("gr_number_normalized") and meta.get("gr_normalised"):
        row["gr_number_normalized"] = meta["gr_normalised"]

    row["filename"] = meta.get("filename")
    row["ocr_text"] = ocr_text
    row["references"] = row.get("references") or cleaned_refs

    return row


def main():

    if not META_FOLDER.exists():
        raise SystemExit(f"Missing metadata folder: {META_FOLDER}")

    files = sorted(META_FOLDER.glob("*.json"))
    print(f"Found {len(files)} metadata JSON files.")
    print(f"Fulltext dir: {TEXT_FOLDER}")

    db = Database()
    print(f"Connected. Existing rows: {db.count()}")

    ok = fail = missing_txt = 0

    if ERROR_LOG.exists():
        ERROR_LOG.unlink()

    for i, json_path in enumerate(tqdm(files, desc="Ingesting"), start=1):

        try:
            meta = load_json(json_path)
            filename = meta.get("filename") or json_path.name.replace(".json", ".txt")

            txt_path = TEXT_FOLDER / filename
            if not txt_path.exists():
                missing_txt += 1
                ocr_text = ""
            else:
                ocr_text = txt_path.read_text(encoding="utf-8", errors="ignore")

            row = prepare_row(meta, ocr_text)
            row["filename"] = filename

            db.insert_document(row, commit=False)

            ok += 1

            if i % COMMIT_EVERY == 0:
                db.commit()

        except Exception:
            fail += 1
            db.rollback()
            with open(ERROR_LOG, "a", encoding="utf-8") as f:
                f.write("=" * 70 + "\n")
                f.write(json_path.name + "\n")
                f.write(traceback.format_exc() + "\n")

    db.commit()
    total = db.count()
    db.close()

    print(
        f"Done. upserted={ok} fail={fail} missing_txt={missing_txt} "
        f"db_rows={total}"
    )
    if fail:
        print(f"See errors in {ERROR_LOG}")


if __name__ == "__main__":
    main()
