# SVC-C2-051 — Unit Tests: health_dimension_score_service (step 2)

from src.services.health_dimension_score_service import (
    score_all_dimensions,
    score_commercial_risk,
    score_product_adoption,
    score_relationship,
    score_support_health,
)


class TestScoreProductAdoption:
    def test_flat_usage_scores_full(self):
        assert score_product_adoption(0.0) == 100.0

    def test_growing_usage_scores_full(self):
        assert score_product_adoption(15.0) == 100.0

    def test_declining_usage_penalized(self):
        assert score_product_adoption(-10.0) == 70.0

    def test_clamped_at_zero_for_severe_decline(self):
        assert score_product_adoption(-100.0) == 0.0


class TestScoreSupportHealth:
    def test_no_tickets_scores_full(self):
        assert score_support_health(0, 0.0) == 100.0

    def test_tickets_with_severity_penalized(self):
        assert score_support_health(3, 2.0) == 76.0

    def test_clamped_at_zero_for_heavy_load(self):
        assert score_support_health(100, 5.0) == 0.0


class TestScoreRelationship:
    def test_neutral_nps_scores_midpoint(self):
        assert score_relationship(0.0) == 50.0

    def test_max_nps_scores_full(self):
        assert score_relationship(100.0) == 100.0

    def test_min_nps_scores_zero(self):
        assert score_relationship(-100.0) == 0.0


class TestScoreCommercialRisk:
    def test_full_utilization_scores_full(self):
        assert score_commercial_risk(100.0) == 100.0

    def test_zero_utilization_scores_zero(self):
        assert score_commercial_risk(0.0) == 0.0

    def test_out_of_range_input_is_clamped(self):
        assert score_commercial_risk(150.0) == 100.0


class TestScoreAllDimensions:
    def test_returns_all_four_dimensions(self):
        scores = score_all_dimensions(
            dau_wau_trend_pct=-10.0,
            ticket_count=3,
            ticket_severity_avg=2.0,
            nps_score=20.0,
            contract_utilization_pct=70.0,
        )
        assert set(scores.keys()) == {
            "product_adoption",
            "support_health",
            "relationship",
            "commercial_risk",
        }
        assert scores["product_adoption"] == 70.0
        assert scores["commercial_risk"] == 70.0
