"""AgentCore Platform v1.0"""

# Step 3 — RiskClassify.
#
# Design Decision Record (docs/02_design.md): risk tier directly drives
# management reporting and intervention urgency — a business-critical
# decision. Per IMPLEMENTATION_LOG.md A4, decisions with material business
# consequence must be deterministic (no `llm` parameter anywhere in this
# module).
#
# dimension_weights and risk_thresholds are institution-configurable via
# config.yaml (proposal §10/§12: "dimension weighting is the key precision
# variable"). The risk-tier cut-points (Red<40/Yellow 40-65/Green>65) are
# taken directly from the proposal's own literal §4 table — not a
# fabricated citation, unlike the per-dimension scoring formula constants.

from __future__ import annotations

from typing import Any

from src.services.health_dimension_score_service import DIMENSION_NAMES

VALID_RISK_TIERS = ("Red", "Yellow", "Green")

DEFAULT_DIMENSION_WEIGHTS = {
    "product_adoption": 0.25,
    "support_health": 0.25,
    "relationship": 0.25,
    "commercial_risk": 0.25,
}
DEFAULT_RISK_THRESHOLDS = {"red_max": 40, "yellow_max": 65}


def compute_composite_score(dimension_scores: dict[str, Any], dimension_weights: dict[str, Any]) -> float:
    """Deterministic weighted average of the 4 dimension scores."""
    return float(sum(dimension_scores[name] * dimension_weights[name] for name in DIMENSION_NAMES))


def classify_risk_tier(composite_score: float, risk_thresholds: dict[str, Any]) -> str:
    """Deterministic composite-score-to-tier classification. No `llm`
    parameter — this signature is asserted by a PB test (A4 principle)."""
    if composite_score < risk_thresholds["red_max"]:
        return "Red"
    if composite_score < risk_thresholds["yellow_max"]:
        return "Yellow"
    return "Green"


def identify_weakest_dimension(dimension_scores: dict[str, Any]) -> str:
    """Deterministic — returns the name of the lowest-scoring dimension."""
    return min(DIMENSION_NAMES, key=lambda name: dimension_scores[name])
