# SVC-C2-051 — Unit Tests: output_validate_service (step 7 — S-3 primary
# defense; see docs/02_design.md "S-1/S-3 Detection Scope")

from src.services.output_validate_service import (
    MANDATORY_DISCLAIMER,
    attach_disclaimer,
    find_prohibited_content_violations,
)


class TestFindProhibitedContentViolations:
    def test_clean_report_has_no_violations(self):
        report = (
            "# Account Health Report Draft\n\n"
            "## Health Scorecard\n\n"
            "- **Product Adoption:** 70/100\n"
            "- **Risk Tier:** Yellow\n\n"
            "## Renewal Outlook\n\n"
            "Renewal is in 45 days — within the 60-day immediate-action window.\n"
        )
        assert find_prohibited_content_violations(report) == []

    def test_leaked_contact_name_detected(self):
        report = "Contact John Smith about this account's renewal."
        violations = find_prohibited_content_violations(report)
        assert any("name" in v for v in violations)

    def test_leaked_account_labeled_name_detected(self):
        report = "Account: Acme Corp is showing signs of churn risk."
        violations = find_prohibited_content_violations(report)
        assert any("name" in v for v in violations)

    def test_leaked_money_symbol_detected(self):
        report = "The renewal contract is worth $50,000."
        violations = find_prohibited_content_violations(report)
        assert any("monetary" in v for v in violations)

    def test_leaked_money_word_detected(self):
        report = "The renewal contract is worth 50000 yen."
        violations = find_prohibited_content_violations(report)
        assert any("monetary" in v for v in violations)

    def test_leaked_japanese_detected(self):
        report = "担当者は山田太郎です。"
        violations = find_prohibited_content_violations(report)
        assert any("Japanese" in v for v in violations)

    def test_own_headings_not_false_positive(self):
        # Regression test for the "# Account Health Report Draft" /
        # "Account Health Report" self-collision found and fixed during
        # implementation (docs/02_design.md, IMPLEMENTATION_LOG.md A8 lesson).
        report = (
            "# Account Health Report Draft\n\n"
            "## Health Scorecard\n\n"
            "## Root Cause Narrative\n\n"
            "## Recommended Intervention\n\n"
            "## Renewal Outlook\n\n"
        )
        assert find_prohibited_content_violations(report) == []

    def test_domain_prose_words_not_false_flagged_without_separator(self):
        report = "The customer account is a company that values commercial relationships."
        assert find_prohibited_content_violations(report) == []


class TestAttachDisclaimer:
    def test_disclaimer_prepended(self):
        result = attach_disclaimer("# Report body")
        assert result.startswith(MANDATORY_DISCLAIMER)
        assert "# Report body" in result

    def test_disclaimer_mentions_ai_draft_and_verification(self):
        assert "AI DRAFT" in MANDATORY_DISCLAIMER
        assert "Customer Success Manager" in MANDATORY_DISCLAIMER
