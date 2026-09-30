# PB-04 (domain): "No prohibited content" guarantee (proposal §3/§10 —
# customer company names, contact names, contract/penalty values). No
# LLM-generated section (root cause narrative, intervention presentation)
# may ship such content, regardless of what an adversarial/misbehaving LLM
# returns. Mirrors an established fleet advisory-only
# enforcement pattern — includes both a behavioral battery (adversarial LLM
# stubs) and a static scan of this template's own fallback template strings.

import ast
import pathlib

from src.services.report_draft_service import assemble_report
from src.services.risk_classify_service import (
    classify_risk_tier,
    compute_composite_score,
    identify_weakest_dimension,
)
from src.services.health_dimension_score_service import score_all_dimensions
from src.services.intervention_recommend_service import lookup_intervention, present_intervention
from src.services.root_cause_narrate_service import draft_root_cause_narrative

_WEIGHTS = {
    "product_adoption": 0.25,
    "support_health": 0.25,
    "relationship": 0.25,
    "commercial_risk": 0.25,
}
_THRESHOLDS = {"red_max": 40, "yellow_max": 65}
_KB = {
    "kb_version": "TEST-1",
    "source": "test fixture",
    "provenance_verified": True,
    "institution_scope_note": "",
    "recommendations": {
        f"{tier}:{dim}": f"{tier}/{dim} intervention text"
        for tier in ("Red", "Yellow", "Green")
        for dim in ("product_adoption", "support_health", "relationship", "commercial_risk")
    },
}


class _AdversarialLLM:
    def __init__(self, text: str):
        self._text = text

    def complete(self, prompt: str) -> str:
        return self._text


ADVERSARIAL_OUTPUTS = [
    "Contact John Smith regarding this account.",
    "Account: Acme Corp is the customer in question.",
    "The renewal contract is worth $50,000.",
    "The penalty was 50000 yen.",
    "担当者は山田太郎です。",
]


class TestAdvisoryOnlyBehavioral:
    def test_no_adversarial_llm_output_survives_into_assembled_report(self):
        dimension_scores = score_all_dimensions(-10.0, 3, 2.0, 20.0, 70.0)
        composite_score = compute_composite_score(dimension_scores, _WEIGHTS)
        risk_tier = classify_risk_tier(composite_score, _THRESHOLDS)
        weakest_dimension = identify_weakest_dimension(dimension_scores)

        for adversarial_text in ADVERSARIAL_OUTPUTS:
            llm = _AdversarialLLM(adversarial_text)
            root_cause_section = draft_root_cause_narrative(
                dimension_scores=dimension_scores,
                risk_tier=risk_tier,
                weakest_dimension=weakest_dimension,
                dau_wau_trend_pct=-10.0,
                ticket_count=3,
                ticket_severity_avg=2.0,
                nps_score=20.0,
                contract_utilization_pct=70.0,
                llm=llm,
            )
            intervention_text = lookup_intervention(_KB, risk_tier, weakest_dimension)
            intervention_section = present_intervention(intervention_text, risk_tier, llm=llm)

            report = assemble_report(
                dimension_scores=dimension_scores,
                composite_score=composite_score,
                risk_tier=risk_tier,
                weakest_dimension=weakest_dimension,
                days_to_renewal=45,
                root_cause_section=root_cause_section,
                intervention_section=intervention_section,
            )
            assert adversarial_text not in report, f"adversarial text leaked via '{adversarial_text}'"


class TestAdvisoryOnlyStaticScan:
    def test_fallback_templates_contain_no_hardcoded_prohibited_content(self):
        # Self-check: none of this template's own deterministic fallback
        # strings may themselves contain a name/money/Japanese pattern.
        from src.services.account_signal_ingest_service import (
            JAPANESE_SCRIPT_RE,
            MONEY_SYMBOL_RE,
            MONEY_WORD_RE,
            NAME_CUE_RE,
        )

        src_dir = pathlib.Path(__file__).parents[2] / "src" / "services"
        offenders = []
        for path in src_dir.glob("*.py"):
            if path.name == "account_signal_ingest_service.py":
                # Excluded: this module defines the detection patterns
                # themselves and its docstrings/comments reference example
                # matches — a self-reference, not a leak.
                continue
            source = path.read_text(encoding="utf-8")
            for node in ast.walk(ast.parse(source, filename=str(path))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    text = node.value
                    if (
                        NAME_CUE_RE.search(text)
                        or MONEY_SYMBOL_RE.search(text)
                        or MONEY_WORD_RE.search(text)
                        or JAPANESE_SCRIPT_RE.search(text)
                    ):
                        offenders.append(f"{path.name}:{node.lineno} contains prohibited-content-shaped text")
        assert offenders == [], "\n".join(offenders)
