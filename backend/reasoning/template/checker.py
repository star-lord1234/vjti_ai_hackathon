"""
GR template structure compliance checker.

Scoring rule (for judges / documentation):
-----------------------------------------
Template accuracy is a weighted percentage over REQUIRED sections only.

For each required section with weight W:
  - 1.0 × W  if the section is found AND its character offset is strictly greater
             than every *found* required section listed earlier in the template order.
  - 0.5 × W  if the section is found but appears before a required section that
             should precede it (out-of-order / partial credit).
  - 0.0 × W  if the section is not found anywhere in the draft.

accuracy_score = (sum of credits / sum of required weights) × 100

Optional sections (e.g. वाचा) do not affect the score denominator. They can still
produce low-severity violations when present but misordered.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from parser.section_locator import SectionMatch, locate_section
from reasoning.findings import AnalysisFinding
from reasoning.template.models import (
    TemplateCheckSection,
    TemplateStructureConfig,
    TemplateViolation,
)

_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "gr_template_structure.json"


def _load_config() -> TemplateStructureConfig:
    raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return TemplateStructureConfig.model_validate(raw)


TEMPLATE_CONFIG: TemplateStructureConfig = _load_config()


def _anchor_snippet(text: str, offset: int, radius: int = 80) -> str:
    start = max(0, offset - radius)
    end = min(len(text), offset + radius)
    snippet = text[start:end].strip()
    return snippet if snippet else text[: min(120, len(text))].strip()


def _earlier_required_violation(
    spec_id: str,
    match: SectionMatch,
    sections,
    matches: Dict[str, SectionMatch],
) -> Optional[tuple[str, str]]:
    """Return (earlier_section_id, earlier_label) if current match is too early."""
    for earlier in sections:
        if earlier.id == spec_id:
            break
        if not earlier.required:
            continue
        earlier_match = matches.get(earlier.id)
        if earlier_match and match.char_offset < earlier_match.char_offset:
            return earlier.id, earlier.label
    return None


def _violation_to_finding(
    violation: TemplateViolation,
    *,
    idx: int,
    text: str,
    match: Optional[SectionMatch],
    expected_offset: Optional[int],
) -> AnalysisFinding:
    if violation.violation_type == "missing":
        anchor_offset = expected_offset if expected_offset is not None else 0
        matched = _anchor_snippet(text, anchor_offset)
        location = (
            f"Expected after line {violation.found_at_line}"
            if violation.found_at_line
            else "Expected in document structure"
        )
        recommendation = (
            f"Add the {violation.section_label} section at the expected position "
            f"in the GR structure."
        )
    else:
        matched = match.matched_text if match else ""
        location = f"Line {violation.found_at_line}" if violation.found_at_line else "Misordered"
        recommendation = (
            f"Move the {violation.section_label} section so it appears after "
            f"{violation.expected_after or 'the preceding required section'}."
        )

    return AnalysisFinding(
        id=f"tpl-{idx + 1}",
        severity=violation.severity,
        category="template",
        summary=violation.section_label,
        matched_text=matched,
        location=location,
        description=violation.description,
        analysis=violation.description,
        recommendation=recommendation,
        line_number=violation.found_at_line,
        char_offset=violation.char_offset or (match.char_offset if match else None),
        line_range=[
            violation.found_at_line or 0,
            violation.found_at_line or 0,
        ],
    )


def run_template_check(draft_text: str) -> TemplateCheckSection:
    text = draft_text.strip()
    required_sections = [s for s in TEMPLATE_CONFIG.sections if s.required]
    total_required = len(required_sections)
    required_weight = sum(s.weight for s in required_sections)

    if not text:
        violation = TemplateViolation(
            violation_type="missing",
            section_id="header_block",
            section_label="Header / document-type block",
            severity="high",
            description="Draft is empty — no GR structure detected.",
        )
        return TemplateCheckSection(
            accuracy_score=0.0,
            total_required_sections=total_required,
            sections_correct=0,
            sections_present=0,
            violations=[violation],
            findings=[_violation_to_finding(violation, idx=0, text="", match=None, expected_offset=0)],
        )

    sections = TEMPLATE_CONFIG.sections
    matches: Dict[str, SectionMatch] = {}
    for spec in sections:
        hit = locate_section(spec.id, text)
        if hit:
            matches[spec.id] = hit

    violations: List[TemplateViolation] = []
    credits = 0.0
    sections_correct = 0
    required_present = 0

    for spec in sections:
        match = matches.get(spec.id)

        if not match:
            if spec.required:
                prev_found = [
                    s for s in sections if s.id != spec.id and s.required and s.id in matches
                ]
                last_label = prev_found[-1].label if prev_found else None
                last_match = matches.get(prev_found[-1].id) if prev_found else None
                violations.append(
                    TemplateViolation(
                        violation_type="missing",
                        section_id=spec.id,
                        section_label=spec.label,
                        severity=spec.severity_missing,
                        description=(
                            f"Required section '{spec.label}' not found"
                            + (f" (expected after '{last_label}')." if last_label else ".")
                        ),
                        expected_after=last_label,
                        found_at_line=last_match.line_number if last_match else None,
                        char_offset=last_match.end_offset if last_match else 0,
                    )
                )
            continue

        ordering_issue = _earlier_required_violation(spec.id, match, sections, matches)
        if ordering_issue:
            _earlier_id, earlier_label = ordering_issue
            violations.append(
                TemplateViolation(
                    violation_type="misordered",
                    section_id=spec.id,
                    section_label=spec.label,
                    severity=spec.severity_misordered,
                    description=(
                        f"Section '{spec.label}' at line {match.line_number} appears "
                        f"before '{earlier_label}', which should precede it."
                    ),
                    expected_after=earlier_label,
                    found_at_line=match.line_number,
                    char_offset=match.char_offset,
                )
            )
            if spec.required:
                required_present += 1
                credits += 0.5 * spec.weight
            continue

        if spec.required:
            required_present += 1
            credits += 1.0 * spec.weight
            sections_correct += 1

    accuracy = (credits / required_weight * 100.0) if required_weight > 0 else 100.0

    findings: List[AnalysisFinding] = []
    for idx, violation in enumerate(violations):
        match = matches.get(violation.section_id)
        findings.append(
            _violation_to_finding(
                violation,
                idx=idx,
                text=text,
                match=match,
                expected_offset=violation.char_offset,
            )
        )

    return TemplateCheckSection(
        accuracy_score=round(accuracy, 1),
        total_required_sections=total_required,
        sections_correct=sections_correct,
        sections_present=required_present,
        violations=violations,
        findings=findings,
        section_positions={sid: m.char_offset for sid, m in matches.items()},
    )
