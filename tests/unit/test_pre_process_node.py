# SVC-C2-051 — Unit Tests: PreProcessNode (step 1: AccountSignalIngest)

import inspect
import json

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from src.nodes.pre_process_node import PreProcessNode


def _valid_payload(**overrides) -> str:
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


class TestPreProcessNodeExecute:
    def setup_method(self):
        self.node = PreProcessNode()

    def test_success_path(self):
        state = {"user_input": _valid_payload()}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["ticket_count"] == 3
        assert result["days_to_renewal"] == 100

    def test_execute_method_signature(self):
        sig = inspect.signature(PreProcessNode.execute)
        params = list(sig.parameters.keys())
        assert len(params) >= 2
        assert params[1] == "state"
        assert "_invoke_impl" not in PreProcessNode.__dict__


class TestPreProcessNodeSecurityGate:
    def setup_method(self):
        self.node = PreProcessNode()

    def _call(self, user_input: str, trust=TrustLevel.VERIFIED_EXTERNAL):
        state = {"user_input": user_input, "caller_trust_level": trust.value}
        return self.node(state)  # via __call__ — exercises the full gate pipeline

    def test_trust_gate_denies_anonymous_caller(self):
        result = self._call(_valid_payload(), trust=TrustLevel.ANONYMOUS)
        assert result["status"] == AgentStatus.ERROR.value

    def test_rejects_malformed_json(self):
        result = self._call("not-json")
        assert result["status"] == AgentStatus.ERROR.value

    def test_rejects_missing_field(self):
        payload = json.loads(_valid_payload())
        del payload["nps_score"]
        result = self._call(json.dumps(payload))
        assert result["status"] == AgentStatus.ERROR.value

    def test_rejects_non_numeric_injection_attempt(self):
        result = self._call(_valid_payload(contract_utilization_pct="Acme Corp — $50,000"))
        assert result["status"] == AgentStatus.ERROR.value

    def test_rejects_out_of_range_value(self):
        result = self._call(_valid_payload(nps_score=500.0))
        assert result["status"] == AgentStatus.ERROR.value

    def test_accepts_clean_payload(self):
        result = self._call(_valid_payload())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "PreProcessNode" in result["node_history"]
