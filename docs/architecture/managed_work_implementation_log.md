# Managed-work V0 implementation log

This ledger records only architecture-relevant progress since the latest deep review. It is not a changelog and does not replace Git history or inspection of the source being changed.

## Starting an implementation iteration

1. Read the [latest architecture review](review/2026-09-08_codex_review.md).
2. Read the implementation entries below that postdate that review.
3. Inspect the relevant Archify target/current maps in `workspace/`.
4. Inspect the actual source files involved in the requested change.
5. Treat actual source as final implementation truth wherever documentation is stale.
6. Rescan the wider repository only when the requested change genuinely requires it.

## Review cadence

Normally perform a new deep architecture review after about 5–6 meaningful managed-work implementation iterations. Review earlier when architecture materially changes, a protocol changes, a frozen assumption is overturned, implementation starts diverging from the latest Archify target, or a significant new subsystem is introduced. Compare a new review with the preceding review instead of rediscovering the project without context.

## Archify feedback loop

Before implementation, the relevant target map shows the coding agent's understanding of the requested architecture. After an architecture-affecting implementation, update the relevant current map to show what the source now implements. The comparison should expose semantic decisions leaking into Task Executive, Plan being treated as an active decision maker, extra manager/coordinator layers, incorrect model-role relationships, and bypassed protocol boundaries.

Archify is development documentation/tooling, not a Benzaiten runtime dependency. Do not regenerate maps for purely mechanical changes; update only a map whose represented architecture changed.

Current map set:

- `workspace/benzaiten_current.architecture.html` — current implemented surface
- `workspace/benzaiten_v0_target.architecture.html` — target V0 component architecture
- `workspace/benzaiten_normal_planning.architecture.html` — target Normal planning roles and flow
- `workspace/benzaiten_managed_work_runtime.html` — target managed-work runtime boundary
- `workspace/benzaiten_managed_work_v0_target.architecture.html` — frozen pre-implementation V0 target

## Baseline

- Latest deep review: 2026-09-08 Codex review, based on commit `959bdff7b83fec64ee46309db180e691f4501fb3`.
- Frozen pre-implementation target: `workspace/benzaiten_managed_work_v0_target.architecture.html`.
- Managed-work implementation entries since that review: none yet.
- Known post-review target clarification: `workspace/benzaiten_v0_architecture_delta.md` and the Normal-planning map specify reciprocal constructive assessments; the saved review's first-slice sequence specifies only Qwen's assessment of Gemma. This is a target-document change, not an implemented source change.
- Known stale documentation: the existing decision schematics contain `JobContext`, contrary to the frozen V0 boundary. They are not implementation authority.

## Entry format

### Iteration N — YYYY-MM-DD

- Goal:
- Files changed:
- Architectural effect:
- Tests/validation:
- Unresolved issue:
- Archify map changed: No, or Yes — `<map path and change>`

### Iteration 1 — 2026-09-11

- Goal: Align the DirectorTask, Plan, TaskExecution, initialization, hardware, and model-role contracts with the frozen Managed-Work V0 target; no planning orchestration or live model calls.
- Files changed: `src/director.py`, `src/orchestrator.py`, `src/task_execution.py`, `src/config.py`, `src/initialization.py`, `protocols/planning/plan_protocol_v0.json`, `protocols/execution/task_execution_vocabulary.yaml`, `workspace/.benzaiten_layout.json`, focused `smoke_tests/`, and the CURRENT Archify JSON/HTML/visual-check receipt.
- Architectural effect: The existing DirectorTask is now a strict 19-field protocol adapter; deterministic validation certifies task and terminal-execution structure; managed preparation treats `DirectorTask.action` as authoritative while the legacy action-state path remains intact. No semantic authority moved into Task Executive.
- Tests/validation: Focused suite 28 passed; full suite 47 passed; `git diff --check` passed; CURRENT Archify showcase validation passed 9/9 with zero errors/warnings and delivery succeeded. Automated browser visual-check was skipped because Chrome/Chromium is unavailable.
- Unresolved issue: No Patch 1 blocker. The reciprocal Normal-planning loop, managed ModelClient execution, TaskExecution builder, and persistence remain intentionally unimplemented for later iterations.
- Archify map changed: Yes — `workspace/benzaiten_current.architecture.json` and `.html` now show the implemented strict DirectorTask/Task Executive seam and terminal-profile validation. The frozen V0 TARGET map did not change.

### Iteration 2 — 2026-09-11

- Goal: Implement the fixed five-call reciprocal Normal-planning sequence through validated final Plan construction only; no DirectorTask generation, execution, TaskExecution, or ACCEPT/REVISE.
- Files changed: `src/director.py`, `src/planning.py`, `src/orchestrator.py`, `src/config.py`, `smoke_tests/test_normal_planning.py`, this ledger, and the CURRENT Archify JSON/HTML/visual-check receipt.
- Architectural effect: Gemma and Qwen now produce structurally isolated proposals, assess one another constructively, and feed configured Gemma Director synthesis. Deterministic projections, validation, routing, trace capture, and numeric budget enforcement surround the semantic loop; Plan remains passive.
- Tests/validation: Focused Normal-planning suite 9 passed; full suite 56 passed; `git diff --check` passed. CURRENT Archify showcase validation passed 9/9 with zero errors/warnings and delivery succeeded. Live smoke was blocked before calls because both configured endpoints refused connections. Automated browser visual-check was skipped because Chrome/Chromium is unavailable.
- Unresolved issue: Live five-call behavior remains unverified until both configured endpoints are running. DirectorTask generation, managed execution, TaskExecution construction, persistence, and ACCEPT/REVISE remain intentionally deferred to Iteration 3 or later.
- Archify map changed: Yes — `workspace/benzaiten_current.architecture.json` and `.html` now show the implemented reciprocal five-call planning path, semantic/deterministic authority split, passive final Plan, and unentered Iteration 3 execution seam. The frozen V0 TARGET map did not change.

#### Live validation follow-up — 2026-09-11

- Both configured model endpoints were started from their existing matching server profiles and passed `/v1/models` plus minimal inference checks. The first live Normal-planning run made both independent proposal calls, then correctly stopped before semantic advancement: Gemma returned JSON inside a Markdown fence, while Qwen returned visible `<think>` content and added fields outside the proposal contract. No assessment or synthesis calls were made, no retry occurred, and no task was executed.
- Added `scripts/open_dev_tabs.sh`, a development-only helper that waits for already-running Harness and Gemma services before opening their UI/docs with `xdg-open`; it does not start services or participate in Benzaiten runtime architecture.


#### Live-conformance follow-up — 2026-09-11

- Added deterministic whole-response normalization for plain JSON objects, exactly one outer `json` Markdown fence, or exactly one leading `<think>...</think>` block followed directly by a JSON object. Malformed JSON, arbitrary prose, combined/repeated envelopes, and unknown semantic fields remain validation failures. Proposal prompts now distinguish planning proposals from requested final results and require exactly the proposal fields.
- Focused tests passed 32/32 and the full suite passed 79/79; `git diff --check` passed. On the unchanged live smoke request, Gemma's outer fence was accepted, but Qwen reached its 800-token limit inside an unclosed `<think>` block and returned no JSON. Planning stopped after two reasoning calls with zero semantic advancements; no assessments, synthesis, final Plan, or execution occurred.
- Archify map changed: No — this is deterministic transport-envelope normalization and prompt conformance within the existing frozen Iteration 2 architecture.


#### Structured-output plumbing follow-up — 2026-09-11

- Verified that proposal `reason` and `proposal_reason` are distinct intentional Plan fields: `reason` explains the proposed approach, while nullable `proposal_reason` accompanies proposal-state disposition metadata (`decided_by_ref` and revision reference). Initial candidate schemas require `proposal_reason` and decision metadata to be null.
- Added generic `response_format` and `chat_template_kwargs` transport options plus exact-field JSON Schemas for all five planning stages. Capability metadata applies those schemas to Qwen; DiffusionGemma remains prompt-constrained with strict post-response validation because its vLLM endpoint explicitly rejects structured outputs for diffusion language models. Qwen now runs with the installed `qwen3` reasoning parser and disables thinking only for schema-constrained planning output.
- Recreated only the remote `benzaiten-qwen` container so its changed launch arguments took effect. Live Qwen proposal output became exact, complete JSON without reasoning leakage or extra fields. The final unchanged plumbing rerun still stopped after two calls and zero semantic advancements because Gemma emitted malformed JSON with a duplicate comma; deterministic code did not repair it. No assessments, synthesis, final Plan, or execution occurred.
- Archify map changed: No — this strengthens deterministic output plumbing within the frozen Iteration 2 architecture.

#### Semantic-ownership and assessment-semantics follow-up — 2026-09-11

- Planning models now author only stage-specific semantic content; deterministic Python supplies trusted proposal, assessment, and final-Plan protocol structure and runs the full validators after assembly. Both proposal branches assemble to the same canonical protocol shape, while Qwen uses semantic-only JSON Schema output and DiffusionGemma remains strictly prompt-constrained.
- Constructive assessment categories are exact-field arrays of zero or more non-empty findings. Empty arrays explicitly represent that no meaningful weakness, question, missing information, conflict, or other category finding was identified; the validator still rejects malformed values, unknown fields, and assessments with neither any finding nor any suggested change.
- Focused Normal-planning tests passed 46/46; the full suite passed 96/96; `git diff --check` passed. On the unchanged live fruit-sorting smoke, all five configured calls returned parseable semantic JSON with no retry: both proposals and both reciprocal assessments validated, consuming five reasoning tasks and two semantic advancements. Final synthesis was correctly rejected before Plan certification because Gemma Director accepted nonexistent suggested-change number 1 when both assessments proposed zero changes. No task was executed.
- Archify map changed: No — semantic/protocol ownership and objective empty-finding representation remain within the frozen Iteration 2 architecture.

#### Synthesis projection and conformance-repair follow-up — 2026-09-11

- Removed the static `[1]` synthesis examples, projected the exact supplied proposal, critique, and suggested-change references, and explicitly required empty change-number classifications when no suggested changes exist while retaining exact-once classification and strict invalid-reference validation.
- Wired the planning policy's generic `conformance_repair` path for structural conformance, invalid references, and protocol integrity. The original semantic producer receives its invalid output, exact deterministic issues, valid references, and semantic-preservation rules; at most one repair call consumes one reasoning task without semantic advancement, and Python revalidates without fabricating corrections.
- Focused Normal-planning tests passed 54/54; the full suite passed 104/104; `git diff --check` passed. The unchanged live fruit-sorting smoke certified a final one-step Plan on the initial synthesis, so no repair was required. It used five reasoning tasks and three semantic advancements. Calls totaled 3,753 prompt tokens, 789 completion tokens, and 4,542 tokens; recorded model latency totaled 8,767.13 ms (Gemma proposal 510.23 ms, Qwen proposal 2,117.42 ms, Qwen assessment 4,437.59 ms, Gemma assessment 380.15 ms, Gemma Director synthesis 1,321.74 ms).
- Archify map changed: No — this implements the target's bounded conformance-repair policy within the existing Iteration-2 semantic/deterministic authority split. The frozen V0 TARGET map did not change, and Iteration 3 remains unentered.

#### Focused Director synthesis-unit follow-up — 2026-09-11

- Replaced the monolithic Director synthesis artifact with focused semantic units: suggested-change disposition when changes exist, overall synthesis, and semantic Plan steps. Python maps complete dispositions to canonical change references, combines validated semantics, assigns trusted Plan/revision/step IDs and bookkeeping, and certifies the canonical Plan. Zero suggested changes skip the disposition call. All focused Director calls remain on the configured `gemma_director` context and at semantic iteration 2; only complete Plan certification advances to iteration 3.
- Added planning-policy `semantic_completion` for omitted required semantic decisions. The same semantic producer receives the incomplete artifact, exact missing decisions, valid references, and a missing-decisions-only scope; one attempt consumes a reasoning task without semantic advancement. Structural conformance, invalid references, and protocol integrity continue through the distinct one-attempt conformance-repair path. No RepairManager, CompletionManager, Router, or other manager was added.
- Focused Normal-planning tests passed 59/59; the full suite passed 109/109; Python source compilation and `git diff --check` passed. Tests cover exact-once dispositions, the zero-change path, strict nonexistent references, completion versus repair routing, same-producer context, reasoning and semantic counters, trusted Python bookkeeping, non-invention, final certification, and honest termination after invalid second outputs.
- The requested live static model-routing planning problem structurally certified in seven reasoning tasks and three semantic advancements, with three suggested changes all accepted and no semantic-completion or conformance-repair call. Total recorded model latency was 31,938.17 ms; calls used 10,195 prompt tokens, 2,429 completion tokens, and 12,624 total tokens.
- Live semantic issue: the certified Plan assigns deterministic model selection to the Director and says it returns an abstract model ID. That conflicts with the frozen authority rule that the Director selects semantic requirements while configuration and the Task Executive resolve the concrete model mechanically. The prompt projected the authority constraints, but current deterministic validation certifies protocol structure rather than this semantic claim. This must be resolved before Iteration 3; no execution work was started.
- Archify map changed: Yes — `workspace/benzaiten_current.architecture.json` and `.html` describe focused Director semantic units, Python-owned assembly, variable six/seven base reasoning calls, and completion/repair remaining at semantic iteration 2. The frozen V0 TARGET map did not change.

#### Semantic architecture acceptance follow-up — 2026-09-11

- Added a configured advisory semantic-architecture assessment after deterministic structural certification. The assessment checks the twelve frozen Director, Plan, Task Executive, routing, static-metadata, and fallback invariants without gaining decision authority. A noncompliant candidate may receive exactly one semantic boundary correction from the same configured Director, followed by canonical Python reassembly, structural recertification, and a second advisory assessment. Correction calls consume reasoning budget and remain at semantic iteration 2; only dual acceptance advances to iteration 3.
- Focused Normal-planning tests passed 68/68; the full suite passed 118/118; Python source/test compilation and `git diff --check` passed. Coverage includes compliant acceptance, concrete-model/Router/implicit-fallback violations, deterministic Task Executive/configuration language, configuration-routed assessment, exactly one correction, reasoning and semantic counters, structural certification before both assessments, successful correction, and honest second-failure termination.
- Both configured live endpoints were healthy. The requested static model-routing planning run produced a structurally certified Plan that the configured `gemma_worker` assessor accepted with zero violations, so no semantic boundary correction was required. The Director disposition artifact did require one same-producer conformance repair for malformed outer JSON; the repaired four-change classification accepted changes 1, 2, and 4 and deferred change 3. The run completed with nine reasoning tasks, three semantic advancements, one structural certification, 37,477.64 ms recorded model latency, 16,060 prompt tokens, 2,517 completion tokens, and 18,577 total tokens.
- The accepted Plan keeps the Director at semantic-requirement authority, assigns concrete resolution mechanically to configuration-driven routing logic, contains no hard-coded model branch or third intelligent manager, uses static capability metadata and deterministic priority tie-breaking only, and makes local fallback an explicit configuration entry. Historical proposal text that assigned resolution to the Director was not adopted into authoritative synthesis.
- Iteration 2 is complete. No DirectorTask was generated, no Plan step or TaskExecution was executed, and no ACCEPT/REVISE or Iteration-3 runtime work began.
- Archify map changed: Yes — `workspace/benzaiten_current.architecture.json` and `.html` now show structural certification plus configured semantic acceptance and the bounded Director correction loop. Showcase delivery passed 9/9 checks with zero errors/warnings; automated browser visual-check remained skipped because Chrome/Chromium is unavailable. The frozen V0 TARGET map did not change.

#### End-of-day architecture checkpoint — 2026-09-11

- Added `docs/architecture/2026-09-11_managed_work_v0_checkpoint.md` as the concise Iteration-1/Iteration-2 handoff, including the validated state, live endpoint evidence, observed Qwen/Gemma latency split, and the already-established Iteration-3 milestone sequence without designing or implementing it.
- Regenerated the CURRENT Archify map so Candidate Plan, deterministic structural/protocol certification, configured semantic architecture acceptance, and final certified passive Plan are distinct nodes. The one-attempt semantic-boundary correction is an explicit return to the existing Director, not another authority; future model resolution and execution remain assigned to Task Executive/configuration beyond the unentered Iteration-3 seam.
- Archify showcase delivery passed 9/9 checks with zero errors/warnings. Specification SHA-256: `bc6c5695c91dc41f8764d2359d21934aca2b50964c136fe40dead308fadca512`; HTML SHA-256: `81518e273b94fbeb6b0847d2c86d1f1e7367df9b6fb4a86ae22c6263ddb6116e`. Automated browser evidence was skipped because Chrome/Chromium is unavailable, so perceptual review remains pending.
- Documentation/architecture only: runtime behavior, tests, and the frozen Managed-Work V0 TARGET were not modified. Iteration 2 remains complete; Iteration 3 remains unentered.
