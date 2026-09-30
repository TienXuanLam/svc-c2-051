"""AgentCore Platform v1.0"""

# Step 2 — HealthDimensionScore. Fully deterministic weighted arithmetic —
# no `llm` parameter anywhere in this module (IMPLEMENTATION_LOG.md A4:
# decisions with material business consequence must be deterministic).
#
# Formula provenance (docs/02_design.md Design Decision Record): these
# per-dimension formulas are illustrative, simple, and documented —
# Gainsight/Totango's exact proprietary scoring formulas are not public, so
# this template does not claim to reproduce them. Institutions should
# calibrate `config.yaml`'s `dimension_weights` (the compositing weights)
# to their own segment; the per-dimension formula constants below are
# internal implementation detail, not separately configurable.

from __future__ import annotations

DIMENSION_NAMES = ("product_adoption", "support_health", "relationship", "commercial_risk")


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def score_product_adoption(dau_wau_trend_pct: float) -> float:
    """Flat or growing usage (trend >= 0) scores 100; each 1 percentage
    point of decline costs 3 points."""
    if dau_wau_trend_pct >= 0:
        return 100.0
    return _clamp(100.0 + dau_wau_trend_pct * 3)


def score_support_health(ticket_count: int, ticket_severity_avg: float) -> float:
    """Baseline 100, penalized by ticket volume weighted by average severity."""
    penalty = ticket_count * ticket_severity_avg * 4
    return _clamp(100.0 - penalty)


def score_relationship(nps_score: float) -> float:
    """Rescales NPS (-100..100) to a 0-100 health score."""
    return _clamp((nps_score + 100.0) / 2.0)


def score_commercial_risk(contract_utilization_pct: float) -> float:
    """Higher utilization is healthier (lower churn/downsell risk); the
    percentage itself is already a 0-100 score."""
    return _clamp(contract_utilization_pct)


def score_all_dimensions(
    dau_wau_trend_pct: float,
    ticket_count: int,
    ticket_severity_avg: float,
    nps_score: float,
    contract_utilization_pct: float,
) -> dict[str, float]:
    """Convenience wrapper — returns all 4 dimension scores keyed by name."""
    return {
        "product_adoption": score_product_adoption(dau_wau_trend_pct),
        "support_health": score_support_health(ticket_count, ticket_severity_avg),
        "relationship": score_relationship(nps_score),
        "commercial_risk": score_commercial_risk(contract_utilization_pct),
    }
