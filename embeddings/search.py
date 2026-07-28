import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from database.db import Database
from embeddings.embed import get_model


def semantic_search(
    query: str,
    top_k: int = 20,
    db: Optional[Database] = None,
) -> List[Dict[str, Any]]:
    """
    Perform semantic vector search against gr_documents in PostgreSQL.

    Parameters
    ----------
    query : str
        Natural language query string (e.g. Marathi legal text).
    top_k : int, default 20
        Number of top matches to return.
    db : Database, optional
        Existing Database instance, or creates a new one if None.

    Returns
    -------
    List[Dict[str, Any]]
        List of dicts containing: id, filename, gr_number_canonical,
        department, gr_date, subject_mr, score (1 - distance).
    """
    if not query or not query.strip():
        return []

    model = get_model()
    query_embedding = model.encode(
        query.strip(), show_progress_bar=False, normalize_embeddings=True
    )
    vec_list = (
        query_embedding.tolist()
        if hasattr(query_embedding, "tolist")
        else list(query_embedding)
    )
    vec_str = f"[{','.join(str(f) for f in vec_list)}]"

    owns_db = db is None
    database = db or Database()

    try:
        results = database.search_embeddings(vec_str, top_k=top_k)
        return results
    finally:
        if owns_db:
            database.close()


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "मुलींसाठी शिष्यवृत्ती"
    print(f"Executing semantic search for: '{query}'")
    results = semantic_search(query, top_k=20)

    print(f"\nTop {len(results)} results:\n" + "=" * 60)
    for idx, res in enumerate(results, 1):
        print(f"[{idx:02d}] Score: {res['score']:.4f}")
        print(f"     ID        : {res['id']}")
        print(f"     GR Number : {res['gr_number_canonical']}")
        print(f"     Dept      : {res['department']}")
        print(f"     Date      : {res['gr_date']}")
        print(f"     Subject   : {res['subject_mr']}")
        print(f"     File      : {res['filename']}")
        print("-" * 60)


if __name__ == "__main__":
    main()
