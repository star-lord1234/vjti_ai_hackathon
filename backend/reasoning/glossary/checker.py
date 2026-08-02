"""
Bilingual terminology consistency checker — separate LLM prompt/module from conflict detection.
Uses the shared Groq APIManager; fails fast when all keys are on cooldown.
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
from reasoning.glossary.loader import get_glossary_for_prompt
from reasoning.glossary.models import GlossaryCheckSection, GlossaryLLMOutput
from reasoning.llm_reasoner import get_api_manager
from reasoning.prompt_utils import (
    GROQ_MAX_INPUT_TOKENS,
    REASONING_TEMPERATURE,
    chars_for_token_budget,
    estimate_tokens,
    fit_prompt_pair,
    summarize_draft_for_prompt,
)
from scripts.api_manager import APIManager

logger = logging.getLogger(__name__)

GLOSSARY_MODEL = os.getenv("GLOSSARY_MODEL", os.getenv("REASONING_MODEL", "llama-3.3-70b-versatile"))
GLOSSARY_MAX_DRAFT_CHARS = int(os.getenv("GLOSSARY_MAX_DRAFT_CHARS", "6000"))
GLOSSARY_MAX_RETRIES = int(os.getenv("GLOSSARY_MAX_RETRIES", "1"))
GLOSSARY_MAX_TOKENS = int(os.getenv("GLOSSARY_MAX_TOKENS", "1536"))

GLOSSARY_OUTPUT_SCHEMA = (
    '{"findings":[{"text_found":str,"context_snippet":str,'
    '"canonical_term":str,"reason":str,"confidence":float}]}'
)

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


def _require_available_client(api_mgr: APIManager) -> tuple[int, object]:
    """Fail fast when no Groq key is usable — do not block waiting for cooldown."""
    idx, client = api_mgr.get_client()
    if client is None:
        raise GlossaryCheckUnavailable("api_quota_exhausted")
    return idx, client


def _call_glossary_llm_json(
    system_prompt: str,
    user_prompt: str,
    model_cls: Type[T],
    *,
    max_retries: int = GLOSSARY_MAX_RETRIES,
) -> T:
    api_mgr = get_api_manager()
    char_budget = chars_for_token_budget(GROQ_MAX_INPUT_TOKENS)
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
        f"Failed to generate valid {model_cls.__name__} from Groq: {last_exception}"
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
        return GlossaryCheckSection(status="ok", findings=output.findings)
    except GlossaryCheckUnavailable as exc:
        logger.warning(
            "Glossary terminology check unavailable: %s (all Groq API keys on cooldown)",
            exc.reason,
        )
        return GlossaryCheckSection(status="unavailable", reason=exc.reason)
    except Exception as exc:
        logger.exception("Glossary terminology check failed: %s", exc)
        return GlossaryCheckSection(status="error", reason="internal_error")
