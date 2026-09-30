"""AgentCore Platform v1.0"""

# main dispatcher — wraps step 2 (HealthDimensionScore), step 3
# (RiskClassify), step 4 (RootCauseNarrate), step 5 (InterventionRecommend),
# and step 6 (ReportDraft), per the proposal's own explicit
# "AgentCore node-slot mapping" table (docs/02_design.md
# "Architecture Overview").

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.health_dimension_score_service import score_all_dimensions
from src.services.intervention_recommend_service import lookup_intervention, present_intervention
from src.services.report_draft_service import DEFAULT_RENEWAL_WARNING_DAYS, assemble_report
from src.services.risk_classify_service import (
    classify_risk_tier,
    compute_composite_score,
    identify_weakest_dimension,
)
from src.services.root_cause_narrate_service import draft_root_cause_narrative


class MainNode(FunctionNode):
    """Step 2-6: score health dimensions, classify risk, narrate root
    cause, recommend intervention, assemble the full account health
    report."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(
        self,
        dimension_weights: dict[str, Any],
        risk_thresholds: dict[str, Any],
        intervention_kb: dict[str, Any],
        renewal_warning_days: tuple[int, int] = DEFAULT_RENEWAL_WARNING_DAYS,
        llm: Any = None,
    ) -> None:
        self._dimension_weights = dimension_weights
        self._risk_thresholds = risk_thresholds
        self._intervention_kb = intervention_kb
        self._renewal_warning_days = renewal_warning_days
        self._llm = llm

    def execute(self, state: AgentState) -> dict[str, Any]:
        dimension_scores = score_all_dimensions(
            dau_wau_trend_pct=state.get("dau_wau_trend_pct", 0.0),
            ticket_count=state.get("ticket_count", 0),
            ticket_severity_avg=state.get("ticket_severity_avg", 0.0),
            nps_score=state.get("nps_score", 0.0),
            contract_utilization_pct=state.get("contract_utilization_pct", 0.0),
        )
        emit_trace_event("health_scored", dimension_scores, state)

        composite_score = compute_composite_score(dimension_scores, self._dimension_weights)
        risk_tier = classify_risk_tier(composite_score, self._risk_thresholds)
        weakest_dimension = identify_weakest_dimension(dimension_scores)
        emit_trace_event(
            "risk_classified",
            {"composite_score": composite_score, "risk_tier": risk_tier, "weakest_dimension": weakest_dimension},
            state,
        )

        root_cause_section = draft_root_cause_narrative(
            dimension_scores=dimension_scores,
            risk_tier=risk_tier,
            weakest_dimension=weakest_dimension,
            dau_wau_trend_pct=state.get("dau_wau_trend_pct", 0.0),
            ticket_count=state.get("ticket_count", 0),
            ticket_severity_avg=state.get("ticket_severity_avg", 0.0),
            nps_score=state.get("nps_score", 0.0),
            contract_utilization_pct=state.get("contract_utilization_pct", 0.0),
            llm=self._llm,
        )
        if self._llm is not None:
            emit_trace_event("llm_call", {"step": "root_cause_narrate"}, state)

        intervention_text = lookup_intervention(self._intervention_kb, risk_tier, weakest_dimension)
        emit_trace_event(
            "intervention_looked_up",
            {
                "risk_tier": risk_tier,
                "weakest_dimension": weakest_dimension,
                "kb_version": self._intervention_kb.get("kb_version"),
            },
            state,
        )
        intervention_section = present_intervention(intervention_text, risk_tier, llm=self._llm)
        if self._llm is not None:
            emit_trace_event("llm_call", {"step": "intervention_recommend"}, state)

        report_draft = assemble_report(
            dimension_scores=dimension_scores,
            composite_score=composite_score,
            risk_tier=risk_tier,
            weakest_dimension=weakest_dimension,
            days_to_renewal=state.get("days_to_renewal", 0),
            root_cause_section=root_cause_section,
            intervention_section=intervention_section,
            renewal_warning_days=self._renewal_warning_days,
        )

        return {
            "product_adoption_score": dimension_scores["product_adoption"],
            "support_health_score": dimension_scores["support_health"],
            "relationship_score": dimension_scores["relationship"],
            "commercial_risk_score": dimension_scores["commercial_risk"],
            "composite_score": composite_score,
            "risk_tier": risk_tier,
            "weakest_dimension": weakest_dimension,
            "root_cause_section": root_cause_section,
            "intervention_section": intervention_section,
            "report_draft": report_draft,
            "status": AgentStatus.SUCCESS.value,
        }
