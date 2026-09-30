"""AgentCore Platform v1.0"""

# ADR-005: State must be a flat TypedDict (see ADR-005 for the prohibited
# alternatives). LangGraph checkpoints use msgpack serialization, so only
# plain serializable fields are allowed. Do NOT add credentials or secrets.
#
# Node-count reconciliation: the proposal's Agent Workflow (§4) describes a
# 7-step pipeline, explicitly mapped in its own "AgentCore node-slot mapping"
# table to pre_process (1 step) / main (5 steps) / post_process (1 step) —
# see docs/02_design.md "Architecture Overview" for the full mapping.

from framework.schemas.agent_state import AgentState


class State(AgentState):
    """Agent state for CustomerSuccessRenewalRiskAssessmentAccountHealthReportAgent.

    No field ever holds a customer company name, contact name, or contract
    value — proposal §3/§10 S-1/S-3 requirement (see docs/02_design.md
    "S-1/S-3 Detection Scope"). All input fields are strictly numeric.
    """

    # Step 1 — AccountSignalIngest (parsed from user_input, a JSON string
    # with 6 numeric keys)
    dau_wau_trend_pct: float
    ticket_count: int
    ticket_severity_avg: float
    nps_score: float
    contract_utilization_pct: float
    days_to_renewal: int

    # Step 2 — HealthDimensionScore (deterministic weighted aggregation)
    product_adoption_score: float
    support_health_score: float
    relationship_score: float
    commercial_risk_score: float

    # Step 3 — RiskClassify (deterministic; see docs/02_design.md Design
    # Decision Record — risk tier is a business-critical decision and must
    # not be LLM-authoritative)
    composite_score: float
    risk_tier: str  # Red | Yellow | Green
    weakest_dimension: str  # product_adoption | support_health | relationship | commercial_risk

    # Step 4 — RootCauseNarrate
    root_cause_section: str

    # Step 5 — InterventionRecommend
    intervention_section: str

    # Step 6 — ReportDraft
    report_draft: str

    # Step 7 — OutputValidate (S-3: belt-and-suspenders re-scan, independent
    # of the input-side numeric-type validation)
    output_pii_violations: str  # JSON-encoded list[str] (ADR-005) — "[]" when clean
