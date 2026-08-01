"""
LLM Reasoning engine for Q&A, pairwise GR comparison, and conflict detection.
Uses Groq multi-key APIManager and strict Pydantic model validation.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Type, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from database.db import Database
from reasoning.context_builder import build_context_block
from reasoning.models import (
    ComparisonResult,
    ConflictFinding,
    QueryAnswer,
    SupportingGR,
)
from retrieval.hybrid import hybrid_search
from scripts.api_manager import APIManager

REASONING_MODEL = os.getenv("REASONING_MODEL", "llama-3.3-70b-versatile")
DEFAULT_MAX_FULL_TEXT = int(os.getenv("REASONING_MAX_FULL_TEXT_DOCS", "8"))

_api_manager: Optional[APIManager] = None


def get_api_manager() -> APIManager:
    """Lazy initialization of Groq APIManager singleton."""
    global _api_manager
    if _api_manager is None:
        _api_manager = APIManager()
    return _api_manager


T = TypeVar("T", bound=BaseModel)


def _clean_json_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


FALLBACK_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]


def _call_llm_json(
    system_prompt: str,
    user_prompt: str,
    model_cls: Type[T],
    max_retries: int = 1,
) -> T:
    """
    Execute Groq LLM completion with APIManager rotation, model fallbacks, and Pydantic model validation.
    """
    api_mgr = get_api_manager()

    models_to_try = [REASONING_MODEL]
    for fallback in FALLBACK_MODELS:
        if fallback not in models_to_try:
            models_to_try.append(fallback)

    last_exception = None

    for model_name in models_to_try:
        attempt = 0
        curr_sys = system_prompt
        curr_usr = user_prompt

        while attempt <= max_retries:
            idx, client = api_mgr.wait_for_client(max_wait=30)
            if client is None:
                break

            try:
                completion = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": curr_sys},
                        {"role": "user", "content": curr_usr},
                    ],
                    temperature=0.1,
                    response_format={"type": "json_object"},
                )

                raw_text = completion.choices[0].message.content or ""
                cleaned = _clean_json_text(raw_text)
                parsed_dict = json.loads(cleaned)
                return model_cls.model_validate(parsed_dict)

            except Exception as e:
                last_exception = e
                err_msg = str(e).lower()

                # If rate-limited, decommissioned, or invalid model, skip to next model immediately
                if any(kw in err_msg for kw in ["rate limit", "429", "quota", "decommissioned", "not supported"]):
                    print(f"Notice: Model {model_name} unavailable ({e}). Falling back to next model...")
                    if idx is not None and ("rate limit" in err_msg or "429" in err_msg):
                        api_mgr.mark_rate_limited(idx, retry_after=15, all_keys=True)
                    break

                attempt += 1
                if attempt <= max_retries:
                    print(f"Warning: Response validation against {model_cls.__name__} failed ({e}). Retrying...")
                    curr_sys = (
                        system_prompt
                        + "\n\nCRITICAL ERROR: Output was not valid JSON. Return ONLY valid JSON matching schema."
                    )
                    curr_usr = (
                        user_prompt
                        + "\n\nEnsure output is strictly valid JSON matching schema."
                    )

    raise RuntimeError(
        f"Failed to generate valid {model_cls.__name__} output from Groq API: {last_exception}"
    ) from last_exception




def answer_query(
    query: str,
    top_k: int = 20,
    hops: int = 1,
    db: Optional[Database] = None,
) -> QueryAnswer:
    """
    Perform natural language Q&A over the GR corpus using RAG.
    """
    print(f"\n--- [answer_query] Processing query: '{query}' ---")
    results = hybrid_search(query, top_k=top_k, hops=hops, db=db)
    print(f"Retrieved {len(results)} candidate GRs from hybrid search.")

    context_text, label_map = build_context_block(
        results, max_full_text=DEFAULT_MAX_FULL_TEXT, db=db
    )

    prompt_chars = len(context_text) + len(query)
    approx_tokens = prompt_chars // 4
    print(f"Context built: {len(results)} GR entries | {prompt_chars} chars (~{approx_tokens} tokens)")

    schema_json = json.dumps(QueryAnswer.model_json_schema(), indent=2)

    system_prompt = f"""
You are an expert AI Legal Assistant specializing in Maharashtra Government Resolutions (GRs).
Your task is to answer user queries based STRICTLY on the provided GR Context block.

CRITICAL INSTRUCTIONS:
1. Base your answer ONLY on the provided GR context. Do NOT use outside knowledge or hallucinate facts.
2. For EVERY claim, policy detail, or date, cite the specific GR label (e.g. [GR 1], [GR 2]).
3. Populate supporting_grs with all cited GR labels and their canonical GR numbers.
4. Output MUST be valid JSON strictly adhering to the JSON schema below. No markdown fences, no explanatory prose outside JSON.

JSON Schema:
{schema_json}
""".strip()

    user_prompt = f"User Query: {query}\n\nGR Context:{context_text}"

    return _call_llm_json(system_prompt, user_prompt, QueryAnswer)


def compare_grs(
    gr_id_a: int,
    gr_id_b: int,
    db: Optional[Database] = None,
) -> ComparisonResult:
    """
    Perform pairwise clause-by-clause comparison and contradiction detection between two GRs.
    """
    print(f"\n--- [compare_grs] Comparing GR ID {gr_id_a} vs GR ID {gr_id_b} ---")

    owns_db = db is None
    database = db or Database()

    try:
        query_sql = """
        SELECT id, filename, gr_number_canonical, department, gr_date, subject_mr, ocr_text
        FROM gr_documents
        WHERE id = ANY(%s)
        """
        database.cur.execute(query_sql, ([gr_id_a, gr_id_b],))
        rows = database.cur.fetchall()
        cols = [desc[0] for desc in database.cur.description]
        docs = {r[0]: dict(zip(cols, r)) for r in rows}

        if gr_id_a not in docs:
            raise ValueError(f"GR ID {gr_id_a} not found in database.")
        if gr_id_b not in docs:
            raise ValueError(f"GR ID {gr_id_b} not found in database.")

        doc_a = docs[gr_id_a]
        doc_b = docs[gr_id_b]

        print(f"GR A [ID {gr_id_a}]: {doc_a.get('gr_number_canonical')} ({doc_a.get('department')})")
        print(f"GR B [ID {gr_id_b}]: {doc_b.get('gr_number_canonical')} ({doc_b.get('department')})")

        ocr_a = (doc_a.get("ocr_text") or "").strip()[:2500]
        ocr_b = (doc_b.get("ocr_text") or "").strip()[:2500]

        context_text = f"""
[GR A]
ID: {gr_id_a}
Canonical GR Number: {doc_a.get('gr_number_canonical')}
Department: {doc_a.get('department')}
Date: {doc_a.get('gr_date')}
Subject: {doc_a.get('subject_mr')}
OCR Excerpt:
{ocr_a if ocr_a else 'No text available'}

============================================================

[GR B]
ID: {gr_id_b}
Canonical GR Number: {doc_b.get('gr_number_canonical')}
Department: {doc_b.get('department')}
Date: {doc_b.get('gr_date')}
Subject: {doc_b.get('subject_mr')}
OCR Excerpt:
{ocr_b if ocr_b else 'No text available'}
""".strip()

        prompt_chars = len(context_text)
        approx_tokens = prompt_chars // 4
        print(f"Comparison prompt built: {prompt_chars} chars (~{approx_tokens} tokens)")

        schema_json = json.dumps(ComparisonResult.model_json_schema(), indent=2)

        system_prompt = f"""
You are an expert Maharashtra Government Resolution (GR) Analyst.
Compare [GR A] and [GR B] clause-by-clause and identify:
1. Added: Provisions or rules present in GR B but missing in GR A.
2. Removed: Provisions present in GR A but missing in GR B.
3. Changed: Modified policy terms, eligibility, dates, or financial allocations.
4. Contradictions: Direct legal or policy conflicts between the two GRs.

Output MUST be valid JSON strictly adhering to the JSON schema below. No markdown text outside JSON.

JSON Schema:
{schema_json}
""".strip()

        user_prompt = f"Compare [GR A] and [GR B]:\n\n{context_text}"

        return _call_llm_json(system_prompt, user_prompt, ComparisonResult)

    finally:
        if owns_db:
            database.close()


def check_conflict(
    draft_input: str,
    top_k: int = 15,
    hops: int = 1,
    db: Optional[Database] = None,
) -> ConflictFinding:
    """
    Check a new/draft GR text against existing related GRs for conflicts, duplications, or superseding policies.
    """
    print("\n--- [check_conflict] Analyzing draft GR for conflicts ---")

    draft_text = draft_input
    if len(draft_input) < 512:
        try:
            draft_path = Path(draft_input)
            if draft_path.exists() and draft_path.is_file():
                print(f"Reading draft text from file: {draft_path}")
                draft_text = draft_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            pass

    draft_text_clean = draft_text.strip()
    if not draft_text_clean:
        raise ValueError("Draft text is empty.")

    # Use first 500 characters of draft as query for hybrid search
    query_seed = draft_text_clean[:500]
    results = hybrid_search(query_seed, top_k=top_k, hops=hops, db=db)
    print(f"Retrieved {len(results)} candidate GRs for conflict analysis.")

    context_text, label_map = build_context_block(
        results, max_full_text=DEFAULT_MAX_FULL_TEXT, db=db
    )

    prompt_chars = len(draft_text_clean) + len(context_text)
    approx_tokens = prompt_chars // 4
    print(f"Conflict check prompt built: {prompt_chars} chars (~{approx_tokens} tokens)")

    schema_json = json.dumps(ConflictFinding.model_json_schema(), indent=2)

    system_prompt = f"""
You are an AI Legal Auditor for Maharashtra Government Resolutions (GRs).
Your task is to analyze a PROPOSED DRAFT GR against existing Government Resolutions in the corpus.

CRITICAL INSTRUCTIONS:
1. Determine if the Proposed Draft conflicts with, duplicates, or contradicts existing GRs in the context.
2. Flag CROSS-DEPARTMENTAL conflicts explicitly if the draft conflicts with a GR from a different department.
3. List specific conflicting clauses and cite affected GRs by label (e.g. [GR 1], [GR 2]).
4. Output MUST be valid JSON strictly conforming to the schema below. No markdown fences outside JSON.

JSON Schema:
{schema_json}
""".strip()

    user_prompt = f"PROPOSED DRAFT GR:\n{draft_text_clean[:3000]}\n\nEXISTING GR CONTEXT:{context_text}"

    return _call_llm_json(system_prompt, user_prompt, ConflictFinding)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m reasoning.llm_reasoner query '<user_query>'")
        print("  python -m reasoning.llm_reasoner compare <gr_id_a> <gr_id_b>")
        print("  python -m reasoning.llm_reasoner conflict '<draft text or file path>'")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "query":
        q = sys.argv[2] if len(sys.argv) > 2 else "does GR conflict with scholarship policy"
        res = answer_query(q)
        print("\n=== Result (QueryAnswer) ===")
        print(json.dumps(res.model_dump(), ensure_ascii=False, indent=2))

    elif cmd == "compare":
        if len(sys.argv) < 4:
            print("Error: compare requires two GR IDs: python -m reasoning.llm_reasoner compare <id_a> <id_b>")
            sys.exit(1)
        id_a = int(sys.argv[2])
        id_b = int(sys.argv[3])
        res = compare_grs(id_a, id_b)
        print("\n=== Result (ComparisonResult) ===")
        print(json.dumps(res.model_dump(), ensure_ascii=False, indent=2))

    elif cmd == "conflict":
        draft = sys.argv[2] if len(sys.argv) > 2 else "मुलींसाठी शिष्यवृत्ती योजना"
        res = check_conflict(draft)
        print("\n=== Result (ConflictFinding) ===")
        print(json.dumps(res.model_dump(), ensure_ascii=False, indent=2))

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
