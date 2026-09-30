"""AgentCore Platform v1.0"""

# pre_process dispatcher — wraps step 1 (AccountSignalIngest) only, per the
# proposal's own explicit "AgentCore node-slot mapping" table
# (docs/02_design.md "Architecture Overview").

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.account_signal_ingest_service import parse_account_signals


class PreProcessNode(FunctionNode):
    """Step 1: parse and validate account signals."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_input(self, state: AgentState) -> AgentState:
        # S-2 custom pre-processing check (proposal §3/§10, labeled "S-1" in
        # the proposal — see docs/02_design.md "S-1/S-3 Detection Scope"):
        # reject missing/non-numeric/out-of-range signal fields. Separate
        # from, and in addition to, the platform S-1 normalizer. Must not
        # raise — surface rejection via state["status"].
        state = dict(state)
        raw = state.get("user_input", "")
        _signals, error = parse_account_signals(raw)
        if error:
            state["status"] = AgentStatus.ERROR.value
            state["error_log"] = [error]
        return state

    def execute(self, state: AgentState) -> dict[str, Any]:
        signals, error = parse_account_signals(state.get("user_input", ""))
        if error or signals is None:
            # Defense in depth: the gate hook above already rejects invalid
            # input, so this path is unreachable in normal operation.
            return {"status": AgentStatus.ERROR.value, "error_log": [error]}

        emit_trace_event(
            "account_signals_ingested",
            {"ticket_count": signals["ticket_count"], "days_to_renewal": signals["days_to_renewal"]},
            state,
        )

        return {
            **signals,
            "status": AgentStatus.SUCCESS.value,
        }
