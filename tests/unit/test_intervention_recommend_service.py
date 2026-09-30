# SVC-C2-051 — Unit Tests: intervention_recommend_service (step 5 — KB
# governance: fail-closed loading, provenance warning, deterministic lookup)

import inspect
import json

import pytest

from src.services.intervention_recommend_service import (
    InterventionKbError,
    is_sample_kb,
    load_intervention_kb,
    lookup_intervention,
    present_intervention,
)

_VALID_KB = {
    "kb_version": "TEST-1",
    "source": "test fixture",
    "provenance_verified": True,
    "institution_scope_note": "Scope note.",
    "recommendations": {
        "Red:relationship": "Escalate to a senior CSM immediately.",
        "Yellow:relationship": "Schedule an executive business review.",
    },
}


def _write_kb(tmp_path, data) -> str:
    path = tmp_path / "kb.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


class TestLoadInterventionKb:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(InterventionKbError, match="not found"):
            load_intervention_kb(str(tmp_path / "does-not-exist.json"))

    def test_invalid_json_raises(self, tmp_path):
        path = tmp_path / "kb.json"
        path.write_text("not json", encoding="utf-8")
        with pytest.raises(InterventionKbError, match="not valid JSON"):
            load_intervention_kb(str(path))

    def test_missing_required_key_raises(self, tmp_path):
        data = dict(_VALID_KB)
        del data["source"]
        with pytest.raises(InterventionKbError, match="missing required key"):
            load_intervention_kb(_write_kb(tmp_path, data))

    def test_empty_recommendations_raises(self, tmp_path):
        data = dict(_VALID_KB)
        data["recommendations"] = {}
        with pytest.raises(InterventionKbError, match="empty or invalid"):
            load_intervention_kb(_write_kb(tmp_path, data))

    def test_valid_kb_loads(self, tmp_path):
        loaded = load_intervention_kb(_write_kb(tmp_path, _VALID_KB))
        assert loaded["kb_version"] == "TEST-1"

    def test_unverified_kb_warns(self, tmp_path):
        data = dict(_VALID_KB)
        data["provenance_verified"] = False
        with pytest.warns(UserWarning, match="provenance_verified=false"):
            load_intervention_kb(_write_kb(tmp_path, data))

    def test_verified_kb_does_not_warn(self, tmp_path, recwarn):
        load_intervention_kb(_write_kb(tmp_path, _VALID_KB))
        assert len(recwarn) == 0

    def test_shipped_reference_kb_loads_and_is_sample(self):
        # The reference KB shipped with the template (src/services/kb/
        # intervention_matrix.json) must itself load successfully and is
        # honestly labeled as an unverified sample.
        from pathlib import Path

        kb_path = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "services"
            / "kb"
            / "intervention_matrix.json"
        )
        with pytest.warns(UserWarning):
            kb = load_intervention_kb(str(kb_path))
        assert is_sample_kb(kb) is True
        # 3 tiers x 4 dimensions
        assert len(kb["recommendations"]) == 12


class TestIsSampleKb:
    def test_unverified_is_sample(self):
        assert is_sample_kb({"provenance_verified": False}) is True

    def test_verified_is_not_sample(self):
        assert is_sample_kb({"provenance_verified": True}) is False


class TestLookupIntervention:
    def test_known_combination_returns_recommendation_with_scope_note(self):
        text = lookup_intervention(_VALID_KB, "Red", "relationship")
        assert "Escalate to a senior CSM immediately." in text
        assert "Scope note." in text

    def test_unmapped_combination_raises(self):
        with pytest.raises(InterventionKbError, match="no entry for"):
            lookup_intervention(_VALID_KB, "Green", "commercial_risk")

    def test_no_llm_parameter(self):
        params = list(inspect.signature(lookup_intervention).parameters)
        assert "llm" not in params


class TestPresentIntervention:
    def test_fallback_used_when_no_llm(self):
        text = present_intervention("Escalate now.", "Red")
        assert "Recommended Intervention" in text
        assert "Red" in text
        assert "Escalate now." in text

    def test_llm_output_used_when_clean(self):
        class StubLLM:
            def complete(self, prompt):
                return "Framed recommendation text."

        text = present_intervention("Escalate now.", "Red", llm=StubLLM())
        assert "Framed recommendation text." in text

    def test_llm_output_discarded_on_leaked_content(self):
        class LeakLLM:
            def complete(self, prompt):
                return "Contact John Smith about the $50,000 renewal."

        text = present_intervention("Escalate now.", "Red", llm=LeakLLM())
        assert "John Smith" not in text
        assert "$50,000" not in text
        assert "Escalate now." in text
