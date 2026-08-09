"""
LLM Reasoning engine for Q&A, pairwise GR comparison, and conflict detection.
Uses local Ollama via LLMClientManager and strict Pydantic model validation.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional, Type, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from offline import configure_offline_mode

configure_offline_mode()

from database.db import Database
from embeddings.search import build_draft_query_segments
from reasoning.context_builder import build_context_block
from reasoning.json_utils import extract_json_object
from reasoning.clause_parser import extract_draft_clauses, format_clauses_for_prompt
from reasoning.models import (
    ComparisonResult,
    ConflictFinding,
    ConflictLLMOutput,
    QueryAnswer,
    RetrievalQualityInfo,
    RuleSignal,
)
from reasoning.retrieval_gate import (
    assess_retrieval_quality,
    build_degradation_reasons,
    rerank_with_draft_overlap,
)
from reasoning.rule_signals import extract_rule_signals, format_rule_signals_for_prompt
from database.sync_status import check_store_sync
from reasoning.prompt_utils import (
    COMPARE_OUTPUT_SCHEMA,
    CONFLICT_CONTEXT_CHARS,
    CONFLICT_DRAFT_CHARS,
    CONFLICT_EXCERPT_CHARS,
    CONFLICT_OUTPUT_SCHEMA,
    LLM_MAX_INPUT_TOKENS,
    MAX_PROMPT_CHARS,
    QUERY_OUTPUT_SCHEMA,
    REASONING_TEMPERATURE,
    apply_conflict_post_validation,
    apply_query_post_validation,
    build_compare_ocr_sections,
    chars_for_token_budget,
    estimate_tokens,
    fit_prompt_pair,
    summarize_draft_for_prompt,
    temporal_context_note,
)
from retrieval.hybrid import hybrid_search
from llm.config import default_reasoning_model
from llm.manager import LLMClientManager

REASONING_MODEL = default_reasoning_model()
DEFAULT_MAX_FULL_TEXT = int(os.getenv("REASONING_MAX_FULL_TEXT_DOCS", "8"))
CONFLICT_MAX_FULL_TEXT = int(os.getenv("CONFLICT_MAX_FULL_TEXT_DOCS", "3"))
CONFLICT_TOP_K = int(os.getenv("CONFLICT_TOP_K", "5"))
CONFLICT_MAX_TOKENS = int(os.getenv("CONFLICT_MAX_TOKENS", "768"))
MAX_LLM_RETRIES = int(os.getenv("REASONING_MAX_RETRIES", "1"))

_api_manager: Optional[LLMClientManager] = None


def get_llm_manager() -> LLMClientManager:
    """Lazy initialization of local Ollama client manager."""
    global _api_manager
    if _api_manager is None:
        _api_manager = LLMClientManager()
    return _api_manager


# Backward-compatible alias used by glossary checker tests/patches
get_api_manager = get_llm_manager


T = TypeVar("T", bound=BaseModel)

# Only treat inputs with path separators as filesystem paths.
_DRAFT_PATH_EXTENSIONS = (".txt", ".md", ".json", ".text")


def resolve_draft_text(draft_input: str) -> str:
    """
    Return draft body text. Short inputs are read from disk only when they
    look like explicit file paths (separator or known extension), avoiding
  accidental reads when a query string matches an existing path.
    """
    if len(draft_input) >= 512:
        return draft_input

    stripped = draft_input.strip()
    # Require path separators — bare filenames like "probe.txt" are draft text
    looks_like_path = "/" in stripped or "\\" in stripped
    if not looks_like_path:
        return draft_input

    try:
        draft_path = Path(stripped)
        if draft_path.exists() and draft_path.is_file():
            print(f"Reading draft text from file: {draft_path}")
            return draft_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        pass

    return draft_input


def _fallback_models() -> list[str]:
    models = [REASONING_MODEL]
    # Deduplicate preserving order
    seen: set[str] = set()
    out: list[str] = []
    for m in models:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _is_request_too_large(err_msg: str) -> bool:
    return any(
        kw in err_msg
        for kw in (
            "413",
            "too large",
            "request too large",
            "tokens per minute",
            "tpm",
            "context length",
            "maximum context",
        )
    )


def _call_llm_json(
    system_prompt: str,
    user_prompt: str,
    model_cls: Type[T],
    max_retries: Optional[int] = None,
    compact_schema: Optional[str] = None,
    char_budget: Optional[int] = None,
    max_tokens: Optional[int] = None,
) -> T:
    """LLM JSON completion with prompt fitting and automatic shrink on token-limit errors."""
    if max_retries is None:
        max_retries = MAX_LLM_RETRIES

    base_sys = system_prompt
    base_usr = user_prompt
    curr_budget = char_budget or MAX_PROMPT_CHARS
    schema_hint = compact_schema or "valid JSON with all required fields"
    api_mgr = get_llm_manager()
    last_exception: Optional[Exception] = None

    for model_name in _fallback_models():
        rate_limited_model = False

        for validation_attempt in range(max_retries + 1):
            sys_prompt = base_sys
            if validation_attempt > 0:
                sys_prompt = (
                    base_sys.split("JSON Schema:")[0].rstrip()
                    + f"\n\nRETRY: Return ONLY JSON matching: {schema_hint}"
                )

            budget = curr_budget
            for shrink_pass in range(6):
                fitted_sys, fitted_usr, _ = fit_prompt_pair(
                    sys_prompt, base_usr, max_total_chars=budget
                )

                idx, client = api_mgr.wait_for_client(max_wait=30)
                if client is None:
                    rate_limited_model = True
                    break

                try:
                    completion = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": fitted_sys},
                            {"role": "user", "content": fitted_usr},
                        ],
                        temperature=REASONING_TEMPERATURE,
                        response_format={"type": "json_object"},
                        max_tokens=max_tokens or CONFLICT_MAX_TOKENS,
                    )

                    raw_text = completion.choices[0].message.content or ""
                    if not raw_text.strip():
                        raise ValueError("LLM returned empty content")
                    parsed_dict = extract_json_object(raw_text)
                    return model_cls.model_validate(parsed_dict)

                except Exception as e:
                    last_exception = e
                    err_msg = str(e).lower()

                    if _is_request_too_large(err_msg) and shrink_pass < 5:
                        budget = max(2500, int(budget * 0.65))
                        curr_budget = budget
                        print(
                            f"Warning: LLM context limit ({e}). "
                            f"Shrinking to {budget} chars (pass {shrink_pass + 1})..."
                        )
                        continue

                    if any(
                        kw in err_msg
                        for kw in ["rate limit", "429", "quota", "decommissioned", "not supported"]
                    ) and not _is_request_too_large(err_msg):
                        if idx is not None and ("rate limit" in err_msg or "429" in err_msg):
                            api_mgr.mark_rate_limited(idx, retry_after=15, all_keys=True)
                        rate_limited_model = True
                        break

                    if validation_attempt < max_retries:
                        print(
                            f"Warning: {model_cls.__name__} parse failed ({e}). "
                            f"Retry {validation_attempt + 1}/{max_retries}..."
                        )
                    break  # leave shrink loop → next validation attempt or model

            if rate_limited_model:
                break

    raise RuntimeError(
        f"Failed to generate valid {model_cls.__name__} output from LLM: {last_exception}"
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
    results, retrieval_meta = hybrid_search(
        query, top_k=top_k, hops=hops, db=db, return_meta=True
    )
    print(f"Retrieved {len(results)} candidate GRs from hybrid search.")
    if retrieval_meta.graph_degraded:
        print(f"Warning: graph retrieval degraded — {retrieval_meta.graph_error}")

    context_text, label_map = build_context_block(
        results, max_full_text=DEFAULT_MAX_FULL_TEXT, db=db
    )

    temporal_note = temporal_context_note(results)
    prompt_chars = len(context_text) + len(query) + len(temporal_note)
    print(f"Context built: {len(results)} GR entries | {prompt_chars} chars (~{prompt_chars // 4} tokens)")

    schema_json = QUERY_OUTPUT_SCHEMA

    system_prompt = f"""
You are an expert AI Legal Assistant for Maharashtra Government Resolutions (GRs).
Answer STRICTLY from the provided GR context. Cite GR labels like [GR 1].
Output valid JSON only (no markdown).

JSON Schema:
{schema_json}
""".strip()

    user_prompt = f"User Query: {query}\n{temporal_note}\nGR Context:{context_text}"

    answer = _call_llm_json(
        system_prompt, user_prompt, QueryAnswer, compact_schema=QUERY_OUTPUT_SCHEMA
    )
    return apply_query_post_validation(answer, label_map)


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

        context_text = build_compare_ocr_sections(doc_a, doc_b, gr_id_a, gr_id_b)

        prompt_chars = len(context_text)
        print(f"Comparison prompt built: {prompt_chars} chars (~{prompt_chars // 4} tokens)")

        schema_json = COMPARE_OUTPUT_SCHEMA

        system_prompt = f"""
You are a Maharashtra GR analyst. Compare GR A and GR B; list added, removed, changed, contradictions.
Output valid JSON only.

JSON Schema:
{schema_json}
""".strip()

        user_prompt = f"Compare [GR A] and [GR B]:\n\n{context_text}"

        return _call_llm_json(
            system_prompt,
            user_prompt,
            ComparisonResult,
            compact_schema=COMPARE_OUTPUT_SCHEMA,
        )

    finally:
        if owns_db:
            database.close()


import hashlib
import time

_CONFLICT_CACHE: Dict[str, Tuple[float, ConflictFinding]] = {}
_CLAUSE_CONFLICT_CACHE: Dict[str, Tuple[float, List[ConflictPair]]] = {}
_CONFLICT_CACHE_TTL = 600  # 10 minutes TTL
_MAX_CONFLICT_CACHE = 128


def _draft_conflict_cache_key(draft_text: str, top_k: int = 15, hops: int = 1) -> str:
    lines = (draft_text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    clean_text = "\n".join(line.rstrip() for line in lines).strip()
    return hashlib.sha256(clean_text.encode("utf-8")).hexdigest()[:24]


def _clause_hash(clause_text: str) -> str:
    clean = (clause_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()[:24]


def clear_conflict_cache() -> None:
    """Clear in-memory conflict analysis cache."""
    _CONFLICT_CACHE.clear()
    _CLAUSE_CONFLICT_CACHE.clear()


def check_conflict(
    draft_input: str,
    top_k: int = CONFLICT_TOP_K,
    hops: int = 1,
    db: Optional[Database] = None,
) -> ConflictFinding:
    """
    Check a new/draft GR text against existing related GRs for conflicts, duplications, or superseding policies.
    Supports instant document caching (<0.001s) and incremental clause-level re-evaluation.
    """
    print("\n--- [check_conflict] Analyzing draft GR for conflicts ---")

    draft_text = resolve_draft_text(draft_input)

    draft_text_clean = draft_text.strip()
    if not draft_text_clean:
        raise ValueError("Draft text is empty.")

    cache_key = _draft_conflict_cache_key(draft_text_clean, top_k, hops)
    now = time.time()
    if cache_key in _CONFLICT_CACHE:
        ts, cached_finding = _CONFLICT_CACHE[cache_key]
        if now - ts < _CONFLICT_CACHE_TTL:
            print("--- [check_conflict] Document Cache Hit! Returning cached ConflictFinding immediately ---")
            return cached_finding

    draft_clauses = extract_draft_clauses(draft_text_clean)

    # Clause-level incremental cache lookup
    cached_pairs: List[ConflictPair] = []
    uncached_clauses: List[str] = []

    if draft_clauses:
        for c in draft_clauses:
            ch = _clause_hash(c)
            if ch in _CLAUSE_CONFLICT_CACHE:
                ts, pairs_for_c = _CLAUSE_CONFLICT_CACHE[ch]
                if now - ts < _CONFLICT_CACHE_TTL:
                    cached_pairs.extend(pairs_for_c)
                    continue
            uncached_clauses.append(c)

        if len(uncached_clauses) == 0:
            print(f"--- [check_conflict] All {len(draft_clauses)} clauses hit clause-level cache! Returning instantly ---")
            finding = ConflictFinding(
                conflicting=len(cached_pairs) > 0,
                conflict_pairs=cached_pairs,
                draft_clauses_detected=draft_clauses,
                explanation="Clause-level cached findings verified — no policy conflicts detected in unchanged clauses.",
            )
            _CONFLICT_CACHE[cache_key] = (now, finding)
            return finding

    # Evaluate only uncached (new or modified) clauses if some clauses were cached
    has_cached_clauses = bool(draft_clauses) and (len(uncached_clauses) < len(draft_clauses))
    eval_text = "\n\n".join(uncached_clauses) if (uncached_clauses and has_cached_clauses) else draft_text_clean
    effective_top_k = min(top_k, 5) if has_cached_clauses else top_k
    if uncached_clauses and has_cached_clauses:
        print(f"--- [check_conflict] Incremental Recheck: {len(draft_clauses) - len(uncached_clauses)} untouched clause(s) preserved · Evaluating {len(uncached_clauses)} modified clause(s) ---")


    query_segments = build_draft_query_segments(eval_text)
    print(
        f"Conflict retrieval using {len(query_segments)} draft segment(s) "
        f"(min score threshold via SEMANTIC_MIN_SCORE, top_k={effective_top_k})"
    )
    results, retrieval_meta = hybrid_search(
        query_segments, top_k=effective_top_k, hops=hops, db=db, return_meta=True
    )


    # Lightweight rerank + pre-LLM retrieval gate
    results = rerank_with_draft_overlap(results, draft_text_clean)
    quality_dict = assess_retrieval_quality(results, retrieval_meta)
    store_sync = check_store_sync(db=db)
    degradation_reasons = build_degradation_reasons(quality_dict, store_sync)
    retrieval_quality = RetrievalQualityInfo(**quality_dict)

    draft_clauses = extract_draft_clauses(draft_text_clean)
    rule_signal_dicts = extract_rule_signals(draft_text_clean, results)
    rule_signals = [
        RuleSignal(
            signal_type=s["signal_type"],
            value=s["value"],
            note=s.get("note", ""),
            matched_gr_id=int(s["matched_gr_id"])
            if s.get("matched_gr_id") and str(s["matched_gr_id"]).isdigit()
            else None,
        )
        for s in rule_signal_dicts
    ]

    context_text, label_map = build_context_block(
        results, max_full_text=2 if has_cached_clauses else DEFAULT_MAX_FULL_TEXT
    )


    if retrieval_meta.graph_degraded:
        print(
            f"Warning: graph retrieval degraded — {retrieval_meta.graph_error}. "
            "Citation-linked GRs may be missing from context."
        )
    elif retrieval_meta.graph_skipped:
        print("Graph expansion skipped (hops=0).")
    else:
        print(
            f"Hybrid retrieval: {retrieval_meta.vector_seeds} vector seeds, "
            f"{retrieval_meta.graph_nodes_added} graph nodes added."
        )
    print(
        f"Retrieved {len(results)} candidate GRs "
        f"(gate passed={quality_dict['passed']}, max_score={quality_dict['max_score']:.3f})."
    )

    if not quality_dict["passed"]:
        return ConflictFinding(
            conflicting=False,
            explanation=(
                "Insufficient retrieval quality to assess conflicts confidently. "
                "No GRs met the similarity threshold or the corpus may need re-embedding. "
                + " ".join(quality_dict.get("warnings") or [])
            ).strip(),
            confidence=0.2,
            degraded=True,
            degradation_reasons=degradation_reasons,
            retrieval_quality=retrieval_quality,
            rule_signals=rule_signals,
            draft_clauses_detected=draft_clauses,
        )

    context_text, label_map = build_context_block(
        results[: 3 if has_cached_clauses else CONFLICT_TOP_K],
        max_full_text=2 if has_cached_clauses else CONFLICT_MAX_FULL_TEXT,
        excerpt_chars=600 if has_cached_clauses else CONFLICT_EXCERPT_CHARS,
        max_context_chars=4000 if has_cached_clauses else CONFLICT_CONTEXT_CHARS,
        db=db,
    )

    draft_for_prompt = summarize_draft_for_prompt(
        eval_text if has_cached_clauses else draft_text_clean,
        max_chars=2000 if has_cached_clauses else CONFLICT_DRAFT_CHARS,
    )
    temporal_note = (
        "\n\nNOTE ON TEMPORAL ORDERING: GRs above are listed newest-first. "
        "A newer GR supercedes older GRs on the same topic."
    )
    clauses_note = (
        f"\n\n{format_clauses_for_prompt(draft_clauses)}" if draft_clauses else ""
    )
    signals_note = (
        f"\n\n{format_rule_signals_for_prompt(rule_signal_dicts[:8])}" if rule_signal_dicts else ""
    )

    prompt_chars = (
        len(draft_for_prompt)
        + len(context_text)
        + len(temporal_note)
        + len(clauses_note)
        + len(signals_note)
    )
    est_tokens = estimate_tokens(
        draft_for_prompt + context_text + temporal_note + clauses_note + signals_note
    )
    print(f"Conflict check prompt built: {prompt_chars} chars (~{est_tokens} tokens est.)")

    schema_json = CONFLICT_OUTPUT_SCHEMA

    system_prompt = f"""
You are an AI Legal Auditor for Maharashtra Government Resolutions (GRs).
Analyze the PROPOSED DRAFT against existing GRs in context.
Set cross_departmental / supersession_detected when applicable.
Cite GRs ONLY by labels in context (e.g. [GR 1]). Use RULE SIGNALS as hints.
For each affected_gr, set corpus_excerpt to the EXACT quote from that GR's OCR in context
that conflicts with the draft (e.g. if draft says ₹25,000 and [GR 2] says ₹24,000, quote the ₹24,000 sentence).
Output valid JSON only.

JSON Schema:
{schema_json}
""".strip()

    user_prompt = (
        f"PROPOSED DRAFT RESOLUTION TO REVIEW:\n{draft_for_prompt}"
        f"{clauses_note}"
        f"{signals_note}"
        f"{temporal_note}\n"
        f"EXISTING GR CONTEXT (newest-first):{context_text}"
    )

    conflict_budget = chars_for_token_budget(LLM_MAX_INPUT_TOKENS - 800)
    llm_out = _call_llm_json(
        system_prompt,
        user_prompt,
        ConflictLLMOutput,
        compact_schema=CONFLICT_OUTPUT_SCHEMA,
        char_budget=conflict_budget,
        max_tokens=512 if has_cached_clauses else CONFLICT_MAX_TOKENS,
    )
    finding = ConflictFinding(
        **llm_out.model_dump(),
        degraded=bool(degradation_reasons),
        degradation_reasons=degradation_reasons,
        retrieval_quality=retrieval_quality,
        rule_signals=rule_signals,
        draft_clauses_detected=draft_clauses,
    )
    finding = apply_conflict_post_validation(finding, label_map)

    # Boost cross_departmental from deterministic department_mismatch signals
    if any(s.signal_type == "department_mismatch" for s in rule_signals):
        finding.cross_departmental = True

    # Merge cached clause pairs from untouched clauses with newly evaluated clause pairs
    if cached_pairs:
        all_pairs = list(finding.conflict_pairs or []) + cached_pairs
        seen_pair_keys = set()
        deduped = []
        for p in all_pairs:
            key = f"{p.draft_clause}::{p.gr_label}"
            if key not in seen_pair_keys:
                seen_pair_keys.add(key)
                deduped.append(p)
        finding.conflict_pairs = deduped
        finding.conflicting = len(deduped) > 0

    # Populate clause-level cache for ALL detected clauses (both conflicting and clean)
    for c in draft_clauses:
        ch = _clause_hash(c)
        c_pairs = [
            p for p in (finding.conflict_pairs or [])
            if _clause_hash(p.draft_clause or p.draft_proposes or "") == ch or c in (p.draft_clause or "")
        ]
        _CLAUSE_CONFLICT_CACHE[ch] = (now, c_pairs)

    if len(_CONFLICT_CACHE) >= _MAX_CONFLICT_CACHE:
        _CONFLICT_CACHE.clear()
    _CONFLICT_CACHE[cache_key] = (now, finding)

    return finding




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
