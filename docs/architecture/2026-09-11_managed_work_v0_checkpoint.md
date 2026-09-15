# Managed-Work V0 end-of-day checkpoint — 2026-09-11

This checkpoint records the implemented state after Managed-Work V0 Iteration 2. It is a handoff summary, not a replacement for the implementation ledger, protocol files, source, tests, or frozen TARGET architecture.

## Iteration 1 — protocol and authority foundations

- DirectorTask expanded from 12 to 19 protocol fields so semantic task intent, execution linkage, targets, anchors, entities, focus, requirements, and external authority references have explicit representation.
- Strict deterministic parsing and validation preserve unknown fields for rejection, enforce required and vocabulary-constrained values, and construct immutable trusted runtime records only after validation.
- Plan protocol contradictions were corrected across finality, revision identity, dependency rules, proposal disposition, and integrity metadata.
- TaskExecution terminal semantics distinguish successful completion from failed execution and preserve deterministic terminal evidence.
- Compute topology, model roles, logical contexts, endpoint configuration, and installed hardware were corrected to match live deployment truth.

## Iteration 2 — reciprocal Normal planning

- Normal planning runs independent Gemma and Qwen proposals, Qwen assessment of Gemma, Gemma assessment of Qwen, and configured Gemma Director synthesis.
- Both proposals receive the same frozen request projection and cannot contain the other proposal before reciprocal assessment begins.
- Reciprocal assessment is constructive: agreement, strengths, weaknesses, uncertainty, missing information, questions, complementary ideas, genuine trade-offs, synthesis opportunities, and suggested changes are represented without forcing disagreement. Finding arrays may legitimately be empty.
- Models author stage-specific semantic fields. Deterministic Python assigns trusted IDs, references, authorship, timestamps, status, dependencies, integrity fields, and canonical Plan structure.
- Structured-output behavior is capability-driven. Qwen uses exact JSON Schema responses with its configured `qwen3` reasoning parser and thinking disabled for structured planning calls; DiffusionGemma remains prompt-constrained with strict deterministic post-response validation.
- Director synthesis is split into suggested-change dispositions when changes exist, overall synthesis, and semantic Plan steps. Python maps semantic numbers to trusted references and assembles the authoritative Plan protocol.
- Generic conformance repair permits the same semantic producer one representation-only repair for structural conformance, invalid references, or protocol integrity. It consumes one reasoning task and does not advance semantic iteration.
- Semantic completion permits the same producer one focused call when required meaning is missing. Python never fabricates the absent judgment, and completion does not advance semantic iteration.
- Plan acceptance is dual: deterministic structural/protocol certification precedes a configured advisory semantic assessment of the frozen architecture invariants. One Director semantic-boundary correction is permitted for identified violations, followed by structural recertification and reassessment.
- A Plan becomes the final certified passive Plan and advances to semantic iteration 3 only after both acceptance gates pass.
- The live static model-routing planning experiment produced a canonical Plan with valid protocol integrity and a compliant semantic architecture assessment. No DirectorTask, Plan step execution, TaskExecution, or ACCEPT/REVISE work occurred.

## Validation state

- Focused Normal-planning tests: 68 passing.
- Full repository suite: 118 passing.
- Python source and test compilation: passing.
- `git diff --check`: passing.
- Configured Gemma and Qwen `/v1/models` endpoints and semantic inference calls: proven live.
- CURRENT Archify source: showcase validation passes 9/9 artifact checks with zero errors and zero warnings.
- Managed-Work V0 Iteration 2: COMPLETE.

## Observed model performance

In the final routing-planning run, the two Qwen calls consumed approximately 31.26 seconds of the 37.48 seconds of recorded model latency. The seven Gemma calls consumed approximately 6.22 seconds combined. On the current deployment, Qwen therefore dominates Normal-planning wall time while DiffusionGemma is substantially faster on the RTX PRO 4500. This is an observed deployment result, not dynamic routing evidence; V0 routing remains based only on static configured capability metadata.

## Next milestone — Iteration 3

The next milestone is limited to this already-established handoff sequence:

```text
Certified Plan
→ Director selects step
→ DirectorTask
→ deterministic validation
→ Task Executive
→ configured worker execution
→ TaskExecution
→ Director ACCEPT / REVISE
```

The initial in-memory Iteration-3 execution foundation was implemented on 2026-09-15. The same session then reconciled outcomes, graph revisions, checkpoint identity, persistence/resume, frontier authorization, output contracts, and configured resource execution; the implementation ledger records the test evidence and remaining live/provider seams. Its durable design authority and frozen continuation decisions follow.

## Iteration 3 — frozen decisions

The complete recovered design record is `docs/architecture/2026-09-14_managed_work_iteration3_design_record.md`. These concise decisions are authoritative for future restart:

- The 2026-09-15 147-test in-memory DirectorTask → Task Executive → TaskExecution path is the validated execution foundation. Its bounded same-Plan REVISE controller is transitional and superseded by the revision policy below.
- Planning semantic iteration 3 marks production of the certified Plan and remains planning-only. Execution has a separately configured transition limit; no planning counter is reused or reset.
- Managed-Work V0 derives transitions from immutable Plan lineage: `@r1` is the planning-created certified Plan, every later chronological revision is exactly one execution transition, and consumed transitions equal `highest revision - 1`. No mutable transition counter or `JobContext` is introduced.
- The Director's semantic outcomes are `ACCEPT`, `REVISE`, and non-terminal `ASK_GUIDANCE`. Representation repair and transport retry are separate mechanical concerns and never mean REVISE.
- `ACCEPT` accepts execution evidence, not the already-certified Plan. Continued work creates a successor Plan revision.
- `REVISE` selects an accepted checkpoint and creates an immutable successor revision. The same `plan_id` is retained, `based_on_revision_ref` records the graph edge, revision numbers remain chronological, and failed or abandoned branches are preserved.
- The planning-certified `@r1` is the distinguished root checkpoint: certified Plan state plus trusted planning finalization/certification evidence, with no fabricated TaskExecution ACCEPT. Every checkpoint created after execution identifies both its Plan revision and a real ACCEPT TaskExecution/outcome. A null `checkpoint_outcome_ref` is valid only for the contextually proven root. No Checkpoint protocol, class, manager, or database is added.
- `ASK_GUIDANCE` persists an awaiting-guidance seam and consumes no transition until returned guidance is incorporated into a successor Plan.
- Frontier policy is persisted at job level as `USER_ONLY`, `ASK_BEFORE_FRONTIER`, or `FRONTIER_ALLOWED`. No frontier call occurs without both explicit persisted user authorization and a configured provider; a frontier model remains an adviser.
- The Director may use Vault/OKF, supplied or local sources, web research, and configured local workers as ordinary semantic resources. Task Executive and configuration resolve their mechanics through the existing DirectorTask → TaskExecution seam. No mandatory escalation order, research coordinator, intelligent router, or third manager is allowed.
- Python gates representation, trusted references, authorization, budgets, lineage, and protocol integrity. The Director decides WHAT and judges meaning. Task Executive determines HOW mechanically. Plan remains passive and ModelClient remains generic.
- The Director selects the semantic output kind (`text` or `json_object`); Python maps it to a trusted configured contract and validates only representation. Structurally valid but semantically inadequate content remains for Director judgment.
- Managed-work artifacts are immutable except for a minimal atomically replaced `resume.json`; transition use is lineage-derived and reasoning-call use is recovered from call artifacts.
- The frozen Managed-Work V0 TARGET remains unchanged.

### Original-mandate fidelity — approved and implemented 2026-09-15

The [accepted diagnosis](review/2026-09-15_request_to_plan_semantic_fidelity.md) records the observed planning-fidelity defect and the approved correction. These rules supplement the Iteration-3 frozen decisions above:

- The resolved immutable original user request is semantic authority for the objective, hard constraints, and explicit success criteria. Later Plan wording, summaries, and unresolved references cannot replace its contents. Python resolves and carries the request and verifies generated request digests before execution, persistence, and reload; Python never judges semantic equivalence or rewrites success criteria.
- Preserve the distinction: response conformance ≠ useful truthful evidence ≠ selected-work fulfillment ≠ overall-mandate fulfillment. Preserve truthful failure reporting, without silently making it alternative fulfillment. A negative answer can legitimately fulfill a diagnostic mandate; this is a semantic judgment, not a keyword rule.
- Deferred execution evidence remains an explicit dependency, uncertainty, or risk. Its absence alone does not justify invented facts, broader success, or unnecessary guidance. Known impossibility must not be certified as achievable through an invented success condition.
- The existing semantic architecture acceptance mechanism is now the shared **semantic Plan acceptance gate**, assessing both architecture fidelity and original-mandate fidelity against the full original request. Reuse the same configured advisory assessor and one same-Director semantic correction followed by reassessment. No competing assessor, manager, or protocol is introduced; existing architecture-named keys remain for compatibility.
- Both the root candidate and every successor candidate must pass this gate before publication into authoritative lineage. Successor assessment/correction also receives the real triggering execution and checkpoint context. Missing-judgment completion retains candidate, mandate, and architecture context. Representation repair, semantic completion, and semantic correction keep their distinct existing bounded mechanisms and reasoning-budget accounting.
- If bounded correction cannot produce a faithful root Plan, fail explicitly with unresolved findings; do not publish/certify `@r1` or fabricate a root checkpoint, TaskExecution, or guidance state. Resumable pre-certification ASK_GUIDANCE remains outside this patch.
- A successor that fails the gate is not published and consumes no execution transition. Preserve the prior immutable Plans and real execution/outcome, report the gate findings, and persist the existing `unresolved` state with the unchanged current Plan. This mechanical stop is not a synthetic ASK_GUIDANCE outcome or a same-Plan REVISE fallback.
- ACCEPT means the selected work legitimately fulfilled its expected result. `ACCEPT` with `continue_work=false`, and therefore completed state, additionally requires the Director to judge that the overall original mandate is fulfilled. Intermediate diagnostic success alone cannot complete a deliverable mandate; evaluation receives the original request, current Plan steps, and prior execution/outcome evidence.
- REVISE requires an authorized alternative approach within the unchanged mandate. ASK_GUIDANCE is appropriate for a material unresolved hurdle or a required decision outside Director authority. It preserves attempts/findings, evidence, uncertainty, options, recommendation, and the specific assistance needed. Permission to consult a frontier adviser does not authorize changing user requirements.

Validation for this correction is deterministic only: 68 managed-work/bootstrap tests, 140 including Normal planning, and 195 full-suite tests passed; Python compilation and `git diff --check` passed. No live fidelity, ASK_GUIDANCE, or REVISE scenario was run. Existing lineage, root-checkpoint identity, budgets, frontier policy, passive Plan, generic ModelClient, and frozen TARGET remain unchanged.
