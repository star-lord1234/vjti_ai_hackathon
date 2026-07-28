import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from database.db import Database
from embeddings.embed_text import build_embedding_text

MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
)
DEFAULT_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))

_model: Optional[SentenceTransformer] = None


def get_model(model_name: Optional[str] = None) -> SentenceTransformer:
    """
    Module-level singleton loader for sentence-transformers embedding model.
    """
    global _model
    if _model is None:
        name = model_name or MODEL_NAME
        print(f"Loading embedding model: {name}...")
        _model = SentenceTransformer(name)
        print("Model loaded successfully.")
    return _model


def generate_embeddings(
    batch_size: Optional[int] = None,
    only_missing: bool = True,
    db: Optional[Database] = None,
) -> int:
    """
    Generate and update vector embeddings for gr_documents rows in PostgreSQL.

    Parameters
    ----------
    batch_size : int, optional
        Batch size for model encoding and DB updates (default from EMBEDDING_BATCH_SIZE or 32).
    only_missing : bool, default True
        If True, only generate embeddings for rows where embedding IS NULL (resumable).
    db : Database, optional
        Existing Database instance, or creates a new one if None.

    Returns
    -------
    int
        Total number of rows embedded and updated.
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

        with tqdm(total=total_rows, desc=desc) as pbar:
            for i in range(0, total_rows, batch_size):
                batch_rows = rows[i : i + batch_size]
                texts = [build_embedding_text(row) for row in batch_rows]
                embeddings = model.encode(
                    texts, show_progress_bar=False, normalize_embeddings=True
                )

                batch_updates = []
                for row, vec in zip(batch_rows, embeddings):
                    vec_list = (
                        vec.tolist() if hasattr(vec, "tolist") else list(vec)
                    )
                    vec_str = f"[{','.join(str(f) for f in vec_list)}]"
                    batch_updates.append((vec_str, row["id"]))

                database.update_embeddings_batch(batch_updates, commit=True)
                embedded_count += len(batch_rows)
                pbar.update(len(batch_rows))

        print(f"Successfully generated embeddings for {embedded_count} documents.")
        return embedded_count
    finally:
        if owns_db:
            database.close()


def main() -> None:
    generate_embeddings()


if __name__ == "__main__":
    main()
