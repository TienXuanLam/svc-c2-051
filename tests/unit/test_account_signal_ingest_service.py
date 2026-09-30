# SVC-C2-051 — Unit Tests: account_signal_ingest_service (step 1 — S-2 input
# content check: strict numeric type + range validation)

import json

from src.services.account_signal_ingest_service import (
    NAME_CUE_RE,
    contains_disallowed_content_helper,
    parse_account_signals,
)


def _valid_payload(**overrides) -> str:
    payload = {
        "dau_wau_trend_pct": -10.0,
        "ticket_count": 3,
        "ticket_severity_avg": 2.0,
        "nps_score": 20.0,
        "contract_utilization_pct": 70.0,
        "days_to_renewal": 100,
    }
    payload.update(overrides)
    return json.dumps(payload)


class TestParseAccountSignals:
    def test_valid_payload_parses(self):
        signals, error = parse_account_signals(_valid_payload())
        assert error is None
        assert signals["ticket_count"] == 3
        assert signals["days_to_renewal"] == 100

    def test_empty_input_rejected(self):
        signals, error = parse_account_signals("")
        assert signals is None
        assert "empty" in error

    def test_malformed_json_rejected(self):
        signals, error = parse_account_signals("not-json")
        assert signals is None
        assert "not valid JSON" in error

    def test_non_object_json_rejected(self):
        signals, error = parse_account_signals("[1, 2, 3]")
        assert signals is None
        assert "must be an object" in error

    def test_missing_field_rejected(self):
        payload = json.loads(_valid_payload())
        del payload["nps_score"]
        signals, error = parse_account_signals(json.dumps(payload))
        assert signals is None
        assert "nps_score" in error

    def test_non_numeric_field_rejected(self):
        signals, error = parse_account_signals(_valid_payload(nps_score="high"))
        assert signals is None
        assert "must be numeric" in error

    def test_bool_field_rejected_as_non_numeric(self):
        # isinstance(True, int) is True in Python — bool must be explicitly
        # excluded so a caller cannot smuggle a non-numeric field through.
        signals, error = parse_account_signals(_valid_payload(ticket_count=True))
        assert signals is None
        assert "must be numeric" in error

    def test_out_of_range_field_rejected(self):
        signals, error = parse_account_signals(_valid_payload(nps_score=150.0))
        assert signals is None
        assert "between" in error

    def test_negative_ticket_count_rejected(self):
        signals, error = parse_account_signals(_valid_payload(ticket_count=-1))
        assert signals is None
        assert "between" in error

    def test_fractional_ticket_count_rejected(self):
        # eng-moderator T1-01 (MEDIUM): int(3.9) == 3 previously truncated a
        # fractional ticket_count silently instead of rejecting it, changing
        # the evidence used for risk classification without surfacing an error.
        signals, error = parse_account_signals(_valid_payload(ticket_count=3.9))
        assert signals is None
        assert "ticket_count" in error
        assert "fractional" in error

    def test_fractional_days_to_renewal_rejected(self):
        signals, error = parse_account_signals(_valid_payload(days_to_renewal=60.5))
        assert signals is None
        assert "days_to_renewal" in error
        assert "fractional" in error

    def test_whole_number_float_ticket_count_accepted(self):
        # A float that represents a whole number (e.g. 3.0) is not a
        # fractional value — it must still be accepted and coerced to int.
        signals, error = parse_account_signals(_valid_payload(ticket_count=3.0))
        assert error is None
        assert signals["ticket_count"] == 3

    def test_whole_number_float_days_to_renewal_accepted(self):
        signals, error = parse_account_signals(_valid_payload(days_to_renewal=100.0))
        assert error is None
        assert signals["days_to_renewal"] == 100

    def test_string_injection_attempt_rejected(self):
        # A caller attempting to smuggle a company/contact name or contract
        # value through a numeric field fails type validation outright
        # (docs/02_design.md "S-1/S-3 Detection Scope").
        signals, error = parse_account_signals(
            _valid_payload(contract_utilization_pct="Acme Corp — $50,000 contract")
        )
        assert signals is None
        assert "must be numeric" in error


class TestContainsDisallowedContentHelper:
    def test_empty_text_is_clean(self):
        assert contains_disallowed_content_helper("") is False

    def test_clean_narrative_text_is_clean(self):
        text = "Support Health (62/100): 3 tickets, average severity 2.0/5."
        assert contains_disallowed_content_helper(text) is False

    def test_cued_name_detected(self):
        assert contains_disallowed_content_helper("Contact John Smith about renewal.") is True

    def test_account_labeled_name_detected(self):
        assert contains_disallowed_content_helper("Account: Acme Corp is at risk.") is True

    def test_bare_account_word_not_false_flagged(self):
        # Regression guard for the "Account Health Report" self-collision
        # bug fixed during implementation — a bare domain word without a
        # mandatory colon/dash separator must not match.
        assert NAME_CUE_RE.search("Account Health Report Draft") is None
        assert contains_disallowed_content_helper("The account health report is ready.") is False

    def test_monetary_symbol_detected(self):
        assert contains_disallowed_content_helper("Contract value is $50,000.") is True

    def test_monetary_word_detected(self):
        assert contains_disallowed_content_helper("Contract value is 50000 yen.") is True

    def test_japanese_script_detected(self):
        assert contains_disallowed_content_helper("担当者は山田太郎です") is True
