"""Tests for Groq prompt budgeting."""

from __future__ import annotations

from reasoning.prompt_utils import (
    CONFLICT_OUTPUT_SCHEMA,
    GROQ_MAX_INPUT_TOKENS,
    CHARS_PER_TOKEN,
    estimate_tokens,
    fit_prompt_pair,
    chars_for_token_budget,
)


def test_default_budget_under_groq_limit():
    budget = chars_for_token_budget(GROQ_MAX_INPUT_TOKENS)
    assert budget < GROQ_MAX_INPUT_TOKENS * 4  # well below naive 4 chars/token


def test_fit_prompt_pair_truncates_large_user_prompt():
    sys_p = "System " + CONFLICT_OUTPUT_SCHEMA
    usr_p = "x" * 50000
    _, fitted_usr, truncated = fit_prompt_pair(sys_p, usr_p, max_total_chars=8000)
    assert truncated is True
    assert len(fitted_usr) < len(usr_p)


def test_marathi_token_estimate_is_conservative():
    marathi = "महाराष्ट्र शासन निर्णय " * 200
    tokens = estimate_tokens(marathi)
    # Should be more tokens than len/4 (English assumption)
    assert tokens > len(marathi) / 4
