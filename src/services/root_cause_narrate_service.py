"""AgentCore Platform v1.0"""

# Step 4 — RootCauseNarrate. Narrative generation (not a legal/financial
# decision) — LLM is appropriate here, with a deterministic fallback
# template when no LLM is configured (IMPLEMENTATION_LOG.md B5 pattern).
# Any LLM output containing a detected company/contact name or monetary
# value is discarded fail-safe (mirrors an established fleet prohibited-
# content filter pattern). The fallback explicitly cites the actual input signal
# values (proposal §11 Risk #1 mitigation: "prompt design that explicitly
# cites input signal values").

from __future__ import annotations

from typing import Any

from src.services.account_signal_ingest_service import contains_disallowed_content_helper


def draft_root_cause_narrative(
    dimension_scores: dict[str, Any],
    risk_tier: str,
    weakest_dimension: str,
    dau_wau_trend_pct: float,
    ticket_count: int,
    ticket_severity_avg: float,
    nps_score: float,
    contract_utilization_pct: float,
    llm: Any = None,
) -> str:
    fallback = (
        "## Root Cause Narrative\n\n"
        f"**Overall Risk Tier:** {risk_tier} (composite score reflects the four "
        f"dimensions below; weakest dimension: {weakest_dimension.replace('_', ' ')}).\n\n"
        "**Primary Drivers:**\n"
        f"- Product Adoption ({dimension_scores['product_adoption']:.0f}/100): usage trend {dau_wau_trend_pct:+.1f}%.\n"
        f"- Support Health ({dimension_scores['support_health']:.0f}/100): {ticket_count} tickets, "
        f"average severity {ticket_severity_avg:.1f}/5.\n"
        f"- Relationship ({dimension_scores['relationship']:.0f}/100): NPS {nps_score:+.0f}.\n"
        f"- Commercial Risk ({dimension_scores['commercial_risk']:.0f}/100): "
        f"{contract_utilization_pct:.0f}% contract utilization.\n\n"
        "**Contributing Signals:** Reviewers should cross-reference these signals "
        "against source-system detail (CRM, support ticketing, survey tooling) "
        "before finalizing this assessment.\n"
    )
    if llm is None:
        return fallback

    prompt = (
        "Draft the 'Root Cause Narrative' section of a Customer Success account "
        "health report. Explicitly cite the input signal values given below. Do "
        "not mention any customer company name, contact name, or contract/dollar "
        "amount — this report must exclude all such content.\n\n"
        f"Risk tier: {risk_tier}\n"
        f"Weakest dimension: {weakest_dimension}\n"
        f"Dimension scores: {dimension_scores}\n"
        f"dau_wau_trend_pct: {dau_wau_trend_pct}\n"
        f"ticket_count: {ticket_count}\n"
        f"ticket_severity_avg: {ticket_severity_avg}\n"
        f"nps_score: {nps_score}\n"
        f"contract_utilization_pct: {contract_utilization_pct}\n"
    )
    try:
        text = llm.complete(prompt)
    except Exception:
        return fallback

    if not text or contains_disallowed_content_helper(text):
        # Fail-safe: discard LLM output entirely rather than risk shipping
        # a leaked company/contact name or monetary value.
        return fallback
    return str(text)
