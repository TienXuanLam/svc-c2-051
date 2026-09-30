# PB-05 (domain): Health-scoring config governance + intervention-KB
# governance boundary. Verifies the approved workflow's config surface —
# dimension_weights / risk_thresholds / intervention_kb_path — actually
# governs the compiled agent's classification/recommendation behavior, that
# a misconfigured config.yaml fails agent.compile() loudly (fail-closed, not
# fail-open), and that this happens via the real deployment
# configuration-loading path (src.api.server._load_runtime_config()), not
# only constructor injection (mirrors a prior fleet review round 2 finding —
# applied proactively here from the start).

import json

import pytest

from src.graph.graph import CustomerSuccessRenewalRiskAssessmentAccountHealthReportAgent as Agent
from src.services.intervention_recommend_service import InterventionKbError


class TestHealthScoringConfigGovernance:
    def test_default_config_compiles(self):
        agent = Agent(config={})
        agent.compile()
        main = agent._nodes["main"]
        assert main._dimension_weights["product_adoption"] == 0.25
        assert main._risk_thresholds["red_max"] == 40

    def test_missing_dimension_key_fails_agent_compile(self):
        agent = Agent(
            config={
                "dimension_weights": {
                    "product_adoption": 0.4,
                    "support_health": 0.3,
                    "relationship": 0.3,
                    # missing commercial_risk
                }
            }
        )
        with pytest.raises(ValueError, match="dimension_weights"):
            agent.compile()

    def test_weights_not_summing_to_one_fails_agent_compile(self):
        agent = Agent(
            config={
                "dimension_weights": {
                    "product_adoption": 0.5,
                    "support_health": 0.5,
                    "relationship": 0.5,
                    "commercial_risk": 0.5,
                }
            }
        )
        with pytest.raises(ValueError, match="sum to 1.0"):
            agent.compile()

    def test_missing_risk_threshold_key_fails_agent_compile(self):
        agent = Agent(config={"risk_thresholds": {"red_max": 40}})
        with pytest.raises(ValueError, match="risk_thresholds"):
            agent.compile()

    def test_custom_weights_override_default(self):
        agent = Agent(
            config={
                "dimension_weights": {
                    "product_adoption": 0.4,
                    "support_health": 0.2,
                    "relationship": 0.2,
                    "commercial_risk": 0.2,
                },
                "risk_thresholds": {"red_max": 30, "yellow_max": 70},
            }
        )
        agent.compile()
        main = agent._nodes["main"]
        assert main._dimension_weights["product_adoption"] == 0.4
        assert main._risk_thresholds["red_max"] == 30


class TestInterventionKbGovernance:
    def test_missing_kb_path_fails_agent_compile(self, tmp_path):
        agent = Agent(config={"intervention_kb_path": str(tmp_path / "does-not-exist.json")})
        with pytest.raises(InterventionKbError, match="not found"):
            agent.compile()

    def test_invalid_kb_json_fails_agent_compile(self, tmp_path):
        bad_kb = tmp_path / "kb.json"
        bad_kb.write_text("not json", encoding="utf-8")
        agent = Agent(config={"intervention_kb_path": str(bad_kb)})
        with pytest.raises(InterventionKbError, match="not valid JSON"):
            agent.compile()

    def test_default_shipped_kb_loads_and_warns_unverified(self, tmp_path):
        with pytest.warns(UserWarning, match="provenance_verified=false"):
            agent = Agent(config={})
            agent.compile()
        main = agent._nodes["main"]
        assert main._intervention_kb["kb_version"]

    def test_institution_kb_override_reaches_compiled_agent(self, tmp_path):
        custom_kb = tmp_path / "kb.json"
        custom_kb.write_text(
            json.dumps(
                {
                    "kb_version": "INSTITUTION-1",
                    "source": "institution playbook",
                    "provenance_verified": True,
                    "recommendations": {
                        f"{tier}:{dim}": f"{tier}/{dim} custom text"
                        for tier in ("Red", "Yellow", "Green")
                        for dim in ("product_adoption", "support_health", "relationship", "commercial_risk")
                    },
                }
            ),
            encoding="utf-8",
        )
        agent = Agent(config={"intervention_kb_path": str(custom_kb)})
        agent.compile()
        main = agent._nodes["main"]
        assert main._intervention_kb["kb_version"] == "INSTITUTION-1"


class TestDeploymentConfigLoadingPath:
    """Exercises src.api.server._load_runtime_config() — the exact function
    the real entry point calls at import/startup time — against real temp
    config.yaml files, and against the real repo config.yaml."""

    def test_load_runtime_config_reads_real_repo_config_yaml(self):
        from src.api.server import _load_runtime_config

        cfg = _load_runtime_config()
        assert cfg["dimension_weights"]["product_adoption"] == 0.25
        assert cfg["risk_thresholds"]["red_max"] == 40

    def test_operator_edited_config_yaml_reaches_compiled_agent(self, tmp_path):
        from src.api.server import _load_runtime_config

        operator_config_yaml = tmp_path / "config.yaml"
        operator_config_yaml.write_text(
            "max_retry: 3\nmemory_enabled: false\ntimeout_s: 30\n"
            "dimension_weights:\n"
            "  product_adoption: 0.4\n"
            "  support_health: 0.2\n"
            "  relationship: 0.2\n"
            "  commercial_risk: 0.2\n"
            "risk_thresholds:\n  red_max: 40\n  yellow_max: 65\n",
            encoding="utf-8",
        )
        loaded = _load_runtime_config(operator_config_yaml)
        agent = Agent(config=loaded)
        agent.compile()
        main = agent._nodes["main"]
        assert main._dimension_weights["product_adoption"] == 0.4

    def test_operator_edited_config_yaml_with_incomplete_weights_blocks_compile(self, tmp_path):
        from src.api.server import _load_runtime_config

        operator_config_yaml = tmp_path / "config.yaml"
        operator_config_yaml.write_text(
            "max_retry: 3\nmemory_enabled: false\ntimeout_s: 30\n"
            "dimension_weights:\n  product_adoption: 1.0\n",
            encoding="utf-8",
        )
        loaded = _load_runtime_config(operator_config_yaml)
        agent = Agent(config=loaded)
        with pytest.raises(ValueError, match="dimension_weights"):
            agent.compile()

    def test_real_server_module_constructs_successfully(self):
        # Smoke test of the actual entry point: importing src.api.server
        # runs its module-level `agent = Agent(config=_load_runtime_config());
        # agent.compile()` against the real repo config/config.yaml —
        # proving the full documented path works end-to-end.
        import src.api.server as server_module

        assert server_module.agent._nodes["main"]._dimension_weights

    def test_real_stg_invoke_payload_produces_success(self):
        import pathlib

        import src.api.server as server_module
        from framework.schemas.invocation_context import InvocationContext
        from framework.schemas.trust_level import TrustLevel

        payload_path = pathlib.Path(__file__).parents[2] / "deploy" / "invoke_payload.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        ctx = InvocationContext(
            session_id=payload.get("session_id", "s1"),
            caller_trust_level=TrustLevel.VERIFIED_EXTERNAL,
            caller_id="c1",
        )
        result = server_module.agent.invoke(payload["input"], ctx=ctx)
        assert result["status"] == "success"
