"""AgentCore Platform v1.0"""

# post_process dispatcher — wraps step 7 (OutputValidate): S-3 prohibited-
# content re-scan (independent of the input-side numeric validation —
# defense in depth) + mandatory disclaimer attachment.

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.output_validate_service import attach_disclaimer, find_prohibited_content_violations


class PostProcessNode(FunctionNode):
    """Step 7: re-scan the assembled report for prohibited content; attach
    the mandatory disclaimer and produce the final formatted_output."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_output(self, result: dict[str, Any]) -> dict[str, Any]:
        # Independent, second re-scan at the gate boundary — defense in
        # depth on top of the execute()-level check below. May raise
        # (per S-3 hook contract) to block output entirely.
        formatted = result.get("formatted_output")
        if isinstance(formatted, dict):
            report_text = formatted.get("report_markdown", "")
            if find_prohibited_content_violations(report_text):
                raise RuntimeError("OutputValidate: S-3 gate re-scan found prohibited content in report_markdown")
        return result

    def execute(self, state: AgentState) -> dict[str, Any]:
        report_draft = state.get("report_draft", "")
        violations = find_prohibited_content_violations(report_draft)

        emit_trace_event(
            "output_content_scan",
            {"violation_count": len(violations)},
            state,
        )

        if violations:
            return {
                "output_pii_violations": json.dumps(violations),
                "status": AgentStatus.ERROR.value,
                "error_log": [f"OutputValidate: blocked release — {v}" for v in violations],
            }

        final_report = attach_disclaimer(report_draft)
        return {
            "output_pii_violations": "[]",
            "formatted_output": {
                "report_markdown": final_report,
                "risk_tier": state.get("risk_tier", ""),
                "composite_score": state.get("composite_score", 0.0),
            },
            "status": AgentStatus.SUCCESS.value,
        }
