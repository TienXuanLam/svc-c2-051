"""AgentCore Platform v1.0"""

# Cat 2 — 7-step account health report pipeline reconciled into the fixed
# 3-slot AgentBaseGraph backbone, following the proposal's own explicit
# "AgentCore node-slot mapping" table (docs/02_design.md
# "Architecture Overview"). No add_edges() override — the default
# START -> initialize -> pre_process -> main -> {route} -> post_process -> finalize -> END
# pipeline is correct for this template (no HITL, no non-standard routing).

from pathlib import Path

from framework.graph.agent_base_graph import AgentBaseGraph

from src.nodes.main_node import MainNode
from src.nodes.post_process_node import PostProcessNode
from src.nodes.pre_process_node import PreProcessNode
from src.schemas.state import State
from src.services.intervention_recommend_service import load_intervention_kb
from src.services.report_draft_service import DEFAULT_RENEWAL_WARNING_DAYS
from src.services.risk_classify_service import DEFAULT_DIMENSION_WEIGHTS, DEFAULT_RISK_THRESHOLDS

# Default intervention KB shipped with the template — an
# institution overrides this via config.yaml's intervention_kb_path (a
# prior fleet review lesson, applied proactively here from the start: sanction/
# intervention policy content must be institution-configurable, not
# hardcoded). Lives under src/services/kb/, not a top-level kb/ directory —
# per the framework's file-layout contract: new files always go into the
# matching subdirectory, never outside this structure.
_DEFAULT_INTERVENTION_KB_PATH = Path(__file__).resolve().parents[1] / "services" / "kb" / "intervention_matrix.json"


class CustomerSuccessRenewalRiskAssessmentAccountHealthReportAgent(AgentBaseGraph):
    """Generates account health reports and renewal risk assessments from
    anonymized Customer Success signal data."""

    @property
    def name(self) -> str:
        return "CustomerSuccessRenewalRiskAssessmentAccountHealthReportAgent"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects InitializeNode + FinalizeNode

        # llm is optional — every drafting step has a deterministic fallback
        # (IMPLEMENTATION_LOG.md B5 pattern). A6 wiring checklist: MainNode
        # takes llm; verify it is wired here whenever a new dependency is
        # added to its constructor.
        llm = self.config.get("llm")

        # Institution-configurable scoring/classification (proposal §10/§12:
        # "dimension weighting is the key precision variable"). Validated at
        # construction time (fail-loud, not fail-open) so a misconfigured
        # config.yaml fails agent.compile() rather than degrading silently
        # at invoke time.
        dimension_weights = self.config.get("dimension_weights", DEFAULT_DIMENSION_WEIGHTS)
        required_dims = {"product_adoption", "support_health", "relationship", "commercial_risk"}
        missing_dims = required_dims - set(dimension_weights)
        if missing_dims:
            raise ValueError(
                f"config.yaml's dimension_weights is missing required dimension(s): {missing_dims}. "
                "See docs/07_operation_guide.md 'Health Scoring Setup'."
            )
        weight_sum = sum(dimension_weights.values())
        if abs(weight_sum - 1.0) > 1e-6:
            raise ValueError(
                f"config.yaml's dimension_weights must sum to 1.0, got {weight_sum}. "
                "See docs/07_operation_guide.md 'Health Scoring Setup'."
            )

        risk_thresholds = self.config.get("risk_thresholds", DEFAULT_RISK_THRESHOLDS)
        missing_thresholds = [key for key in ("red_max", "yellow_max") if key not in risk_thresholds]
        if missing_thresholds:
            raise ValueError(
                f"config.yaml's risk_thresholds is missing required key(s): {missing_thresholds}. "
                "See docs/07_operation_guide.md 'Health Scoring Setup'."
            )

        renewal_warning_days = self.config.get("renewal_warning_days", DEFAULT_RENEWAL_WARNING_DAYS)

        # Fail-closed (mirrors a prior fleet review finding): a misconfigured
        # intervention_kb_path raises InterventionKbError here, at agent
        # construction/compile() time.
        intervention_kb_path = self.config.get("intervention_kb_path", str(_DEFAULT_INTERVENTION_KB_PATH))
        intervention_kb = load_intervention_kb(intervention_kb_path)

        self._nodes["pre_process"] = PreProcessNode()
        self._nodes["main"] = MainNode(
            dimension_weights=dimension_weights,
            risk_thresholds=risk_thresholds,
            intervention_kb=intervention_kb,
            renewal_warning_days=renewal_warning_days,
            llm=llm,
        )
        self._nodes["post_process"] = PostProcessNode()
