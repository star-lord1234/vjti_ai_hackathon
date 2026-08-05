"""
Pydantic response models for structured LLM reasoning and RAG answers.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator

UNPARSEABLE_CONFIDENCE = float(os.getenv("REASONING_UNPARSEABLE_CONFIDENCE", "0.5"))


def _clamp_confidence_value(v: Any, default_on_none: float = 0.7) -> float:
    if v is None:
        return default_on_none
    try:
        val = float(str(v).replace("%", "").strip())
        if val > 1.0 and val <= 100.0:
            val = val / 100.0
        return max(0.0, min(1.0, val))
    except Exception:
        return UNPARSEABLE_CONFIDENCE


class RuleSignal(BaseModel):
    """Deterministic overlap signal from rule extraction / regex."""

    signal_type: str = Field(description="e.g. amount_overlap, jurisdiction_overlap")
    value: str = Field(description="Matched token or value")
    note: str = Field(default="", description="Human-readable signal explanation")
    matched_gr_id: Optional[int] = Field(
        default=None, description="Corpus GR id when applicable"
    )


class RetrievalQualityInfo(BaseModel):
    """Pre-LLM retrieval assessment exposed to clients."""

    passed: bool = Field(description="True when enough results meet score threshold")
    result_count: int = 0
    above_threshold_count: int = 0
    max_score: float = 0.0
    min_score_threshold: float = 0.35
    chunk_hits: int = 0
    graph_degraded: bool = False
    graph_skipped: bool = False
    warnings: List[str] = Field(default_factory=list)


class SupportingGR(BaseModel):
    """
    Reference to a supporting or cited Government Resolution.
    """

    label: str = Field(
        description="GR label from context, e.g. '[GR 1]'"
    )
    gr_number_canonical: Optional[str] = Field(
        default=None,
        description="Canonical GR number (internal key) if available",
    )
    gr_number_original: Optional[str] = Field(
        default=None,
        description="Official original GR number as it appears in the document.",
    )
    gr_number_normalized: Optional[str] = Field(
        default=None,
        description="Normalized/formatted GR number for display.",
    )
    relevance_note: Optional[str] = Field(
        default=None,
        description="Brief note on why this GR supports or relates to the claim",
    )
    corpus_excerpt: Optional[str] = Field(
        default=None,
        description="Exact quote from this GR's OCR text that conflicts with the draft.",
    )


class QueryAnswer(BaseModel):
    """
    Structured answer to a natural language Q&A query over the GR corpus.
    """

    answer: str = Field(
        description="Comprehensive answer to the query based strictly on the provided GR context."
    )
    supporting_grs: List[SupportingGR] = Field(
        default_factory=list,
        description="List of GRs cited in the answer.",
    )
    confidence: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        return _clamp_confidence_value(v, default_on_none=0.7)


class ConflictPair(BaseModel):
    """Side-by-side draft clause and matching corpus language."""

    draft_clause: str
    corpus_excerpt: str
    gr_label: str
    gr_number_canonical: Optional[str] = None
    gr_number_original: Optional[str] = None
    gr_number_normalized: Optional[str] = None
    relevance_note: Optional[str] = None
    # Per-conflict structured English fields
    per_conflict_explanation: Optional[str] = None
    draft_proposes: Optional[str] = None
    existing_gr_provides: Optional[str] = None
    conflict_type: Optional[str] = None  # "override" | "overlap" | "inconsistency"
    recommendation: Optional[str] = None


class ConflictLLMOutput(BaseModel):
    """Fields the LLM is allowed to populate — architectural metadata added post-hoc."""

    conflicting: bool
    explanation: str
    conflicting_clauses: List[str] = Field(default_factory=list)
    affected_grs: List[SupportingGR] = Field(default_factory=list)
    cross_departmental: bool = False
    supersession_detected: bool = False
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        return _clamp_confidence_value(v, default_on_none=0.7)


class ConflictFinding(BaseModel):
    """
    Structured conflict and alignment report for a draft or query GR.
    """

    conflicting: bool = Field(
        description="True if a conflict, duplication, or superseding issue exists; False otherwise."
    )
    explanation: str = Field(
        description="Detailed explanation of the conflict or alignment findings."
    )
    conflicting_clauses: List[str] = Field(
        default_factory=list,
        description="List of specific conflicting clauses or policy rules.",
    )
    affected_grs: List[SupportingGR] = Field(
        default_factory=list,
        description="List of GRs involved in the conflict.",
    )
    cross_departmental: bool = Field(
        default=False,
        description="True when the conflict spans different government departments.",
    )
    supersession_detected: bool = Field(
        default=False,
        description="True when a newer GR supersedes or replaces language in an older GR.",
    )
    confidence: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )
    degraded: bool = Field(
        default=False,
        description="True when retrieval or store sync quality was reduced.",
    )
    degradation_reasons: List[str] = Field(
        default_factory=list,
        description="Client-visible warnings about degraded pipeline stages.",
    )
    retrieval_quality: Optional[RetrievalQualityInfo] = Field(
        default=None,
        description="Pre-LLM retrieval gate assessment.",
    )
    rule_signals: List[RuleSignal] = Field(
        default_factory=list,
        description="Deterministic rule-based overlap signals.",
    )
    draft_clauses_detected: List[str] = Field(
        default_factory=list,
        description="Operative clauses parsed from the draft for alignment.",
    )
    conflict_pairs: List[ConflictPair] = Field(
        default_factory=list,
        description="Draft clause paired with exact conflicting language from corpus GRs.",
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        return _clamp_confidence_value(v, default_on_none=0.7)


class ComparisonResult(BaseModel):
    """
    Structured clause-by-clause comparison result between two GRs.
    """

    summary: str = Field(
        description="High-level summary of differences between the two GRs."
    )
    added: List[str] = Field(
        default_factory=list,
        description="Clauses, rules, or provisions present in GR B but absent in GR A.",
    )
    removed: List[str] = Field(
        default_factory=list,
        description="Clauses, rules, or provisions present in GR A but absent in GR B.",
    )
    changed: List[str] = Field(
        default_factory=list,
        description="Provisions modified between GR A and GR B.",
    )
    contradictions: List[str] = Field(
        default_factory=list,
        description="Direct policy or legal contradictions between the GRs.",
    )
    confidence: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        return _clamp_confidence_value(v, default_on_none=0.7)
