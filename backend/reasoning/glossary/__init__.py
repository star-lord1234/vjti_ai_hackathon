"""Bilingual GR terminology glossary checker (separate from conflict detection)."""

from reasoning.glossary.checker import run_glossary_check
from reasoning.glossary.exceptions import GlossaryCheckUnavailable
from reasoning.glossary.loader import GLOSSARY_ENTRIES, get_glossary_for_prompt
from reasoning.glossary.models import (
    GlossaryCheckSection,
    GlossaryFinding,
    GlossaryLLMOutput,
)

__all__ = [
    "GLOSSARY_ENTRIES",
    "GlossaryCheckSection",
    "GlossaryCheckUnavailable",
    "GlossaryFinding",
    "GlossaryLLMOutput",
    "get_glossary_for_prompt",
    "run_glossary_check",
]
