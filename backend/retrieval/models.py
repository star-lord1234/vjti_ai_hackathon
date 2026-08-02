"""
Shared retrieval result types for hybrid vector + graph search.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GraphExpansionResult:
    """Outcome of Neo4j citation expansion."""

    nodes: Dict[int, Dict[str, int]] = field(default_factory=dict)
    skipped: bool = False  # True when hops=0 (vector-only mode)
    error: Optional[str] = None

    @property
    def degraded(self) -> bool:
        return self.error is not None


@dataclass
class HybridSearchMeta:
    """Metadata about how hybrid retrieval was performed."""

    graph_expanded: bool = False
    graph_skipped: bool = False
    graph_error: Optional[str] = None
    graph_degraded: bool = False
    graph_nodes_added: int = 0
    vector_seeds: int = 0
    total_results: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_expanded": self.graph_expanded,
            "graph_skipped": self.graph_skipped,
            "graph_error": self.graph_error,
            "graph_degraded": self.graph_degraded,
            "graph_nodes_added": self.graph_nodes_added,
            "vector_seeds": self.vector_seeds,
            "total_results": self.total_results,
        }
