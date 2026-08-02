"""
Ingest metadata/*.json + matching fulltext OCR into PostgreSQL.

Usage:
    .venv/bin/python scripts/ingest.py

Environment:
    GR_FULLTEXT_DIR   — override OCR fulltext directory
    GR_METADATA_DIR   — override metadata JSON directory
    INGEST_SYNC_NEO4J — sync Neo4j graph after ingest (true/false)
    STRICT_INGEST_VALIDATION — exit 1 if post-ingest checks fail
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from parser.normalize import normalize_metadata
from parser.paths import resolve_metadata_folder, resolve_text_folder
from database.db import Database
from scripts.ingest_validation import run_post_ingest_validation

TEXT_FOLDER = resolve_text_folder(ROOT)
META_FOLDER = resolve_metadata_folder(ROOT)
ERROR_LOG = ROOT / "failed_ingest.txt"
COMMIT_EVERY = 100
SYNC_NEO4J = os.getenv("INGEST_SYNC_NEO4J", "false").lower() in ("1", "true", "yes")
RUN_EMBED_AFTER = os.getenv("INGEST_RUN_EMBED", "false").lower() in ("1", "true", "yes")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_row(meta: dict, ocr_text: str) -> dict:
    """Normalize JSON metadata and attach OCR text for DB insert."""

    refs = meta.get("references") or []
    cleaned_refs = []
    for item in refs:
        if isinstance(item, str):
            cleaned_refs.append({"raw": item, "date": None})
        elif isinstance(item, dict):
            cleaned_refs.append(item)
    meta = {**meta, "references": cleaned_refs}

    if meta.get("gr_normalised") and not meta.get("gr_number_normalized"):
        meta["gr_number_normalized"] = meta["gr_normalised"]

    row = normalize_metadata(meta)

    row["department"] = meta.get("department")

    if not row.get("gr_number_normalized") and meta.get("gr_normalised"):
        row["gr_number_normalized"] = meta["gr_normalised"]

    # Recompute canonical if normalize left it empty but we have a normalized number
    if not row.get("gr_number_canonical") and row.get("gr_number_normalized"):
        from parser.normalize import canonical_gr_number
        row["gr_number_canonical"] = canonical_gr_number(row["gr_number_normalized"])

    row["filename"] = meta.get("filename")
    row["ocr_text"] = ocr_text
    row["references"] = row.get("references") or cleaned_refs

    return row


def main():

    if not META_FOLDER.exists():
        raise SystemExit(f"Missing metadata folder: {META_FOLDER}")

    if not TEXT_FOLDER.exists():
        print(f"Warning: fulltext folder does not exist: {TEXT_FOLDER}")
        print("Set GR_FULLTEXT_DIR or place files under backend/maha_grs/fulltext")

    files = sorted(META_FOLDER.glob("*.json"))
    print(f"Found {len(files)} metadata JSON files.")
    print(f"Metadata dir : {META_FOLDER}")
    print(f"Fulltext dir : {TEXT_FOLDER}")

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

    print(
        f"Done. upserted={ok} fail={fail} missing_txt={missing_txt} "
        f"db_rows={total}"
    )
    if fail:
        print(f"See errors in {ERROR_LOG}")

    if RUN_EMBED_AFTER and ok > 0:
        print("\nINGEST_RUN_EMBED=true — generating embeddings...")
        try:
            from embeddings.embed import generate_embeddings

            generate_embeddings(only_missing=True, db=db)
        except Exception as e:
            print(f"Warning: embedding generation failed ({e}).")

    if SYNC_NEO4J and ok > 0:
        print("\nINGEST_SYNC_NEO4J=true — syncing citation graph to Neo4j...")
        try:
            from graph.neo4j_loader import Neo4jLoader

            loader = Neo4jLoader(db=db)
            loader.load_graph(clear=False)
            loader.close()
            print("Neo4j graph sync complete.")
        except Exception as e:
            print(f"Warning: Neo4j sync failed ({e}). Run graph.neo4j_loader manually.")

    run_post_ingest_validation(db=db)
    db.close()


if __name__ == "__main__":
    main()
