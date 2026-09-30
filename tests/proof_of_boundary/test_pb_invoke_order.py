# PB-6: Invoke Execution Order Verification
# Verifies BaseNode.__call__() enforces: S-1 trust gate -> S-4 node_start ->
# S-2 _security_gate_input() -> execute() -> S-3 _security_gate_output() ->
# S-4 node_complete, for every concrete node under src/nodes/.

import importlib
import inspect
import json
import pkgutil

import pytest

_TEST_DIMENSION_WEIGHTS = {
    "product_adoption": 0.25,
    "support_health": 0.25,
    "relationship": 0.25,
    "commercial_risk": 0.25,
}
_TEST_RISK_THRESHOLDS = {"red_max": 40, "yellow_max": 65}
_TEST_INTERVENTION_KB = {
    "kb_version": "TEST-1",
    "source": "test fixture",
    "provenance_verified": True,
    "recommendations": {
        f"{tier}:{dim}": f"{tier}/{dim} intervention"
        for tier in ("Red", "Yellow", "Green")
        for dim in ("product_adoption", "support_health", "relationship", "commercial_risk")
    },
}


def _instantiate(node_cls: type):
    """MainNode requires dimension_weights/risk_thresholds/intervention_kb
    (no hardcoded default — config.yaml is the source of truth); other
    nodes construct with no arguments."""
    if node_cls.__name__ == "MainNode":
        return node_cls(
            dimension_weights=_TEST_DIMENSION_WEIGHTS,
            risk_thresholds=_TEST_RISK_THRESHOLDS,
            intervention_kb=_TEST_INTERVENTION_KB,
        )
    return node_cls()


def _discover_node_classes() -> list[type]:
    """Import every module under src/nodes/ and collect concrete BaseNode subclasses."""
    from framework.nodes.base_node import BaseNode

    try:
        pkg = importlib.import_module("src.nodes")
    except ImportError:
        return []

    discovered = []
    for _, modname, _ in pkgutil.walk_packages(pkg.__path__, prefix="src.nodes."):
        module = importlib.import_module(modname)
        for attr in vars(module).values():
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseNode)
                and attr is not BaseNode
                and attr.__module__ == modname
                and not inspect.isabstract(attr)
            ):
                discovered.append(attr)
    return discovered


class TestInvokeOrder:
    """PB-6: __call__ must run S-1 -> node_start -> S-2 -> execute() -> S-3 -> node_complete."""

    def test_call_order_for_every_node(self, monkeypatch):
        node_classes = _discover_node_classes()
        if not node_classes:
            pytest.skip("no concrete BaseNode subclasses found under src/nodes/")

        import framework.nodes.base_node as base_node_module

        failures: list[str] = []
        for node_cls in node_classes:
            order: list[str] = []
            monkeypatch.setattr(
                base_node_module,
                "emit_trace_event",
                lambda event_type, _payload, _state, _o=order: _o.append(f"event:{event_type}"),
            )

            for method_name, label in (
                ("_security_gate_input", "security_gate_input"),
                ("execute", "execute"),
                ("_security_gate_output", "security_gate_output"),
            ):
                original = getattr(node_cls, method_name)

                def spy(self, arg, _o=order, _label=label, _orig=original):
                    _o.append(_label)
                    return _orig(self, arg)

                monkeypatch.setattr(node_cls, method_name, spy)

            instance = _instantiate(node_cls)
            # user_input must be a valid account-signals JSON payload —
            # PreProcessNode's custom S-2 pre-processing check
            # (docs/02_design.md) rejects malformed input at the gate, which
            # would short-circuit before execute() and break the order
            # assertion below for that node.
            state = {
                "caller_trust_level": node_cls.required_trust_level.value,
                "correlation_id": "pb6-invoke-order-test",
                "user_input": json.dumps(
                    {
                        "dau_wau_trend_pct": -10.0,
                        "ticket_count": 3,
                        "ticket_severity_avg": 2.0,
                        "nps_score": 20.0,
                        "contract_utilization_pct": 70.0,
                        "days_to_renewal": 100,
                    }
                ),
            }
            instance(state)

            expected = [
                "event:node_start",
                "security_gate_input",
                "execute",
                "security_gate_output",
                "event:node_complete",
            ]
            if order != expected:
                failures.append(
                    f"{node_cls.__name__}: invoke order violation.\n" f"expected: {expected}\nactual:   {order}"
                )

        assert not failures, "\n\n".join(failures)
