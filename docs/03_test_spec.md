# Test Specification

## Test Strategy
- Coverage target: 100% of `src/services/*.py` (7/7) and `src/nodes/*.py` (3/3) — all
  deterministic domain logic and node dispatch paths.
- Test types: Unit (`tests/unit/`) + Proof-of-Boundary (`tests/proof_of_boundary/`).
  No integration tests — `dimension_weights`/`risk_thresholds`/`intervention_kb_path`
  are institution-configurable local YAML config (proposal §10/§12), not a remote
  service; LLM is optional with a deterministic fallback for every drafting step.
- Verified against the real `agenticstar-agentcore` framework throughout development.

## S-1/S-3 Detection Scope Statement

Unlike other templates in this project line, this template's input schema (`src/schemas/state.py`,
`account_signal_ingest_service.py`) has **no free-text field at all** — every one of
the 6 caller-supplied fields is strictly numeric with a validated range
(`FIELD_RANGES`). Per proposal §10 angle 5's own explicit guidance ("reject any
field value that is a string longer than N chars where a number is expected"),
strict numeric type + range validation on ingest **is** the complete S-2 content
check — there is no field shape through which a company/contact name or contract
value could be smuggled without failing numeric validation outright.

The `NAME_CUE_RE`/`MONEY_SYMBOL_RE`/`MONEY_WORD_RE`/`JAPANESE_SCRIPT_RE` patterns
(defined once in `account_signal_ingest_service.py`, reused by
`output_validate_service.py`) exist purely for the **output-side re-scan** — they
guard against an LLM hallucinating such content into the narrative sections
(root cause, intervention), not against the structured numeric input. This makes
the S-3 output gate (PB-02) the **primary** defense in this template, not a
belt-and-suspenders addition — see `docs/02_design.md` "S-1/S-3 Detection Scope".

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: flat TypedDict (`src/schemas/state.py`) | No Pydantic/dataclass — `tests/proof_of_boundary/test_state_safety.py` | PASS |
| TC-02 | Invalid/malformed input rejected | `PreProcessNode` custom S-2 gate rejects malformed JSON / missing fields / non-numeric / out-of-range values — `tests/unit/test_pre_process_node.py` | PASS |
| TC-03 | No JWT/Credential in State | CI `gate-credential-scan`: 0 violations | Pending real CI run |
| TC-04 | `InvocationContext` via `from_state()` only | No node in this template constructs `InvocationContext` directly — every drafting step has a deterministic fallback, no secret-gated dependency required | PASS |
| TC-05 | S-4: no duplicate lifecycle events in `execute()` | `node_start`/`node_complete`/`node_error` absent from all 3 `execute()` bodies (confirmed by code review) | PASS |
| TC-06 | S-2: `_security_gate_input()` not overridden | Only `_extra_security_gate_input()` on `PreProcessNode` | PASS |
| TC-07 | S-3: `_security_gate_output()` not overridden | Only `_extra_security_gate_output()` on `PostProcessNode` | PASS |
| TC-08 | `required_trust_level` enforced (via `__call__`, not `execute()`) | `tests/unit/test_pre_process_node.py::test_trust_gate_denies_anonymous_caller` | PASS |
| TC-09 | S-2 `_extra_security_gate_input()` non-trivial | `PreProcessNode` rejects non-numeric/out-of-range/malformed input — `tests/unit/test_pre_process_node.py` | PASS |
| TC-10 | S-3 `_extra_security_gate_output()` non-trivial | `PostProcessNode` independently re-scans for prohibited content, may raise — `tests/unit/test_post_process_node.py::TestPostProcessNodeOutputGateHook` | PASS |
| TC-11 | S-4: ≥1 domain `emit_trace_event()` per node, on the success path | `account_signals_ingested` (pre_process), `health_scored`/`risk_classified`/`llm_call`×2 (conditional on `llm is not None`, not on LLM call outcome)/`intervention_looked_up` (main), `output_content_scan` (post_process) | PASS — correction (eng-moderator T2-02, LOW): a prior revision of this row read "per node" without qualification, which was interpreted as "every invocation" in review. This is success-path domain-event coverage only: `PreProcessNode.execute()` returns before `account_signals_ingested` fires when `_extra_security_gate_input()` (or the defense-in-depth re-check in `execute()`) rejects the input (`src/nodes/pre_process_node.py`) — no domain event is emitted for a rejected request. Separately, `llm_call` is emitted whenever `self._llm is not None` (`src/nodes/main_node.py`) — i.e. an LLM is *configured* — regardless of whether that LLM call itself succeeded or the deterministic fallback engaged after an exception; it is not evidence the LLM call succeeded. |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-1 | BaseNode → AuditLogger | `emit_trace_event()` fires on the success path of every node (see TC-11 correction) | No silent failures on the success path — NOT all-path/failure-path audit telemetry; a rejected `pre_process` request emits no domain event at all | PASS |
| PB-2 | State serialization | `test_state_safety.py` | No Pydantic/dataclass/credential fields in `src/schemas/state.py` | PASS |
| PB-3 | L1 → External service | N/A — scoring/classification config is local YAML; LLM is optional | Not applicable | N/A |
| PB-4 | Import isolation | `test_import_isolation.py` (`encoding="utf-8"` fix — Japanese-script source content breaks the Windows cp1252 default read) | AST scan: 0 violations across `src/` | PASS |
| PB-5 | Checkpoint safety | Covered by PB-2 (same state definition) | No JWT/Pydantic in checkpoint | PASS |
| PB-6 | Invoke execution order | `test_pb_invoke_order.py` (`_instantiate()` supplies `MainNode`'s required `dimension_weights`/`risk_thresholds`/`intervention_kb`; state carries a valid account-signals JSON `user_input` so `PreProcessNode`'s custom S-2 gate doesn't short-circuit) | S-1 → `node_start` → S-2 → `execute()` → S-3 → `node_complete`, for all 3 nodes | PASS |
| PB-7 | HITL interrupt propagation | Not applicable — `config/config.yaml` does not set `hitl.enabled: true` (CSM verification against source systems is an out-of-band human process, not a technical `interrupt()` checkpoint; see `docs/02_design.md`) | **Auto-waived — non-HITL** | SKIPPED (2 tests, by design) |

## Domain Proof-of-Boundary Tests

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-01 | Custom S-2 pre-processing check (AccountSignalIngest → MainNode) | `test_pb01_custom_content_rejection.py` | An injection attempt, out-of-range value, missing field, or fractional discrete signal (`ticket_count`/`days_to_renewal`) never produces `report_draft`/`risk_tier` state — rejected before reaching `main`. A clean numeric payload reaches `main` and produces a report | PASS (added `test_fractional_ticket_count_never_reaches_main_node` / `test_fractional_days_to_renewal_never_reaches_main_node`, eng-moderator T2-01, MEDIUM, 2026-07-20) |
| PB-02 | S-3 output gate — **primary defense** (see Detection Scope above) | `test_pb02_s3_output_content_block.py` | A report with a leaked name/monetary value/Japanese identifier is blocked via the real `__call__()` pipeline, and independently via the gate hook even if the execute()-level check is bypassed | PASS |
| PB-03 | Deterministic-vs-LLM authority | `test_pb03_deterministic_classification.py` | `score_all_dimensions()`/`compute_composite_score()`/`classify_risk_tier()`/`identify_weakest_dimension()` signatures have no `llm` parameter; the full classification pipeline is pure | PASS |
| PB-04 | No-prohibited-content guarantee (proposal §3/§10) | `test_pb04_prohibited_content_never_leaks.py` | No adversarial LLM output (name/money/Japanese) survives into the assembled report across both LLM-touched sections (root cause narrative, intervention presentation); this template's own fallback templates contain no hardcoded prohibited content | PASS |
| PB-05 | Health-scoring config governance + intervention-KB governance + deployment config-loading path | `test_pb05_kb_and_config_governance.py` | Default config compiles; a missing dimension-weight/risk-threshold key or a weight sum ≠ 1.0 fails `agent.compile()` (fail-closed); a missing/invalid intervention KB file fails `agent.compile()` (`InterventionKbError`); the shipped sample KB loads with a `provenance_verified=false` warning; custom config genuinely overrides defaults **via the real deployment loading path** (`src.api.server._load_runtime_config()`); the STG `deploy/invoke_payload.json` produces `status: success` | PASS |

> **Pre-CoE gate checklist:** PB-1 through PB-6 are mandatory (PB-3 N/A per
> above). PB-7 is auto-waived — non-HITL. PB-01 through PB-05 are
> domain-specific additions covering this template's highest proposal risks
> (§11 Risk #1: LLM hallucination risk; §11 Risk #3: data-quality/injection
> risk; the KB-governance risk mirroring a prior fleet review
> finding), applying every relevant prior-template lesson from the start
> rather than as a post-review fix.

## Business Logic Tests

| TC-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01 | Health-dimension scoring — all 4 dimensions | Representative signal values (usage trend, tickets, NPS, utilization) | Deterministic 0-100 score per dimension, clamped at the boundaries | PASS (`test_health_dimension_score_service.py`) |
| BL-02 | Composite score + risk-tier classification | Weighted dimension scores against `red_max`/`yellow_max` thresholds | Correct Red/Yellow/Green tier returned deterministically, boundary-inclusive on the Yellow side | PASS (`test_risk_classify_service.py`) |
| BL-03 | Weakest-dimension identification, including ties | Tied lowest scores across dimensions | Deterministic — first dimension in `DIMENSION_NAMES` order | PASS (`test_risk_classify_service.py::test_tie_returns_first_in_dimension_order`) |
| BL-04 | Renewal outlook framing across all 3 windows | `days_to_renewal` inside/at/outside the configured warning window | Correct immediate/early-warning/outside-window message, tolerant of an unsorted `renewal_warning_days` tuple | PASS (`test_report_draft_service.py::TestRenewalOutlook`) |
| BL-05 | Report assembly — all sections present | Full set of drafted sections | Markdown report contains Health Scorecard, Root Cause Narrative, Recommended Intervention, Renewal Outlook | PASS (`test_report_draft_service.py`) |
| BL-06 | Mandatory disclaimer on every released report | Clean report draft | Output is prefixed with the "AI DRAFT — NOT A FINAL DETERMINATION" disclaimer | PASS (`test_output_validate_service.py`) |
| BL-07 | Self-heading false-positive regression | This template's own generated headings ("# Account Health Report Draft", "Health Scorecard", etc.) | Not flagged as a prohibited-content violation | PASS (`test_output_validate_service.py::test_own_headings_not_false_positive`, `test_account_signal_ingest_service.py::test_bare_account_word_not_false_flagged`) |
| BL-08 | Prohibited-content fail-safe filter on every LLM-touched section | Adversarial LLM stub returning name/money/Japanese-shaped text | Discarded in favor of the deterministic fallback, for root cause narrative and intervention presentation alike | PASS (`test_root_cause_narrate_service.py`, `test_intervention_recommend_service.py`, `test_pb04_prohibited_content_never_leaks.py`) |
| BL-09 | Intervention KB governance — fail-closed loading + provenance warning | Missing file, invalid JSON, missing required key, empty `recommendations`, `provenance_verified=false` | `InterventionKbError` raised for each malformed case; non-fatal `UserWarning` for the unverified-sample case | PASS (`test_intervention_recommend_service.py::TestLoadInterventionKb`) |
| BL-10 | Unmapped risk-tier/weakest-dimension combination | KB missing the required `"{tier}:{dimension}"` key | `InterventionKbError` raised (fail-closed, no silent generic substitute) | PASS (`test_intervention_recommend_service.py::test_unmapped_combination_raises`) |
| BL-11 | Fractional discrete-signal rejection (eng-moderator T1-01, MEDIUM, 2026-07-20) | `ticket_count`/`days_to_renewal` as a non-integral float (e.g. `3.9`, `60.5`) vs. a whole-number float (e.g. `3.0`) | Fractional values rejected with a specific message — `int(3.9) == 3` previously truncated silently instead of rejecting; whole-number floats still accepted and coerced to `int` | PASS (`test_account_signal_ingest_service.py::test_fractional_ticket_count_rejected`, `test_fractional_days_to_renewal_rejected`, `test_whole_number_float_ticket_count_accepted`, `test_whole_number_float_days_to_renewal_accepted`) |

## Test Execution Summary
- Execution date: 2026-07-20
- Total tests: 145 (143 passed, 2 skipped — PB-7, auto-waived non-HITL) — up from
  139/137 after eng-moderator T1-01/T2-01 (MEDIUM, 2026-07-20) added 6 new tests: 4 unit
  (`test_fractional_ticket_count_rejected`, `test_fractional_days_to_renewal_rejected`,
  `test_whole_number_float_ticket_count_accepted`, `test_whole_number_float_days_to_renewal_accepted`
  in `test_account_signal_ingest_service.py`), 2 domain proof-of-boundary
  (`test_fractional_ticket_count_never_reaches_main_node`,
  `test_fractional_days_to_renewal_never_reaches_main_node` in `test_pb01_custom_content_rejection.py`)
- Verified against the real `agenticstar-agentcore` framework throughout development
- Local gates: `check_cat_consistency.py`, `check_dep_pinning.py`, `check_stub_tests.py`,
  `check_trust_level.py` — 4/4 PASS (`check_stub_tests.py` required the same
  `encoding="utf-8"` fix as `test_import_isolation.py` — both scan this template's
  Japanese-script source)
- Coverage: 100% of `src/services/*.py` (7/7 modules) and `src/nodes/*.py` (3/3 modules)
  have dedicated unit tests, plus 5 domain proof-of-boundary tests (PB-01 through PB-05),
  now including the fractional-integer ingress boundary for `ticket_count`/`days_to_renewal`
  at both the isolated service level and through the `pre_process` → `main` node boundary
