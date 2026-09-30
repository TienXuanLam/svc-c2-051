"""AgentCore Platform v1.0"""

# Step 1 — AccountSignalIngest. Pure Python, no framework imports (per the
# framework's service-module contract: service modules must not depend on
# the agenticstar SDK or on framework security-gate code directly).
#
# Custom pre-processing check (proposal §3/§10): reject customer company
# names, contact names, and contract values. Proposal §10 labels this check
# "S-1" — per the framework's 5-layer security model, S-1 is the framework's
# trust-gate layer (cannot itself do content rejection); this domain-specific
# rejection is implemented as a custom S-2 input-content check
# (_extra_security_gate_input), consistent with an established fleet
# precedent for this proposal-terminology mismatch.
#
# Design decision (docs/02_design.md): unlike other templates in this project line, this
# template's input schema has NO free-text field at all — every field is
# strictly numeric. Per proposal §10 angle 5's own explicit guidance
# ("Reject any field value that is a string longer than N chars where a
# number is expected"), strict numeric type + range validation on ingest IS
# the S-2 content check — there is no field shape in which a company name,
# contact name, or contract value could be smuggled through without failing
# numeric validation outright. The NAME_CUE_RE/MONEY_*_RE/JAPANESE_SCRIPT_RE
# patterns below exist for the OUTPUT-side re-scan only (reused by
# output_validate_service.py) — they guard against an LLM hallucinating such
# content into the narrative sections, not against the structured input.

from __future__ import annotations

import json
import re
from typing import cast

REQUIRED_FIELDS = (
    "dau_wau_trend_pct",
    "ticket_count",
    "ticket_severity_avg",
    "nps_score",
    "contract_utilization_pct",
    "days_to_renewal",
)

# Valid ranges for each numeric field — out-of-range values are rejected as
# a data-quality error (proposal §11 Risk #3), not silently clamped.
FIELD_RANGES = {
    "dau_wau_trend_pct": (-100.0, 100.0),
    "ticket_count": (0, 10_000),
    "ticket_severity_avg": (0.0, 5.0),
    "nps_score": (-100.0, 100.0),
    "contract_utilization_pct": (0.0, 100.0),
    "days_to_renewal": (0, 3650),
}

# ticket_count and days_to_renewal are discrete operational signals (int in
# docs/02_design.md "State Definition") — a fractional value like 3.9 or
# 60.5 is not a legitimate reading, and int(3.9) == 3 previously truncated
# it silently instead of rejecting it, changing the evidence used for risk
# classification/reporting without surfacing an error (eng-moderator T1-01,
# MEDIUM). Rejected explicitly here rather than defining a rounding policy
# — per the required-correction guidance, rejection is preferred when the
# field represents a count of discrete real-world events/days.
INTEGER_ONLY_FIELDS = ("ticket_count", "days_to_renewal")

# Public (not underscore-prefixed): reused by output_validate_service.py for
# the step-7 belt-and-suspenders re-scan.
#
# Cue-gated ASCII name detection (IMPLEMENTATION_LOG.md A8): a bare "two
# capitalized words" pattern false-positives on legitimate headings/labels
# this template itself generates. Requires a name/company-introducing cue
# word immediately before the candidate text.
#
# Two cue groups with different separator strictness (found by direct
# testing — this template's own "# Account Health Report Draft" heading
# collided with a bare "account" cue): "name"/"contact"/"reported by" are
# specific enough to name-introducing use that an optional separator is
# safe (matches an established fleet pattern). "account"/"company"/
# "customer"/"client" are common CS-domain prose words that appear in this
# template's own headings without introducing a name — these require a
# MANDATORY colon/dash separator (i.e. an explicit label like
# "Account: Acme Corp"), which this template's own prose headings never use.
NAME_CUE_RE = re.compile(
    r"(?:(?i:name|contact|reported by)\s*[:\-]?\s+|(?i:account|company|customer|client)\s*[:\-]\s+)"
    r"([A-Z][a-z]+\s[A-Z][a-z]+)"
)

# Monetary value detection: currency symbol + amount, or amount + currency
# code/word (English and Japanese). Covers proposal §3/§10's "contract
# value" exclusion requirement.
MONEY_SYMBOL_RE = re.compile(r"[¥$€£]\s?\d[\d,]*(?:\.\d+)?")
MONEY_WORD_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?\s?(?:yen|USD|JPY|EUR|GBP|dollars?|円|万円)\b", re.IGNORECASE)

# Japanese-script detection: no cue word required — this template's own
# generated content (headings, disclaimer, fallback templates) is pure
# ASCII English, so a bare CJK-script run carries no false-positive risk
# against our own output (same rationale as elsewhere in this project line).
JAPANESE_SCRIPT_RE = re.compile(r"[一-鿿぀-ゟ゠-ヿ]{2,}")


def contains_disallowed_content_helper(text: str) -> bool:
    """True if `text` appears to carry a company/contact name (cue-word
    gated) or a monetary value. Used to fail-safe-filter LLM-generated
    narrative sections (root_cause_narrate_service.py,
    intervention_recommend_service.py) before they are inserted into the
    report — NOT used for input-field validation (see module docstring:
    input fields are strictly numeric, so this check is unnecessary there).
    """
    if not text:
        return False
    return (
        bool(NAME_CUE_RE.search(text))
        or bool(MONEY_SYMBOL_RE.search(text))
        or bool(MONEY_WORD_RE.search(text))
        or bool(JAPANESE_SCRIPT_RE.search(text))
    )


def parse_account_signals(raw: str) -> tuple[dict[str, object] | None, str | None]:
    """Parse the caller-supplied JSON account-signal string.

    Returns (signals, None) on success or (None, error_message) on failure.
    All 6 fields must be present, numeric, and within FIELD_RANGES — this is
    the complete S-2 content check for this template (see module docstring).
    """
    if not raw or not raw.strip():
        return None, "AccountSignalIngest: user_input is empty"

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, "AccountSignalIngest: user_input is not valid JSON"

    if not isinstance(payload, dict):
        return None, "AccountSignalIngest: user_input JSON must be an object"

    missing = [f for f in REQUIRED_FIELDS if payload.get(f) in (None, "")]
    if missing:
        return None, f"AccountSignalIngest: missing required field(s): {', '.join(missing)}"

    numeric: dict[str, object] = {}
    for field in REQUIRED_FIELDS:
        value = payload[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None, f"AccountSignalIngest: '{field}' must be numeric"
        if field in INTEGER_ONLY_FIELDS and isinstance(value, float) and not value.is_integer():
            return None, f"AccountSignalIngest: '{field}' must be a whole number, not a fractional value"
        low, high = FIELD_RANGES[field]
        if not (low <= value <= high):
            return None, f"AccountSignalIngest: '{field}' must be between {low} and {high}"
        numeric[field] = value

    return {
        "dau_wau_trend_pct": float(cast("int | float", numeric["dau_wau_trend_pct"])),
        "ticket_count": int(cast("int | float", numeric["ticket_count"])),
        "ticket_severity_avg": float(cast("int | float", numeric["ticket_severity_avg"])),
        "nps_score": float(cast("int | float", numeric["nps_score"])),
        "contract_utilization_pct": float(cast("int | float", numeric["contract_utilization_pct"])),
        "days_to_renewal": int(cast("int | float", numeric["days_to_renewal"])),
    }, None
