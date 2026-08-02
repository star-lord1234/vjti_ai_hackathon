"""Rule-based GR template / structure compliance checker."""

from reasoning.template.checker import run_template_check
from reasoning.template.models import TemplateCheckSection, TemplateViolation

__all__ = [
    "TemplateCheckSection",
    "TemplateViolation",
    "run_template_check",
]
