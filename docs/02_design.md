# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: `CustomerSuccessRenewalRiskAssessmentAccountHealthReportAgent`
- **L1 Base**: `AgentBaseGraph` (Cat 2 — fixed multi-step domain workflow, not an
  autonomous think→act→observe loop; see docs/01_proposal.md Cat Judgment Rationale)
- **Pattern**: `DocGenerationAgent` (Level 2 label; mechanism is always
  L1-direct `AgentBaseGraph` inheritance per the framework's base-graph contract)
- **Three-Layer Separation**:
  - State: flat `TypedDict` composition (`src/schemas/state.py`, extends `AgentState`)
  - Node: L1 inheritance (Template Method: `execute(self, state) -> dict` override only)
  - Graph: composition (`register_nodes()` wires 3 real `FunctionNode` instances)

## Architecture Overview

### Node-count reconciliation (proposal §4 → framework 3-slot limit)

The proposal's Agent Workflow describes **7 steps**, and — unusually among
this project line's proposals — the proposal itself already specifies the
exact slot mapping in its own "AgentCore node-slot mapping" table:

```
pre_process (PreProcessNode — real FunctionNode)
  → AccountSignalIngest        (step 1 — account_signal_ingest_service.parse_account_signals,
                                          also wired into _extra_security_gate_input as the
                                          custom S-2 numeric type/range validation)

main (MainNode — real FunctionNode)
  → HealthDimensionScore       (step 2 — health_dimension_score_service.score_all_dimensions
                                          [deterministic weighted arithmetic])
  → RiskClassify               (step 3 — risk_classify_service.compute_composite_score +
                                          classify_risk_tier + identify_weakest_dimension
                                          [all deterministic])
  → RootCauseNarrate           (step 4 — root_cause_narrate_service.draft_root_cause_narrative
                                          [LLM with deterministic fallback + prohibited-content filter])
  → InterventionRecommend      (step 5 — intervention_recommend_service.lookup_intervention
                                          [deterministic, file-backed KB] + present_intervention
                                          [LLM presentation wrapper with deterministic fallback])
  → ReportDraft                (step 6 — report_draft_service.assemble_report
                                          [deterministic string assembly incl. renewal outlook])

post_process (PostProcessNode — real FunctionNode)
  → OutputValidate             (step 7 — output_validate_service.find_prohibited_content_violations +
                                          attach_disclaimer; also wired into
                                          _extra_security_gate_output as a second,
                                          independent re-scan — defense in depth)
```

This 1/5/1 split differs from the 2/4/1 splits seen on other templates in
this project line — `AgentBaseGraph` still only exposes 3 domain slots
regardless, and the proposal's own explicit mapping is followed directly
rather than re-deriving a split (an established pattern for this class of
node-count reconciliation, applied here per the proposal's own guidance
instead of engineer judgment).

### Node Configuration

| Node | Responsibility | Input State | Output State | Inherits/Overrides |
|------|---------------|-------------|--------------|-------------------|
| initialize | Standard state setup | — | `session_id`, `caller_trust_level`, `node_history=[]`, `error_log=[]` | `InitializeNode` (default) |
| pre_process | Parse+validate account signals (step 1); reject non-numeric/out-of-range fields (custom S-2) | `user_input` (JSON string) | `dau_wau_trend_pct`, `ticket_count`, `ticket_severity_avg`, `nps_score`, `contract_utilization_pct`, `days_to_renewal` | `FunctionNode` |
| main | Score 4 dimensions (step 2) + classify risk (step 3) + narrate root cause (step 4) + recommend intervention (step 5) + assemble report (step 6) | signal fields | dimension scores, `composite_score`, `risk_tier`, `weakest_dimension`, `root_cause_section`, `intervention_section`, `report_draft` | `FunctionNode` |
| post_process | Re-scan assembled report for prohibited content (step 7, S-3 belt-and-suspenders); attach mandatory disclaimer | `report_draft` | `output_pii_violations`, `formatted_output` | `FunctionNode` |
| finalize | Assemble final output from state | `formatted_output` | response | `FinalizeNode` (default) |

### Step Detail (7 proposal steps → 3 node dispatchers)

| Step | Node | Service module | Deterministic / LLM |
|------|------|----------------|---------------------|
| 1. AccountSignalIngest | pre_process | `account_signal_ingest_service.py` | Deterministic (JSON parse + numeric type/range validation) |
| 2. HealthDimensionScore | main | `health_dimension_score_service.py` | Deterministic weighted arithmetic |
| 3. RiskClassify | main | `risk_classify_service.py` | Deterministic (composite score vs. configured thresholds) |
| 4. RootCauseNarrate | main | `root_cause_narrate_service.py` | LLM (optional) with deterministic template fallback; prohibited-content filter always active |
| 5. InterventionRecommend | main | `intervention_recommend_service.py` | Lookup: deterministic, file-backed KB, fail-closed. Presentation: LLM (optional) with deterministic fallback; filter always active |
| 6. ReportDraft | main | `report_draft_service.py` | Deterministic string assembly (incl. renewal outlook) |
| 7. OutputValidate | post_process | `output_validate_service.py` | Deterministic regex re-scan + disclaimer |

### Data Flow

```
START → initialize → pre_process → main → {route} → post_process → finalize → END
```

No retry loop is expected in normal operation (no external I/O with transient
failure modes — no network/DB calls). `AgentStatus.ERROR` from `pre_process`
(malformed input / out-of-range value) routes directly to `finalize`,
skipping `main`/`post_process` — no report is drafted from rejected input.
`AgentStatus.ERROR` from `post_process` (prohibited-content re-scan hit) also
routes to `finalize` — a report that fails the final check is never released.

### S-1/S-3 Detection Scope

Proposal §3/§10 requires excluding "customer company name, contact name, and
contract value" — labeled "S-1" in the proposal text. Per the framework's
5-layer security model, S-1 is the framework's trust-gate layer (cannot
itself do content rejection); this domain-specific rejection is implemented
as a custom **S-2** input-content check (`_extra_security_gate_input`),
consistent with an established fleet precedent for this
proposal-terminology mismatch.

**Input side:** unlike other templates in this project line, this template's input schema
has **no free-text field at all** — all 6 fields (`dau_wau_trend_pct`,
`ticket_count`, `ticket_severity_avg`, `nps_score`,
`contract_utilization_pct`, `days_to_renewal`) are strictly numeric. Per
proposal §10 angle 5's own explicit guidance ("Reject any field value that
is a string longer than N chars where a number is expected"), strict
numeric type + range validation on ingest **is** the S-2 content check —
there is no field shape in which a company name, contact name, or contract
value could be smuggled through without failing numeric validation
outright. This is a materially simpler and more precise design than
the free-text pattern scanning used elsewhere in this project line, made possible because
the proposal itself constrains the input schema to pure numerics.

**Output side:** `output_validate_service.find_prohibited_content_violations`
re-scans the assembled report for the same 3 concrete patterns used in
prior templates (cue-gated ASCII personal/company names, monetary-value
patterns, embedded Japanese-script runs) — this is the *primary* defense
against LLM hallucination introducing such content (proposal §11 Risk #1),
since `root_cause_narrate_service`/`intervention_recommend_service`'s
optional LLM calls could in principle fabricate a company/contact name or
contract figure even though none was ever in state.

**Honest limitation:** the output-side scan is a best-effort,
defense-in-depth heuristic layer, not an exhaustive free-text detector
(mirrors a prior fleet review finding, applied proactively here from
the start).

### State Definition

| Field | Type | Producer | Consumer | Purpose |
|-------|------|----------|----------|---------|
| `dau_wau_trend_pct` | `float` | pre_process (step 1) | main (step 2) | Usage trend, e.g. -20.0 = 20% decline |
| `ticket_count` | `int` | pre_process (step 1) | main (step 2) | Support ticket count for the period |
| `ticket_severity_avg` | `float` | pre_process (step 1) | main (step 2) | Average ticket severity, 1 (low) – 5 (critical) |
| `nps_score` | `float` | pre_process (step 1) | main (step 2) | Net Promoter Score, -100 to 100 |
| `contract_utilization_pct` | `float` | pre_process (step 1) | main (step 2) | Contracted capacity actually used, 0-100 |
| `days_to_renewal` | `int` | pre_process (step 1) | main (step 6, renewal outlook) | Days until contract renewal date |
| `product_adoption_score` | `float` | main (step 2) | main (step 3) | 0-100, derived from `dau_wau_trend_pct` |
| `support_health_score` | `float` | main (step 2) | main (step 3) | 0-100, derived from `ticket_count`/`ticket_severity_avg` |
| `relationship_score` | `float` | main (step 2) | main (step 3) | 0-100, derived from `nps_score` |
| `commercial_risk_score` | `float` | main (step 2) | main (step 3) | 0-100, derived from `contract_utilization_pct` |
| `composite_score` | `float` | main (step 3) | main (report heading) | Weighted average of the 4 dimension scores |
| `risk_tier` | `str` | main (step 3) | main (steps 4-6) | One of `Red`/`Yellow`/`Green` — deterministic |
| `weakest_dimension` | `str` | main (step 3) | main (steps 4-5) | Name of the lowest-scoring dimension |
| `root_cause_section` | `str` | main (step 4) | main (step 6) | Drafted Markdown subsection |
| `intervention_section` | `str` | main (step 5) | main (step 6) | Drafted Markdown subsection |
| `report_draft` | `str` | main (step 6) | post_process (step 7) | Full assembled Markdown, pre-disclaimer |
| `output_pii_violations` | `str` (JSON-encoded `list[str]`, ADR-005) | post_process (step 7) | audit / test assertions | `"[]"` when clean; non-empty blocks release |

**State Constraints (mandatory):**
- Flat TypedDict only (primitives + JSON-serializable types) — confirmed:
  `str`/`float`/`int` only
- No JWT, API keys, credentials in State
- `InvocationContext` obtained via `InvocationContext.from_state(state)` inside `execute()` only — not stored in State (this template does not currently call any secret-gated dependency; the optional `llm` client manages its own secrets)
- No Pydantic models, dataclass, arbitrary Python objects
- **No customer company name, contact name, or contract value in any field** — proposal §3/§10 requirement; structurally impossible on the input side (all fields numeric) and re-verified at output (S-3 belt-and-suspenders re-scan)

## Security Design (S-1 → S-4)

| Layer | Implementation | Risk mitigated (proposal §11) |
|-------|---------------|-------------------------------|
| S-1 | All 3 `FunctionNode` subclasses declare `required_trust_level = TrustLevel.VERIFIED_EXTERNAL` explicitly (no implicit `ANONYMOUS`) | Restricts invocation to authenticated CRM/CS-platform callers |
| S-2 (custom) | `PreProcessNode._extra_security_gate_input()` parses the account-signal JSON and rejects (sets `status=ERROR`, does not raise) when any of the 6 fields is missing, non-numeric, or out of its documented valid range — separate from, and in addition to, the platform S-1 normalizer | No customer company name/contact name/contract value can be smuggled through a numeric field; malformed/adversarial input fails fast |
| S-3 | `PostProcessNode._extra_security_gate_output()` re-scans the assembled `formatted_output.report_markdown` independently of the step-7 execute()-level check (may raise to block entirely — defense in depth, mirrors an established fleet `SecurityGateOutputNode` pattern) | Belt-and-suspenders: catches an LLM-hallucinated company/contact name or contract figure even though none exists in state |
| S-4 | `emit_trace_event()` called at least once on the SUCCESS path of each node: `account_signals_ingested` (pre_process), `health_scored`, `risk_classified`, `llm_call` × 2 when `llm is not None` (main — configured, not necessarily successful; see correction below), `output_content_scan` (post_process) | Audit trail for accepted/processed requests (proposal §10 S-4 requirement). NOT all-path telemetry — a `pre_process` rejection (missing/non-numeric/out-of-range/fractional field) returns before `account_signals_ingested` fires, so a rejected request emits no domain event (eng-moderator T2-02, LOW, 2026-07-20; see `docs/03_test_spec.md` TC-11). Similarly, `llm_call` reflects that an LLM client was configured for this deployment, not that the call itself succeeded — `root_cause_narrate_service`/`intervention_recommend_service` fall back to a deterministic template on any LLM exception or disallowed-content hit, but `llm_call` still fires because `self._llm is not None` remains true. |
| Risk #1 (LLM root cause narrative diverges from signals, 🟡 Medium) | Health scoring, composite score, risk tier, and weakest dimension are all deterministic (never LLM-decided); `root_cause_narrate_service`/`intervention_recommend_service` discard any LLM output containing a detected company/contact name or monetary value, falling back to a safe deterministic template that explicitly cites the actual input signal values; `output_validate_service.attach_disclaimer()` prepends "AI DRAFT — NOT A FINAL DETERMINATION" to every released report | Mitigates fabricated/inaccurate narrative; grounds the narrative in cited signal values per the proposal's own mitigation design |
| Risk #2 (scoring weights/thresholds do not fit segment, 🟡 Medium) | `dimension_weights` and `risk_thresholds` are institution-configurable via `config.yaml`, validated (sum-to-1.0 / required keys present) at construction time (fail-loud, not fail-open) | An institution can calibrate weights/thresholds to its own customer segment without a code change |
| Risk #3 (missing input signals, 🟢 Low) | `parse_account_signals()` requires all 6 fields to be present and numeric — a genuinely unmeasured signal must be rejected at ingest rather than silently guessed; proposal's "report as data unavailable" design is documented as an operational data-collection responsibility, not a code-level default (see `docs/07_operation_guide.md`) | Bad/incomplete input fails fast with a clear error instead of producing a report grounded in a guessed value |

> **S-2/S-3 gate behaviour (ADR-017):** all 3 nodes are `FunctionNode` subclasses — the
> framework `@final` gate always runs automatically; extended only via
> `_extra_security_gate_input()` / `_extra_security_gate_output()`, never by overriding the
> `@final` methods themselves.

## Framework Utilization

### Shared Components Used
- [x] `InvocationContext` — reserved access point for the optional `llm` client's own secret
      handling; this template does not itself call `ctx.secrets.require()` (no required-secret
      dependency — every drafting step has a deterministic fallback)
- [ ] ConnectionPolicy — not used (no external service calls)
- [x] S-2: `_extra_security_gate_input()` on `PreProcessNode` — custom numeric type/range validation
      (see Security Design table above)
- [x] S-3: `_extra_security_gate_output()` on `PostProcessNode` — independent prohibited-content
      re-scan, may raise to block release entirely
- [x] S-4: `emit_trace_event()` — domain events on all 3 nodes (see Security Design table)

### Composition Pattern

- **Pattern**: Standalone (no `GraphNode`/`RemoteAgentNode` composition — this is a
  leaf Cat 2 template, not a composition of other templates)
- **Composition target**: n/a
- **Error propagation strategy**: n/a

## Import Isolation Confirmation
- [x] Template does not import agenticstar-platform SDK (Level 0)
- [x] Import targets: `framework/` and `shared/` only (no `agents/base/` required)
- [x] `src/services/*.py` import neither `framework` nor `shared` — pure Python domain logic only

## Class Name Consistency

| Source | Value |
|--------|-------|
| `config/agent.yaml` `agent.class` | `CustomerSuccessRenewalRiskAssessmentAccountHealthReportAgent` |
| `config/agent.yaml` `agent.module` | `src.graph` |
| `src/graph/graph.py` class name | `CustomerSuccessRenewalRiskAssessmentAccountHealthReportAgent` |
| `src/graph/graph.py` `name` property | `"CustomerSuccessRenewalRiskAssessmentAccountHealthReportAgent"` |
| `src/api/server.py` import | `from src.graph.graph import CustomerSuccessRenewalRiskAssessmentAccountHealthReportAgent` |

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|----------|----------|----------|--------|-----------|
| L1 base type | `AgentBaseGraph` | `AutonomousBaseGraph` | **A** | Fixed 7-step pipeline with deterministic termination — no autonomous think→act loop needed (Cat 2, not Cat 3) |
| Node-count reconciliation | Re-derive a 3-slot mapping independently | Follow the proposal's own explicit "AgentCore node-slot mapping" table (1 pre_process / 5 main / 1 post_process) | **B** | The proposal is unusually prescriptive here — using its exact mapping avoids an unnecessary re-derivation and any risk of disagreeing with the architect's intent |
| RiskClassify authority | LLM decides risk tier | Deterministic composite-score-vs-threshold rule decides; LLM only narrates/presents, never classifies | **B** | Risk tier directly drives management reporting and intervention urgency — a business-critical decision. `IMPLEMENTATION_LOG.md` A4: decisions with material business consequence must be deterministic; LLM is narrative-only |
| Scoring weights / risk thresholds source | Hardcoded Python constants | Institution-configurable via `config.yaml`'s `dimension_weights`/`risk_thresholds`, with defaults only as a construction-time fallback | **B** | Proposal §10/§12 explicitly calls out "dimension weighting is the key precision variable" and specifies YAML config for "dimension score thresholds" — an institution's actual customer segment determines real weights, not a fixed in-code value. `register_nodes()` validates required keys/weight-sum at construction time (fail-loud, not fail-open) |
| Scoring weight/threshold provenance honesty | Present shipped defaults as an authoritative Gainsight-derived formula | Label as illustrative defaults (equal-weight dimensions; risk-tier cut-points taken from the proposal's own explicit Red<40/Yellow 40-65/Green>65 table) requiring institution calibration; no fabricated Gainsight-proprietary-formula citation | **B** | Gainsight/Totango's exact proprietary weighting formulas are not public — presenting arbitrary equal weights as "the Gainsight formula" would be a false assurance (mirrors a prior fleet review finding, applied proactively here from the start). The risk-tier cut-points ARE taken directly from the proposal's own literal table, so those specific three numbers are not a fabricated citation — only the per-dimension scoring weights and internal formula constants are labeled illustrative |
| Intervention KB source | Hardcoded Python dict | Versioned, provenance-tagged JSON file (`src/services/kb/intervention_matrix.json`), institution-overridable via `config.yaml`'s `intervention_kb_path`, fail-closed on load/lookup failure, `provenance_verified` field required | **B** | Directly reuses an established fleet sanction-KB governance pattern (prior review lessons) — proposal §12 explicitly lists "Intervention KB construction" as a dependency still "in progress (scope in design phase)", i.e. this is exactly the kind of legally/operationally consequential reference data that must not be silently hardcoded or presented as authoritative without verification |
| `config.yaml` loading for the standalone entry point | Assume the framework auto-populates `self.config` from `config.yaml` at construction | `src/api/server.py` explicitly loads `config/config.yaml` (`_load_runtime_config()`) and passes it as `Agent(config=...)`, from the initial implementation | **B** | Empirically disproved on a prior fleet template (review round 2): `Agent()` with no `config=` argument leaves `self.config == {}` after `compile()` — this template's own entry point bypasses AgentRegistry, so it must load the file itself. Applied here from day 1 rather than as a post-review fix |
| Input-side content-rejection mechanism | Free-text pattern scanning (an established fleet pattern) | Strict numeric type + range validation only — no pattern scanning needed | **B** | This proposal's input schema (unlike other templates in this project line) has no free-text field at all; every field is numeric by design. Per proposal §10 angle 5's own explicit guidance, rejecting non-numeric/out-of-range values on ingest already fully satisfies the "no company/contact name, no contract value" input requirement — there is no field shape for such content to occupy |
| PII/prohibited-content re-scan location (step 7) | Only in `execute()` | Both in `execute()` (blocks release, sets `output_pii_violations`) and independently in `_extra_security_gate_output()` (may raise) | **B** | Defense in depth — mirrors an established fleet `SecurityGateOutputNode` pattern, independent of the step-1 ingest check |
| Composition pattern | Standalone | `GraphNode` wrapping an inner workflow | **A** | No existing template to compose; this is itself the leaf domain-workflow template (proposal §5: establishes the pattern for future SVC customer-success management templates) |
