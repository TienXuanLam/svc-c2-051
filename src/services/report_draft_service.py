"""AgentCore Platform v1.0"""

# Step 6 — ReportDraft. Deterministic Markdown assembly of the health
# scorecard, risk narrative, recommended actions, and renewal outlook. No
# customer company name, contact name, or contract value appears here —
# only the caller-supplied numeric signals and derived scores.

from __future__ import annotations

from typing import Any

DEFAULT_RENEWAL_WARNING_DAYS = (60, 90)


def renewal_outlook(days_to_renewal: int, renewal_warning_days: tuple[int, int] = DEFAULT_RENEWAL_WARNING_DAYS) -> str:
    """Deterministic renewal-urgency framing (proposal §9: "structured risk
    detection 60-90 days before renewal creates intervention lead time").
    renewal_warning_days is institution-configurable via config.yaml."""
    immediate_window, approaching_window = sorted(renewal_warning_days)
    if days_to_renewal <= immediate_window:
        return (
            f"Renewal is in {days_to_renewal} days — within the {immediate_window}-day "
            "immediate-action window. Intervention should begin now."
        )
    if days_to_renewal <= approaching_window:
        return (
            f"Renewal is in {days_to_renewal} days — within the {approaching_window}-day "
            "early-warning window. Begin planning intervention activities."
        )
    return f"Renewal is in {days_to_renewal} days — outside the current early-warning window."


def assemble_report(
    dimension_scores: dict[str, Any],
    composite_score: float,
    risk_tier: str,
    weakest_dimension: str,
    days_to_renewal: int,
    root_cause_section: str,
    intervention_section: str,
    renewal_warning_days: tuple[int, int] = DEFAULT_RENEWAL_WARNING_DAYS,
) -> str:
    return (
        "# Account Health Report Draft\n\n"
        "## Health Scorecard\n\n"
        f"- **Product Adoption:** {dimension_scores['product_adoption']:.0f}/100\n"
        f"- **Support Health:** {dimension_scores['support_health']:.0f}/100\n"
        f"- **Relationship:** {dimension_scores['relationship']:.0f}/100\n"
        f"- **Commercial Risk:** {dimension_scores['commercial_risk']:.0f}/100\n"
        f"- **Composite Score:** {composite_score:.0f}/100\n"
        f"- **Risk Tier:** {risk_tier}\n"
        f"- **Weakest Dimension:** {weakest_dimension.replace('_', ' ').title()}\n\n"
        f"{root_cause_section}\n\n"
        f"{intervention_section}\n\n"
        "## Renewal Outlook\n\n"
        f"{renewal_outlook(days_to_renewal, renewal_warning_days)}\n"
    )
