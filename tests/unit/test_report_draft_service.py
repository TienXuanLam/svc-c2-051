# SVC-C2-051 — Unit Tests: report_draft_service (step 6)

from src.services.report_draft_service import assemble_report, renewal_outlook

_SCORES = {
    "product_adoption": 70.0,
    "support_health": 76.0,
    "relationship": 60.0,
    "commercial_risk": 70.0,
}


class TestRenewalOutlook:
    def test_within_immediate_window(self):
        text = renewal_outlook(30, renewal_warning_days=(60, 90))
        assert "immediate-action window" in text

    def test_at_immediate_boundary(self):
        text = renewal_outlook(60, renewal_warning_days=(60, 90))
        assert "immediate-action window" in text

    def test_within_early_warning_window(self):
        text = renewal_outlook(75, renewal_warning_days=(60, 90))
        assert "early-warning window. Begin planning" in text

    def test_outside_warning_window(self):
        text = renewal_outlook(200, renewal_warning_days=(60, 90))
        assert "outside the current early-warning window" in text

    def test_unsorted_window_tuple_is_handled(self):
        text = renewal_outlook(30, renewal_warning_days=(90, 60))
        assert "immediate-action window" in text


class TestAssembleReport:
    def test_report_contains_all_sections(self):
        report = assemble_report(
            dimension_scores=_SCORES,
            composite_score=69.0,
            risk_tier="Yellow",
            weakest_dimension="relationship",
            days_to_renewal=45,
            root_cause_section="## Root Cause Narrative\n\nBody.",
            intervention_section="## Recommended Intervention\n\nBody.",
        )
        assert "# Account Health Report Draft" in report
        assert "## Health Scorecard" in report
        assert "Relationship" in report
        assert "## Root Cause Narrative" in report
        assert "## Recommended Intervention" in report
        assert "## Renewal Outlook" in report
        assert "Yellow" in report

    def test_weakest_dimension_is_title_cased_with_spaces(self):
        report = assemble_report(
            dimension_scores=_SCORES,
            composite_score=69.0,
            risk_tier="Yellow",
            weakest_dimension="product_adoption",
            days_to_renewal=45,
            root_cause_section="",
            intervention_section="",
        )
        assert "Product Adoption" in report

    def test_no_customer_identifying_content(self):
        report = assemble_report(
            dimension_scores=_SCORES,
            composite_score=69.0,
            risk_tier="Yellow",
            weakest_dimension="relationship",
            days_to_renewal=45,
            root_cause_section="",
            intervention_section="",
        )
        assert "$" not in report
