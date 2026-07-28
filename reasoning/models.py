"""
Pydantic response models for structured LLM reasoning and RAG answers.
"""

from __future__ import annotations

from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator


class SupportingGR(BaseModel):
    """
    Reference to a supporting or cited Government Resolution.
    """

    label: str = Field(
        description="GR label from context, e.g. '[GR 1]'"
    )
    gr_number_canonical: Optional[str] = Field(
        default=None,
        description="Canonical GR number if available",
    )
    relevance_note: Optional[str] = Field(
        default=None,
        description="Brief note on why this GR supports or relates to the claim",
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
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        if v is None:
            return 1.0
        try:
            val = float(str(v).replace("%", "").strip())
            if val > 1.0 and val <= 100.0:
                val = val / 100.0
            return max(0.0, min(1.0, val))
        except Exception:
            return 1.0


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
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        if v is None:
            return 1.0
        try:
            val = float(str(v).replace("%", "").strip())
            if val > 1.0 and val <= 100.0:
                val = val / 100.0
            return max(0.0, min(1.0, val))
        except Exception:
            return 1.0


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
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        if v is None:
            return 1.0
        try:
            val = float(str(v).replace("%", "").strip())
            if val > 1.0 and val <= 100.0:
                val = val / 100.0
            return max(0.0, min(1.0, val))
        except Exception:
            return 1.0
