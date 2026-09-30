# SVC-C2-051 — Unit Tests: risk_classify_service (step 3)

import inspect

from src.services.risk_classify_service import (
    DEFAULT_DIMENSION_WEIGHTS,
    DEFAULT_RISK_THRESHOLDS,
    classify_risk_tier,
    compute_composite_score,
    identify_weakest_dimension,
)

_SCORES = {
    "product_adoption": 70.0,
    "support_health": 76.0,
    "relationship": 60.0,
    "commercial_risk": 70.0,
}


class TestComputeCompositeScore:
    def test_equal_weights_average(self):
        score = compute_composite_score(_SCORES, DEFAULT_DIMENSION_WEIGHTS)
        assert score == (70.0 + 76.0 + 60.0 + 70.0) / 4

    def test_skewed_weights_favor_weighted_dimension(self):
        weights = {
            "product_adoption": 1.0,
            "support_health": 0.0,
            "relationship": 0.0,
            "commercial_risk": 0.0,
        }
        assert compute_composite_score(_SCORES, weights) == 70.0


class TestClassifyRiskTier:
    def test_below_red_max_is_red(self):
        assert classify_risk_tier(39.9, DEFAULT_RISK_THRESHOLDS) == "Red"

    def test_at_red_max_boundary_is_yellow(self):
        assert classify_risk_tier(40.0, DEFAULT_RISK_THRESHOLDS) == "Yellow"

    def test_between_thresholds_is_yellow(self):
        assert classify_risk_tier(50.0, DEFAULT_RISK_THRESHOLDS) == "Yellow"

    def test_at_yellow_max_boundary_is_green(self):
        assert classify_risk_tier(65.0, DEFAULT_RISK_THRESHOLDS) == "Green"

    def test_above_yellow_max_is_green(self):
        assert classify_risk_tier(90.0, DEFAULT_RISK_THRESHOLDS) == "Green"

    def test_no_llm_parameter(self):
        # IMPLEMENTATION_LOG.md A4: decisions with material business
        # consequence must be deterministic — no llm kwarg anywhere.
        params = list(inspect.signature(classify_risk_tier).parameters)
        assert "llm" not in params


class TestIdentifyWeakestDimension:
    def test_returns_lowest_scoring_dimension(self):
        assert identify_weakest_dimension(_SCORES) == "relationship"

    def test_tie_returns_first_in_dimension_order(self):
        tied = {
            "product_adoption": 50.0,
            "support_health": 50.0,
            "relationship": 90.0,
            "commercial_risk": 90.0,
        }
        assert identify_weakest_dimension(tied) == "product_adoption"

    def test_no_llm_parameter(self):
        params = list(inspect.signature(identify_weakest_dimension).parameters)
        assert "llm" not in params
