# SVC-C2-051 — Unit Tests: root_cause_narrate_service (step 4)

from src.services.root_cause_narrate_service import draft_root_cause_narrative

_SCORES = {
    "product_adoption": 70.0,
    "support_health": 76.0,
    "relationship": 60.0,
    "commercial_risk": 70.0,
}
_KWARGS = dict(
    dimension_scores=_SCORES,
    risk_tier="Yellow",
    weakest_dimension="relationship",
    dau_wau_trend_pct=-10.0,
    ticket_count=3,
    ticket_severity_avg=2.0,
    nps_score=20.0,
    contract_utilization_pct=70.0,
)


class TestDraftRootCauseNarrative:
    def test_fallback_used_when_no_llm(self):
        text = draft_root_cause_narrative(**_KWARGS)
        assert "Root Cause Narrative" in text
        assert "Yellow" in text
        assert "relationship" in text
        # Proposal §11 Risk #1 mitigation: fallback must cite actual input signals.
        assert "-10.0%" in text
        assert "3 tickets" in text
        assert "NPS +20" in text

    def test_llm_output_used_when_clean(self):
        class StubLLM:
            def complete(self, prompt):
                return "Clean LLM-generated root cause narrative."

        text = draft_root_cause_narrative(**_KWARGS, llm=StubLLM())
        assert text == "Clean LLM-generated root cause narrative."

    def test_llm_output_discarded_on_leaked_name(self):
        class LeakLLM:
            def complete(self, prompt):
                return "Contact John Smith regarding this account."

        text = draft_root_cause_narrative(**_KWARGS, llm=LeakLLM())
        assert "John Smith" not in text
        assert "Root Cause Narrative" in text  # fell back

    def test_llm_output_discarded_on_leaked_money(self):
        class LeakLLM:
            def complete(self, prompt):
                return "The contract is worth $50,000."

        text = draft_root_cause_narrative(**_KWARGS, llm=LeakLLM())
        assert "$50,000" not in text
        assert "Root Cause Narrative" in text

    def test_llm_exception_falls_back_safely(self):
        class BrokenLLM:
            def complete(self, prompt):
                raise RuntimeError("LLM unavailable")

        text = draft_root_cause_narrative(**_KWARGS, llm=BrokenLLM())
        assert "Root Cause Narrative" in text

    def test_llm_empty_output_falls_back(self):
        class EmptyLLM:
            def complete(self, prompt):
                return ""

        text = draft_root_cause_narrative(**_KWARGS, llm=EmptyLLM())
        assert "Root Cause Narrative" in text
