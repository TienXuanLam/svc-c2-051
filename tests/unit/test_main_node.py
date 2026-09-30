# SVC-C2-051 — Unit Tests: MainNode (steps 2-6: score, classify, narrate,
# recommend, assemble)
#
# Rewritten from the scaffold stub (IMPLEMENTATION_LOG.md A7) — the original
# stub tested a generic "process input" MainNode that no longer matches this
# template's real business logic.

import inspect

from framework.schemas.agent_status import AgentStatus
from src.nodes.main_node import MainNode

_DIMENSION_WEIGHTS = {
    "product_adoption": 0.25,
    "support_health": 0.25,
    "relationship": 0.25,
    "commercial_risk": 0.25,
}
_RISK_THRESHOLDS = {"red_max": 40, "yellow_max": 65}
_INTERVENTION_KB = {
    "kb_version": "TEST-1",
    "source": "test fixture",
    "provenance_verified": True,
    "recommendations": {
        f"{tier}:{dim}": f"{tier}/{dim} intervention text"
        for tier in ("Red", "Yellow", "Green")
        for dim in ("product_adoption", "support_health", "relationship", "commercial_risk")
    },
}


def _base_state(**overrides) -> dict:
    state = {
        "dau_wau_trend_pct": -10.0,
        "ticket_count": 3,
        "ticket_severity_avg": 2.0,
        "nps_score": 20.0,
        "contract_utilization_pct": 70.0,
        "days_to_renewal": 45,
    }
    state.update(overrides)
    return state


def _node(**kwargs) -> MainNode:
    defaults = dict(
        dimension_weights=_DIMENSION_WEIGHTS,
        risk_thresholds=_RISK_THRESHOLDS,
        intervention_kb=_INTERVENTION_KB,
    )
    defaults.update(kwargs)
    return MainNode(**defaults)


class TestMainNode:
    def setup_method(self):
        self.node = _node()

    def test_success_path_without_llm(self):
        result = self.node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["risk_tier"] in ("Red", "Yellow", "Green")
        assert "Root Cause Narrative" in result["root_cause_section"]
        assert "Recommended Intervention" in result["intervention_section"]
        assert "Account Health Report Draft" in result["report_draft"]

    def test_deterministic_classification_computed_from_signals(self):
        # Severe decline + heavy ticket load + negative NPS -> Red tier.
        result = self.node.execute(
            _base_state(
                dau_wau_trend_pct=-50.0,
                ticket_count=10,
                ticket_severity_avg=4.0,
                nps_score=-80.0,
                contract_utilization_pct=20.0,
            )
        )
        assert result["risk_tier"] == "Red"
        assert result["weakest_dimension"] in _DIMENSION_WEIGHTS

    def test_healthy_signals_classify_green(self):
        result = self.node.execute(
            _base_state(
                dau_wau_trend_pct=5.0,
                ticket_count=0,
                ticket_severity_avg=0.0,
                nps_score=80.0,
                contract_utilization_pct=90.0,
            )
        )
        assert result["risk_tier"] == "Green"

    def test_success_path_with_llm(self):
        class StubLLM:
            def complete(self, prompt):
                return "Stub LLM narrative text."

        node = _node(llm=StubLLM())
        result = node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "Stub LLM narrative text." in result["root_cause_section"]

    def test_report_never_contains_prohibited_content_even_with_leaking_llm(self):
        class LeakLLM:
            def complete(self, prompt):
                return "Contact John Smith who negotiated a $50,000 discount."

        node = _node(llm=LeakLLM())
        result = node.execute(_base_state())
        assert "John Smith" not in result["report_draft"]
        assert "$50,000" not in result["report_draft"]

    def test_missing_intervention_kb_entry_raises(self):
        from src.services.intervention_recommend_service import InterventionKbError

        sparse_kb = {
            "kb_version": "TEST-2",
            "source": "test fixture",
            "provenance_verified": True,
            "recommendations": {},
        }
        node = _node(intervention_kb=sparse_kb)
        try:
            node.execute(_base_state())
            raised = False
        except InterventionKbError:
            raised = True
        assert raised

    def test_execute_method_signature(self):
        sig = inspect.signature(MainNode.execute)
        params = list(sig.parameters.keys())
        assert len(params) >= 2
        assert params[1] == "state"
        assert "_invoke_impl" not in MainNode.__dict__
