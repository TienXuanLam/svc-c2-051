# PB-01 (domain): Custom S-2 pre-processing check boundary.
#
# Verifies the AccountSignalIngest custom pre-processing check blocks a case
# with a non-numeric/out-of-range/injection-attempt field before it can
# reach MainNode. Unlike other templates in this project line, this template's input schema
# has NO free-text field at all (docs/02_design.md "S-1/S-3 Detection
# Scope") — every field is strictly numeric, so strict numeric type + range
# validation on ingest IS the complete S-2 content check here; there is no
# field shape in which a company/contact name or contract value could be
# smuggled through without failing numeric validation outright.

import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from src.nodes.main_node import MainNode
from src.nodes.pre_process_node import PreProcessNode

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


def _invoke_pre_then_main(user_input: str) -> dict:
    # A single BaseNode.__call__() only returns that node's own partial
    # update + framework bookkeeping — it does NOT re-include unrelated
    # pre-existing fields (found on a prior fleet template: caller_trust_level was
    # silently dropped between two raw node.__call__() invocations). Merge
    # each node's result into a persistent running state ourselves to
    # correctly simulate the pipeline here without a compiled graph.
    full_state = {"user_input": user_input, "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value}
    pre = PreProcessNode()
    full_state.update(pre(full_state))
    if full_state.get("status") == AgentStatus.ERROR.value:
        return full_state  # AgentBaseGraph routes ERROR straight to finalize — main is skipped
    main = MainNode(
        dimension_weights=_DIMENSION_WEIGHTS,
        risk_thresholds=_RISK_THRESHOLDS,
        intervention_kb=_INTERVENTION_KB,
    )
    full_state.update(main(full_state))
    return full_state


def _case_payload(**overrides) -> str:
    payload = {
        "dau_wau_trend_pct": -10.0,
        "ticket_count": 3,
        "ticket_severity_avg": 2.0,
        "nps_score": 20.0,
        "contract_utilization_pct": 70.0,
        "days_to_renewal": 100,
    }
    payload.update(overrides)
    return json.dumps(payload)


class TestCustomContentRejectionBoundary:
    def test_injection_attempt_never_reaches_main_node(self):
        state = _invoke_pre_then_main(_case_payload(contract_utilization_pct="Acme Corp — $50,000"))
        assert state["status"] == AgentStatus.ERROR.value
        assert "report_draft" not in state
        assert "risk_tier" not in state

    def test_out_of_range_value_never_reaches_main_node(self):
        state = _invoke_pre_then_main(_case_payload(nps_score=500.0))
        assert state["status"] == AgentStatus.ERROR.value
        assert "report_draft" not in state

    def test_missing_field_never_reaches_main_node(self):
        payload = json.loads(_case_payload())
        del payload["days_to_renewal"]
        state = _invoke_pre_then_main(json.dumps(payload))
        assert state["status"] == AgentStatus.ERROR.value
        assert "report_draft" not in state

    def test_fractional_ticket_count_never_reaches_main_node(self):
        # eng-moderator T1-01/T2-01 (MEDIUM): a fractional discrete signal
        # (ticket_count: 3.9) must be rejected before scoring — proving
        # int(3.9) == 3 silent truncation is fixed through the same
        # pre_process -> main boundary this PB verifies for other
        # data-quality rejections, not just at the isolated service level.
        state = _invoke_pre_then_main(_case_payload(ticket_count=3.9))
        assert state["status"] == AgentStatus.ERROR.value
        assert "report_draft" not in state
        assert "risk_tier" not in state

    def test_fractional_days_to_renewal_never_reaches_main_node(self):
        state = _invoke_pre_then_main(_case_payload(days_to_renewal=60.5))
        assert state["status"] == AgentStatus.ERROR.value
        assert "report_draft" not in state

    def test_clean_case_reaches_main_node(self):
        state = _invoke_pre_then_main(_case_payload())
        assert state["status"] == AgentStatus.SUCCESS.value
        assert state["report_draft"]
