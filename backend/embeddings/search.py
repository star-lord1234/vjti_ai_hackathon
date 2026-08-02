import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from database.db import Database
from embeddings.embed import get_model

DEFAULT_MIN_SCORE = float(os.getenv("SEMANTIC_MIN_SCORE", "0.35"))
DEFAULT_DRAFT_SEGMENT_CHARS = int(os.getenv("DRAFT_QUERY_SEGMENT_CHARS", "600"))
DEFAULT_MAX_DRAFT_SEGMENTS = int(os.getenv("DRAFT_QUERY_MAX_SEGMENTS", "5"))


def get_min_score() -> float:
    return float(os.getenv("SEMANTIC_MIN_SCORE", str(DEFAULT_MIN_SCORE)))


def encode_query(text: str) -> str:
    """Encode a query string to a pgvector literal."""
    model = get_model()
    query_embedding = model.encode(
        text.strip(), show_progress_bar=False, normalize_embeddings=True
    )
    vec_list = (
        query_embedding.tolist()
        if hasattr(query_embedding, "tolist")
        else list(query_embedding)
    )
    return f"[{','.join(str(f) for f in vec_list)}]"


def _dedupe_chunks_to_documents(
    chunk_results: List[Dict[str, Any]], top_k: int
) -> List[Dict[str, Any]]:
    """Collapse chunk hits to one entry per document (best score wins)."""
    by_id: Dict[int, Dict[str, Any]] = {}
    for row in chunk_results:
        doc_id = row["id"]
        existing = by_id.get(doc_id)
        if existing is None or row["score"] > existing["score"]:
            entry = {
                k: v
                for k, v in row.items()
                if k not in ("chunk_index", "chunk_text")
            }
            entry["matched_chunk_index"] = row.get("chunk_index")
            entry["matched_chunk_text"] = row.get("chunk_text")
            by_id[doc_id] = entry
    return sorted(by_id.values(), key=lambda r: -(r.get("score") or 0.0))[:top_k]


def _merge_document_results(
    result_lists: List[List[Dict[str, Any]]], top_k: int
) -> List[Dict[str, Any]]:
    """Merge multiple search result lists, keeping best score per document."""
    by_id: Dict[int, Dict[str, Any]] = {}
    for results in result_lists:
        for row in results:
            doc_id = row["id"]
            existing = by_id.get(doc_id)
            if existing is None or (row.get("score") or 0) > (existing.get("score") or 0):
                by_id[doc_id] = row
    return sorted(by_id.values(), key=lambda r: -(r.get("score") or 0.0))[:top_k]


def build_draft_query_segments(
    draft_text: str,
    max_segments: int = DEFAULT_MAX_DRAFT_SEGMENTS,
    segment_chars: int = DEFAULT_DRAFT_SEGMENT_CHARS,
) -> List[str]:
    """
    Split a draft GR into multiple query segments for multi-vector retrieval.
    Skips short header boilerplate and always includes a tail segment.
    """
    text = draft_text.strip()
    if not text:
        return []
    if len(text) <= segment_chars:
        return [text]

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]

    # Skip short header-only paragraphs at the start (department lines, etc.)
    start_idx = 0
    for i, para in enumerate(paragraphs[:4]):
        if len(para) < 100 and not re.search(r"\d", para):
            start_idx = i + 1
        else:
            break

    segments: List[str] = []
    current: List[str] = []
    current_len = 0

    for para in paragraphs[start_idx:]:
        if len(para) >= segment_chars:
            if current:
                segments.append("\n\n".join(current))
                current = []
                current_len = 0
            step = max(segment_chars - 100, 1)
            for start in range(0, len(para), step):
                seg = para[start : start + segment_chars].strip()
                if len(seg) >= 80:
                    segments.append(seg)
        elif current_len + len(para) + 2 > segment_chars and current:
            segments.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += len(para) + 2

    if current:
        segments.append("\n\n".join(current))

    tail = text[-segment_chars:].strip()
    if tail:
        segments.append(tail)

    # Deduplicate near-identical segments, preserve order
    seen: set[str] = set()
    unique: List[str] = []
    for seg in segments:
        key = seg[:120]
        if key not in seen:
            seen.add(key)
            unique.append(seg)

    return unique[:max_segments]


def semantic_search(
    query: str,
    top_k: int = 20,
    min_score: Optional[float] = None,
    db: Optional[Database] = None,
    prefer_chunks: bool = True,
) -> List[Dict[str, Any]]:
    """
    Semantic vector search against gr_chunks (preferred) with document-level fallback.

    Parameters
    ----------
    query : str
        Natural language query string (e.g. Marathi legal text).
    top_k : int
        Number of top document matches to return.
    min_score : float, optional
        Minimum cosine similarity (0–1). Defaults to SEMANTIC_MIN_SCORE env (0.35).
    prefer_chunks : bool
        Search clause-level chunk embeddings first; fall back to document vectors.
    """
    if not query or not query.strip():
        return []

    if min_score is None:
        min_score = get_min_score()

    vec_str = encode_query(query)

    owns_db = db is None
    database = db or Database()

    try:
        if prefer_chunks:
            chunk_hits = database.search_chunks(
                vec_str, top_k=top_k, min_score=min_score
            )
            if chunk_hits:
                return _dedupe_chunks_to_documents(chunk_hits, top_k)

        return database.search_embeddings(
            vec_str, top_k=top_k, min_score=min_score
        )
    finally:
        if owns_db:
            database.close()


def semantic_search_multi(
    queries: Union[str, List[str]],
    top_k: int = 20,
    min_score: Optional[float] = None,
    db: Optional[Database] = None,
    prefer_chunks: bool = True,
) -> List[Dict[str, Any]]:
    """
    Run semantic search over multiple query segments and merge by best document score.
    """
    if isinstance(queries, str):
        return semantic_search(
            queries,
            top_k=top_k,
            min_score=min_score,
            db=db,
            prefer_chunks=prefer_chunks,
        )

    clean = [q.strip() for q in queries if q and q.strip()]
    if not clean:
        return []
    if len(clean) == 1:
        return semantic_search(
            clean[0],
            top_k=top_k,
            min_score=min_score,
            db=db,
            prefer_chunks=prefer_chunks,
        )

    per_query_k = max(top_k // len(clean), 5)
    owns_db = db is None
    database = db or Database()

    try:
        all_results: List[List[Dict[str, Any]]] = []
        for q in clean:
            all_results.append(
                semantic_search(
                    q,
                    top_k=per_query_k,
                    min_score=min_score,
                    db=database,
                    prefer_chunks=prefer_chunks,
                )
            )
        return _merge_document_results(all_results, top_k)
    finally:
        if owns_db:
            database.close()


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "मुलींसाठी शिष्यवृत्ती"
    print(f"Executing semantic search for: '{query}'")
    print(f"Min score threshold: {get_min_score()}")
    results = semantic_search(query, top_k=20)

    print(f"\nTop {len(results)} results:\n" + "=" * 60)
    for idx, res in enumerate(results, 1):
        print(f"[{idx:02d}] Score: {res['score']:.4f}")
        print(f"     ID        : {res['id']}")
        print(f"     GR Number : {res['gr_number_canonical']}")
        print(f"     Dept      : {res['department']}")
        print(f"     Date      : {res['gr_date']}")
        print(f"     Subject   : {res['subject_mr']}")
        if res.get("matched_chunk_text"):
            preview = res["matched_chunk_text"][:80].replace("\n", " ")
            print(f"     Chunk     : {preview}...")
        print(f"     File      : {res['filename']}")
        print("-" * 60)


if __name__ == "__main__":
    main()
