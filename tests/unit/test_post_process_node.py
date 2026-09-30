# SVC-C2-051 — Unit Tests: PostProcessNode (step 7: OutputValidate — S-3
# primary defense re-scan + mandatory disclaimer)

import inspect
import json

from framework.schemas.agent_status import AgentStatus
from src.nodes.post_process_node import PostProcessNode


class TestPostProcessNodeExecute:
    def setup_method(self):
        self.node = PostProcessNode()

    def test_clean_report_attaches_disclaimer(self):
        state = {
            "report_draft": "# Account Health Report Draft\n\nClean content.",
            "risk_tier": "Yellow",
            "composite_score": 69.0,
        }
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["output_pii_violations"] == "[]"
        assert "AI DRAFT" in result["formatted_output"]["report_markdown"]
        assert result["formatted_output"]["risk_tier"] == "Yellow"
        assert result["formatted_output"]["composite_score"] == 69.0

    def test_leaked_name_blocks_release(self):
        state = {"report_draft": "Contact John Smith during the review."}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        violations = json.loads(result["output_pii_violations"])
        assert violations
        assert "formatted_output" not in result

    def test_leaked_money_blocks_release(self):
        state = {"report_draft": "Contract value is $50,000."}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value

    def test_execute_method_signature(self):
        sig = inspect.signature(PostProcessNode.execute)
        params = list(sig.parameters.keys())
        assert len(params) >= 2
        assert params[1] == "state"
        assert "_invoke_impl" not in PostProcessNode.__dict__


class TestPostProcessNodeOutputGateHook:
    def setup_method(self):
        self.node = PostProcessNode()

    def test_gate_hook_raises_on_leaked_content_in_formatted_output(self):
        result = {"formatted_output": {"report_markdown": "Penalty of ¥1,000,000 was assessed."}}
        try:
            self.node._extra_security_gate_output(result)
            raised = False
        except RuntimeError:
            raised = True
        assert raised

    def test_gate_hook_passes_clean_output(self):
        result = {"formatted_output": {"report_markdown": "Clean report content."}}
        assert self.node._extra_security_gate_output(result) == result
