# PB-03 (domain): Deterministic-vs-LLM authority boundary
# (IMPLEMENTATION_LOG.md A4 / docs/02_design.md Design Decision Record).
#
# Risk-tier classification and compositing must never accept an `llm`
# parameter — confirmed here by inspecting the function signatures directly,
# not just by behavioral testing (a future edit could add an `llm` param
# without changing observed behavior in a small test matrix).

import inspect

from src.services.health_dimension_score_service import score_all_dimensions
from src.services.risk_classify_service import (
    classify_risk_tier,
    compute_composite_score,
    identify_weakest_dimension,
)

_WEIGHTS = {
    "product_adoption": 0.25,
    "support_health": 0.25,
    "relationship": 0.25,
    "commercial_risk": 0.25,
}
_THRESHOLDS = {"red_max": 40, "yellow_max": 65}


class TestDeterministicAuthorityBoundary:
    def test_score_all_dimensions_has_no_llm_parameter(self):
        assert "llm" not in inspect.signature(score_all_dimensions).parameters

    def test_compute_composite_score_has_no_llm_parameter(self):
        assert "llm" not in inspect.signature(compute_composite_score).parameters

    def test_classify_risk_tier_has_no_llm_parameter(self):
        assert "llm" not in inspect.signature(classify_risk_tier).parameters

    def test_identify_weakest_dimension_has_no_llm_parameter(self):
        assert "llm" not in inspect.signature(identify_weakest_dimension).parameters

    def test_classification_pipeline_is_pure_deterministic(self):
        scores = score_all_dimensions(-10.0, 3, 2.0, 20.0, 70.0)
        composite_a = compute_composite_score(scores, _WEIGHTS)
        composite_b = compute_composite_score(scores, _WEIGHTS)
        assert composite_a == composite_b
        assert classify_risk_tier(composite_a, _THRESHOLDS) == classify_risk_tier(composite_b, _THRESHOLDS)
        assert identify_weakest_dimension(scores) == identify_weakest_dimension(scores)
