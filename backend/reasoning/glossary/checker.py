"""
Bilingual terminology consistency checker — separate LLM prompt/module from conflict detection.
Uses the shared local Ollama client manager; fails fast when the client is on cooldown.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Type, TypeVar

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reasoning.glossary.exceptions import GlossaryCheckUnavailable
from reasoning.glossary.loader import get_glossary_for_prompt, GLOSSARY_ENTRIES
from reasoning.glossary.models import GlossaryCheckSection, GlossaryFinding, GlossaryLLMOutput
from reasoning.llm_reasoner import get_llm_manager
from reasoning.prompt_utils import (
    LLM_MAX_INPUT_TOKENS,
    REASONING_TEMPERATURE,
    chars_for_token_budget,
    estimate_tokens,
    fit_prompt_pair,
    summarize_draft_for_prompt,
)
from llm.manager import LLMClientManager

logger = logging.getLogger(__name__)

from llm.config import default_reasoning_model

GLOSSARY_MODEL = os.getenv("GLOSSARY_MODEL", default_reasoning_model())
GLOSSARY_MAX_DRAFT_CHARS = int(os.getenv("GLOSSARY_MAX_DRAFT_CHARS", "6000"))
GLOSSARY_MAX_RETRIES = int(os.getenv("GLOSSARY_MAX_RETRIES", "1"))
GLOSSARY_MAX_TOKENS = int(os.getenv("GLOSSARY_MAX_TOKENS", "1536"))

GLOSSARY_OUTPUT_SCHEMA = (
    '{"findings":[{"text_found":str,"context_snippet":str,'
    '"canonical_term":str,"reason":str,"confidence":float}]}'
)

# Minimum token overlap ratio for a finding to be considered a real glossary hit
_MIN_GLOSSARY_OVERLAP = 0.5


def _normalize_term(t: str) -> str:
    """Lowercase, strip punctuation for robust comparison."""
    import re
    return re.sub(r"[^\w\u0900-\u097F]", "", t.lower()).strip()


def _is_glossary_term(text: str) -> bool:
    """
    Return True if 'text' matches any glossary entry's canonical or variant,
    using exact normalized match OR token overlap >= _MIN_GLOSSARY_OVERLAP.
    """
    norm_text = _normalize_term(text)
    if not norm_text:
        return False
    for entry in GLOSSARY_ENTRIES:
        candidates = list(entry.variants)
        if entry.canonical_en:
            candidates.append(entry.canonical_en)
        if entry.canonical_mr:
            candidates.append(entry.canonical_mr)
        for cand in candidates:
            norm_cand = _normalize_term(cand)
            if norm_cand and (norm_text == norm_cand or norm_text in norm_cand or norm_cand in norm_text):
                return True
    return False


def _postfilter_glossary_findings(findings: list) -> list:
    """
    Deterministically filter LLM glossary output:
    1. Drop findings where text_found already equals canonical_term (already correct usage).
    2. Drop findings where text_found doesn't match any known glossary entry variant.
    3. Deduplicate by (text_found, canonical_term), keeping highest confidence.
    """
    filtered: list = []
    seen: dict = {}  # (text_found_norm, canonical_norm) -> best finding

    for f in findings:
        norm_found = _normalize_term(f.text_found)
        norm_canonical = _normalize_term(f.canonical_term)

        # Rule 1: Drop if text_found is already the canonical form
        if norm_found == norm_canonical:
            logger.debug(
                "Glossary post-filter: dropping '%s' (already canonical)", f.text_found
            )
            continue

        # Rule 2: Drop if text_found is not a known glossary entry at all
        if not _is_glossary_term(f.text_found) and not _is_glossary_term(f.canonical_term):
            logger.debug(
                "Glossary post-filter: dropping '%s' (not a glossary entry)", f.text_found
            )
            continue

        # Rule 3: Deduplicate — keep highest confidence per (text_found, canonical) pair
        key = (norm_found, norm_canonical)
        existing = seen.get(key)
        if existing is None or f.confidence > existing.confidence:
            seen[key] = f

    return list(seen.values())

_SYSTEM_PROMPT = """You are a Maharashtra Government Resolution (GR) terminology reviewer.

Your ONLY task is to find terminology inconsistencies in draft GR text against the provided glossary.

STRICT RULES:
1. Flag ONLY terms that match or closely resemble a glossary entry's canonical term or listed variant.
2. Do NOT invent new "should-be-standard" terms that are not in the glossary.
3. Do NOT flag correct uses of canonical terms.
4. Do NOT flag general writing style, grammar, or legal substance — terminology only.
5. For each finding, provide the exact text found, a short context snippet, the canonical replacement,
   a one-line reason, and a confidence score from 0.0 to 1.0.
6. Return an empty findings list if no glossary-related inconsistencies are found.

Return ONLY valid JSON matching this schema:
{schema}
"""

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


def _require_available_client(api_mgr: LLMClientManager) -> tuple[int, object]:
    """Fail fast when the LLM client is cooling down."""
    idx, client = api_mgr.get_client()
    if client is None:
        raise GlossaryCheckUnavailable("llm_unavailable")
    return idx, client


def _call_glossary_llm_json(
    system_prompt: str,
    user_prompt: str,
    model_cls: Type[T],
    *,
    max_retries: int = GLOSSARY_MAX_RETRIES,
) -> T:
    api_mgr = get_llm_manager()
    char_budget = chars_for_token_budget(LLM_MAX_INPUT_TOKENS)
    schema_hint = GLOSSARY_OUTPUT_SCHEMA
    last_exception: Optional[Exception] = None

    for validation_attempt in range(max_retries + 1):
        sys_prompt = system_prompt
        if validation_attempt > 0:
            sys_prompt = (
                system_prompt.split("Return ONLY valid JSON")[0].rstrip()
                + f"\n\nRETRY: Return ONLY JSON matching: {schema_hint}"
            )

        idx, client = _require_available_client(api_mgr)

        fitted_sys, fitted_usr, _ = fit_prompt_pair(
            sys_prompt, user_prompt, max_total_chars=char_budget
        )

        try:
            completion = client.chat.completions.create(  # type: ignore[union-attr]
                model=GLOSSARY_MODEL,
                messages=[
                    {"role": "system", "content": fitted_sys},
                    {"role": "user", "content": fitted_usr},
                ],
                temperature=REASONING_TEMPERATURE,
                response_format={"type": "json_object"},
                max_tokens=GLOSSARY_MAX_TOKENS,
            )
            raw_text = completion.choices[0].message.content or ""
            parsed_dict = json.loads(_clean_json_text(raw_text))
            return model_cls.model_validate(parsed_dict)

        except GlossaryCheckUnavailable:
            raise
        except Exception as e:
            last_exception = e
            err_msg = str(e).lower()

            if any(kw in err_msg for kw in ["rate limit", "429", "quota"]) and idx is not None:
                api_mgr.mark_rate_limited(idx, retry_after=15, all_keys=True)
                # One more key attempt within this validation pass, then fail fast if none left
                try:
                    idx2, client2 = _require_available_client(api_mgr)
                except GlossaryCheckUnavailable:
                    raise
                try:
                    completion = client2.chat.completions.create(  # type: ignore[union-attr]
                        model=GLOSSARY_MODEL,
                        messages=[
                            {"role": "system", "content": fitted_sys},
                            {"role": "user", "content": fitted_usr},
                        ],
                        temperature=REASONING_TEMPERATURE,
                        response_format={"type": "json_object"},
                        max_tokens=GLOSSARY_MAX_TOKENS,
                    )
                    raw_text = completion.choices[0].message.content or ""
                    parsed_dict = json.loads(_clean_json_text(raw_text))
                    return model_cls.model_validate(parsed_dict)
                except GlossaryCheckUnavailable:
                    raise
                except Exception as inner_e:
                    last_exception = inner_e

            if validation_attempt < max_retries:
                logger.warning(
                    "Glossary LLM parse/validation failed (%s). Retry %s/%s.",
                    e,
                    validation_attempt + 1,
                    max_retries,
                )
                continue
            break

    raise RuntimeError(
        f"Failed to generate valid {model_cls.__name__} from LLM: {last_exception}"
    ) from last_exception


def _build_user_prompt(draft_text: str) -> str:
    draft_excerpt = summarize_draft_for_prompt(draft_text, max_chars=GLOSSARY_MAX_DRAFT_CHARS)
    glossary_block = get_glossary_for_prompt()
    return (
        "GLOSSARY (only flag inconsistencies against these entries):\n"
        f"{glossary_block}\n\n"
        "DRAFT TEXT TO REVIEW:\n"
        f"{draft_excerpt}"
    )


def run_glossary_check(draft_text: str) -> GlossaryCheckSection:
    """
    Run terminology consistency check. Returns a section with status — never raises
    GlossaryCheckUnavailable to callers (logged as WARNING degradation).
    """
    if not draft_text.strip():
        return GlossaryCheckSection(status="ok", findings=[])

    system_prompt = _SYSTEM_PROMPT.format(schema=GLOSSARY_OUTPUT_SCHEMA)
    user_prompt = _build_user_prompt(draft_text)

    est_tokens = estimate_tokens(system_prompt) + estimate_tokens(user_prompt)
    logger.info(
        "Glossary check starting (~%s input tokens, %s entries)",
        est_tokens,
        len(get_glossary_for_prompt().splitlines()),
    )

    try:
        output = _call_glossary_llm_json(
            system_prompt,
            user_prompt,
            GlossaryLLMOutput,
        )
        filtered = _postfilter_glossary_findings(output.findings)
        logger.info(
            "Glossary post-filter: %s findings in, %s findings out.",
            len(output.findings),
            len(filtered),
        )
        return GlossaryCheckSection(status="ok", findings=filtered)
    except GlossaryCheckUnavailable as exc:
        logger.warning(
            "Glossary terminology check unavailable: %s (LLM client on cooldown)",
            exc.reason,
        )
        return GlossaryCheckSection(status="unavailable", reason=exc.reason)
    except Exception as exc:
        logger.exception("Glossary terminology check failed: %s", exc)
        return GlossaryCheckSection(status="error", reason="internal_error")
