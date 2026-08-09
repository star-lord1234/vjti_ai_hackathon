import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from offline import configure_offline_mode

configure_offline_mode()

from sentence_transformers import SentenceTransformer

from tqdm import tqdm

from database.db import Database, VECTOR_DIM
from embeddings.embed_text import build_embedding_text, chunk_text

# Override via EMBEDDING_MODEL for domain-specific models (e.g. multilingual-e5-base).
MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
)
DEFAULT_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
CHUNK_SIZE = int(os.getenv("EMBEDDING_CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("EMBEDDING_CHUNK_OVERLAP", "150"))
EMBEDDING_LOCAL_FILES_ONLY = os.getenv("EMBEDDING_LOCAL_FILES_ONLY", "true").lower() in (
    "1",
    "true",
    "yes",
)

_model: Optional[SentenceTransformer] = None


def get_vector_dim() -> int:
    return VECTOR_DIM


def validate_embedding_dimension(model: SentenceTransformer) -> None:
    """Ensure model output dimension matches VECTOR_DIM / schema."""
    if hasattr(model, "get_embedding_dimension"):
        actual = model.get_embedding_dimension()
    else:
        actual = model.get_sentence_embedding_dimension()
    expected = get_vector_dim()
    if actual != expected:
        raise ValueError(
            f"Embedding model dimension ({actual}) does not match VECTOR_DIM ({expected}). "
            f"Set VECTOR_DIM={actual} in the environment or choose a compatible EMBEDDING_MODEL."
        )


def get_model(model_name: Optional[str] = None) -> SentenceTransformer:
    """
    Module-level singleton loader for sentence-transformers embedding model.
    """
    global _model
    if _model is None:
        name = model_name or MODEL_NAME
        device = os.getenv("EMBEDDING_DEVICE", "cpu")
        print(f"Loading embedding model: {name} (device={device})...")
        try:
            _model = SentenceTransformer(
                name,
                device=device,
                local_files_only=EMBEDDING_LOCAL_FILES_ONLY,
            )
        except Exception as exc:
            if EMBEDDING_LOCAL_FILES_ONLY:
                raise RuntimeError(
                    f"Could not load embedding model offline ({name}). "
                    "While online, run once: cd backend && python -m embeddings.embed "
                    "Or set EMBEDDING_LOCAL_FILES_ONLY=false when you have network access."
                ) from exc
            raise
        validate_embedding_dimension(_model)
        print(f"Model loaded successfully (dim={get_vector_dim()}).")
    return _model



def _vector_to_str(vec) -> str:
    vec_list = vec.tolist() if hasattr(vec, "tolist") else list(vec)
    return f"[{','.join(str(f) for f in vec_list)}]"


def _build_chunk_embed_texts(row: dict) -> List[Tuple[str, str]]:
    """
    Build (stored_chunk_text, text_to_embed) pairs for a document row.
    Prefixes each chunk with subject/department/GR number for better retrieval.
    """
    prefix_parts = []
    for key in ("subject_mr", "department", "gr_number_canonical"):
        val = row.get(key)
        if val and str(val).strip():
            prefix_parts.append(str(val).strip())
    prefix = "\n".join(prefix_parts)

    ocr_text = (row.get("ocr_text") or "").strip()
    if ocr_text:
        raw_chunks = chunk_text(ocr_text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
    else:
        raw_chunks = []

    if not raw_chunks:
        meta_text = build_embedding_text(row)
        return [(meta_text, meta_text)]

    pairs: List[Tuple[str, str]] = []
    for chunk in raw_chunks:
        embed_text = f"{prefix}\n{chunk}" if prefix else chunk
        pairs.append((chunk, embed_text))
    return pairs


def generate_embeddings(
    batch_size: Optional[int] = None,
    only_missing: bool = True,
    db: Optional[Database] = None,
) -> int:
    """
    Generate document-level and chunk-level vector embeddings for gr_documents rows.

    For each document:
    - One document-level embedding (metadata + up to EMBEDDING_MAX_OCR_CHARS of OCR)
    - Multiple chunk embeddings in gr_chunks for clause-level retrieval
    """
    if batch_size is None:
        batch_size = DEFAULT_BATCH_SIZE

    owns_db = db is None
    database = db or Database()

    try:
        model = get_model()
        rows = database.get_documents_for_embedding(only_missing=only_missing)
        total_rows = len(rows)

        if total_rows == 0:
            print("No documents found for embedding (all up to date).")
            return 0

        desc = "Generating embeddings" if only_missing else "Rebuilding embeddings"
        embedded_count = 0
        chunk_count = 0

        with tqdm(total=total_rows, desc=desc) as pbar:
            for i in range(0, total_rows, batch_size):
                batch_rows = rows[i : i + batch_size]

                # Document-level embeddings
                doc_texts = [build_embedding_text(row) for row in batch_rows]
                doc_embeddings = model.encode(
                    doc_texts, show_progress_bar=False, normalize_embeddings=True
                )

                doc_updates = []
                for row, vec in zip(batch_rows, doc_embeddings):
                    doc_updates.append((_vector_to_str(vec), row["id"]))

                database.update_embeddings_batch(doc_updates, commit=False)

                # Chunk-level embeddings (replace stale chunks per document)
                for row in batch_rows:
                    doc_id = row["id"]
                    database.delete_chunks_for_document(doc_id, commit=False)

                    chunk_pairs = _build_chunk_embed_texts(row)
                    if not chunk_pairs:
                        continue

                    stored_texts, embed_texts = zip(*chunk_pairs)
                    chunk_embeddings = model.encode(
                        list(embed_texts),
                        show_progress_bar=False,
                        normalize_embeddings=True,
                    )

                    chunk_batch = []
                    for idx, (stored, vec) in enumerate(
                        zip(stored_texts, chunk_embeddings)
                    ):
                        chunk_batch.append(
                            (doc_id, idx, stored, _vector_to_str(vec))
                        )

                    if chunk_batch:
                        database.insert_chunks_batch(chunk_batch, commit=False)
                        chunk_count += len(chunk_batch)

                database.commit()
                embedded_count += len(batch_rows)
                pbar.update(len(batch_rows))

        print(
            f"Successfully generated embeddings for {embedded_count} documents "
            f"({chunk_count} chunks)."
        )
        return embedded_count
    finally:
        if owns_db:
            database.close()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Generate GR document + chunk embeddings")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Re-embed all documents (not only missing/stale)",
    )
    args = parser.parse_args()
    generate_embeddings(only_missing=not args.rebuild)


if __name__ == "__main__":
    main()
