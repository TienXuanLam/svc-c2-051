"""AgentCore Platform v1.0"""

# Step 5 — InterventionRecommend.
#
# Design Decision Record (docs/02_design.md): proposal §12 explicitly lists
# "Intervention KB construction (risk tier × weak dimension matrix)" as a
# dependency still "in progress (scope in design phase)" — exactly the kind
# of operationally consequential reference data that must not be silently
# hardcoded or presented as authoritative without verification. This
# directly reuses an established fleet sanction-KB governance pattern (prior
# review lessons): the intervention matrix lives in an external, versioned JSON file
# (default: src/services/kb/intervention_matrix.json, overridable via
# config.yaml's intervention_kb_path). load_intervention_kb() is
# fail-closed: a missing file, invalid JSON, or missing required keys
# raises InterventionKbError at agent construction time. `provenance_verified`
# is a required KB field — every KB (shipped or institution-supplied) must
# explicitly declare true/false; load_intervention_kb() warns loudly
# (non-fatal — dev/STG legitimately runs against the unverified sample) when
# it is false.
#
# lookup_intervention() remains a pure, deterministic function over the
# loaded KB dict — no `llm` parameter (IMPLEMENTATION_LOG.md A4). An
# unmapped risk-tier/weakest-dimension combination raises rather than
# silently substituting a generic recommendation.

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

from src.services.account_signal_ingest_service import contains_disallowed_content_helper

REQUIRED_KB_KEYS = ("kb_version", "source", "recommendations", "provenance_verified")


class InterventionKbError(Exception):
    """Raised when the intervention KB is missing, malformed, or incomplete.

    Deliberately fail-closed: callers must not catch this to substitute a
    silent default — an institution must supply a valid, versioned
    intervention playbook before this template can produce recommendations.
    """


def load_intervention_kb(kb_path: str) -> dict[str, Any]:
    """Load and validate the intervention KB file. Raises
    InterventionKbError on any problem — called once at agent construction
    time (src/graph/graph.py register_nodes()), so a misconfigured
    intervention_kb_path fails agent.compile() loudly."""
    path = Path(kb_path)
    if not path.is_file():
        raise InterventionKbError(
            f"Intervention KB not found at '{kb_path}'. Set config.yaml's "
            "intervention_kb_path to a valid institution playbook file (see "
            "src/services/kb/intervention_matrix.json for the reference schema)."
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InterventionKbError(f"Intervention KB at '{kb_path}' is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise InterventionKbError(f"Intervention KB at '{kb_path}' must be a JSON object.")

    missing = [key for key in REQUIRED_KB_KEYS if key not in data]
    if missing:
        raise InterventionKbError(f"Intervention KB at '{kb_path}' missing required key(s): {', '.join(missing)}.")

    if not isinstance(data["recommendations"], dict) or not data["recommendations"]:
        raise InterventionKbError(f"Intervention KB at '{kb_path}' has an empty or invalid 'recommendations' object.")

    if data["provenance_verified"] is not True:
        warnings.warn(
            f"Intervention KB at '{kb_path}' (v{data.get('kb_version', 'unknown')}) has "
            "provenance_verified=false — this KB has NOT been verified against a cited "
            "institution playbook and must not be used in production. See "
            "docs/07_operation_guide.md 'Intervention KB Setup' and the STG Sign-off "
            "Record checklist.",
            stacklevel=2,
        )

    return data


def is_sample_kb(intervention_kb: dict[str, Any]) -> bool:
    """True when the loaded KB has not been provenance-verified."""
    return intervention_kb.get("provenance_verified") is not True


def lookup_intervention(intervention_kb: dict[str, Any], risk_tier: str, weakest_dimension: str) -> str:
    """Deterministic KB lookup — no `llm` parameter (asserted by a PB test,
    A4 principle). Raises InterventionKbError (fail-closed) if the KB does
    not define a recommendation for this risk-tier/weakest-dimension
    combination."""
    key = f"{risk_tier}:{weakest_dimension}"
    recommendations = intervention_kb["recommendations"]
    if key not in recommendations:
        raise InterventionKbError(
            f"Intervention KB v{intervention_kb.get('kb_version', 'unknown')} "
            f"(source: {intervention_kb.get('source', 'unknown')}) has no entry for '{key}'."
        )
    scope_note = intervention_kb.get("institution_scope_note", "")
    return f"{recommendations[key]} {scope_note}".strip()


def present_intervention(intervention_text: str, risk_tier: str, llm: Any = None) -> str:
    """Narrative presentation wrapper around the deterministic KB lookup
    result — LLM (optional) may add priority/framing language; the
    underlying recommendation content itself is never LLM-decided. Any LLM
    output containing a detected company/contact name or monetary value is
    discarded fail-safe."""
    fallback = f"## Recommended Intervention\n\n**Priority:** {risk_tier}\n\n{intervention_text}\n"
    if llm is None:
        return fallback

    prompt = (
        "Present the following Customer Success intervention recommendation "
        "with appropriate priority framing for a management report. Do not "
        "invent a different recommendation, and do not mention any customer "
        "company name, contact name, or contract/dollar amount.\n\n"
        f"Risk tier: {risk_tier}\n"
        f"Recommendation: {intervention_text}\n"
    )
    try:
        text = llm.complete(prompt)
    except Exception:
        return fallback

    if not text or contains_disallowed_content_helper(text):
        return fallback
    return f"## Recommended Intervention\n\n{text}\n"
