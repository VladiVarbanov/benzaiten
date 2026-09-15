# Request-to-Plan semantic fidelity diagnosis — 2026-09-15

Status at recording: diagnosis accepted; implementation authorized separately below. This record preserves the complete diagnosis delivered before editing. Its findings describe the checkout and available evidence at that time, not later implementation.

## Accepted diagnosis

The defect starts in model-authored planning semantics and escapes a gate that checks architecture but cannot compare the Plan with the original request. Python preserves the broadened semantics. Execution judgment and successor synthesis then have the same missing-request problem.

I inspected the local checkout, including its uncommitted changes. No files were changed, tests rerun, or live models launched. The 178/55 test counts remain reported results.

### 1. Root-cause findings

#### Where the broadening appeared

The saved Plan contains enough proposal and assessment history to trace the earliest visible change:

| Stage | Evidence from this candidate |
|---|---|
| Gemma proposal | Says “Output either a feasible configuration … or a precise incompatibility report.” This is the earliest visible loss of the distinction between fulfillment and failure reporting. |
| Qwen proposal | Preserves the feasible configuration as the expected result in `main_points`, but its rationale adds “unless no configuration is possible,” leaving the distinction ambiguous. |
| Qwen assessment of Gemma | Discusses how to handle incompatibility reports, missing files, and validation methods. It does not challenge the success-condition broadening. |
| Gemma assessment of Qwen | Praises both the feasible expected output and truthful failure reporting. It does not explicitly protect the exclusion of failure reporting from successful fulfillment. |
| Director synthesis | Adopts the alternative into `steps[0].expected_result` and `validation`. This is the definitive promotion into success criteria. |
| Semantic acceptance | Records `compliant: true`, with no violations. |

The proposal’s alternative output wording alone does not conclusively prove it intended both outputs as success. The final expected result and validation do.

Sources: saved [proposals](/tmp/benzaiten-live-revise.YBH9mv/certified-plan-evidence-final.json:122), [reciprocal assessments](/tmp/benzaiten-live-revise.YBH9mv/certified-plan-evidence-final.json:68), [final step](/tmp/benzaiten-live-revise.YBH9mv/certified-plan-evidence-final.json:257), and [assessment record](/tmp/benzaiten-live-revise.YBH9mv/planning-evidence-final-summary.json:7).

#### The original constraint reaches early planning calls, then disappears

Current call construction shows:

- Both independent proposals receive the same complete `frozen_request`.
- Both reciprocal assessments receive that complete request and their selected proposal.
- Change disposition, overall synthesis, and Plan-step synthesis also receive the complete request.
- Final semantic assessment and semantic correction receive **no original request contents**.

These are explicit projections in [proposal and assessment rendering](../../../src/planning.py#L669), [synthesis rendering](../../../src/planning.py#L780), and [assessment/correction rendering](../../../src/planning.py#L916). The actual controller passes those messages in [run_normal_planning](../../../src/director.py#L3209).

The gate receives `candidate_plan` and twelve architecture invariants. The Plan contains a hashed request reference, model-authored summaries, and historical proposals—not the original request text. Nothing resolves that reference before the assessor call at `src/director.py:3490`.

Therefore the early error cannot be attributed simply to withholding the constraint from all models. Early models received it; the final gate lacks both the comparison input and an explicit fidelity criterion.

#### The acceptance gate checks the wrong scope for this failure

The frozen invariants concern Director/Task Executive authority, passive Plans, routing, managers, and fallback. They do not cover preservation of the user’s objective or success criteria.

The correction prompt is likewise restricted to architecture violations. Its scope is enforced by both `protocols/planning/planning_policy.yaml:211` and a literal policy check in `src/director.py:3538`.

Also, `normal_policy_projection()` exposes only the planning level, iteration semantics, convergence policy, and numeric budget. Adding an unused YAML rule would not reach the models. See `src/planning.py:400`.

#### Python does not introduce the broadening

`assemble_final_plan()` copies model-authored `goal`, `expected_result`, and `validation` directly. Assessment summaries concatenate model findings; they are not additional model summaries.

Relevant functions: `src/planning.py:1835 assemble_final_plan` and `src/planning.py:1336 assemble_assessment`.

The observed problem belongs in semantic assessment and correction. A Python rewrite of `expected_result` would cross the frozen authority boundary.

#### Execution and successor synthesis can propagate the same error

Three downstream gaps are concrete:

1. **Selection** receives current Plan semantics and input descriptors, without the original mandate contents. See `src/director.py:724 render_director_task_selection_messages`.
2. **Evaluation** receives the Plan goal, selected step, DirectorTask, and execution evidence. Its instruction is to judge against the certified step. It receives neither the original request nor a view of the other Plan steps. See `src/director.py:1637 render_director_evaluation_messages`.
3. **Successor synthesis** says “Preserve the managed mandate,” but receives only current/checkpoint Plan projections and execution/outcome evidence. Successors subsequently receive structural/lineage validation without the existing semantic acceptance gate. See `src/director.py:2312 request_successor_plan_semantics` and `src/director.py:2727`.

There is also a completion ambiguity: `ACCEPT` with `continue_work=false` becomes `accepted`, which persistence maps to `completed`. The model prompt does not explicitly require overall mandate fulfillment before choosing that combination. See `src/director.py:2262` and `src/orchestrator.py:1395`.

**Hypothesis:** the models favored robust “solution-or-failure-report” planning, and later prompts reinforced consistency with that synthesis. The artifacts support this interpretation, but cannot establish the models’ internal cause.

### 2. What the artifacts prove—and their limits

The original artifact is still available. Its SHA-256 matches the previously reported value:

`9215719cd7af14d5700cd37d95025957b1f04b6338dcda66f9886662eabcb745`

The saved request snapshot, Plan, and summary establish:

- The initiating request explicitly excluded incompatibility reporting as alternative fulfillment.
- The certified candidate nevertheless included that alternative.
- Both reciprocal critiques survived in the Plan; neither challenged that distinction.
- The recorded architecture assessor accepted it.
- The recorded representation repair only wrapped change dispositions into valid JSON. It did not change the success condition.

The saved bundle does **not** contain complete raw prompts and responses for every historical call. Current source establishes how those calls are constructed; it does not substitute for a complete historical transport trace.

No execution was started for this candidate. There is no evidence of a live ACCEPT, REVISE, ASK_GUIDANCE, or successor from it.

### 3. Proposed shared semantic rule

I recommend one policy section, explicitly projected into the relevant prompts:

> Preserve the user’s objective, hard constraints, and explicit success criteria. Choose or revise approaches within that mandate; do not silently relax requirements or redefine fulfillment.
>
> Distinguish response conformance, useful truthful evidence, fulfillment of the selected work, and fulfillment of the overall objective.
>
> Preserve truthful reporting of impossibility, incompatibility, missing evidence, and unsuccessful attempts. Such reporting fulfills the objective only when the user’s mandate makes it a valid answer. A diagnostic objective may legitimately be fulfilled by a negative finding.
>
> Represent deferred evidence as a dependency, uncertainty, or risk. Do not invent its contents or broaden success because it is unavailable. When known evidence rules out fulfillment, do not present the current approach as achievable.
>
> ACCEPT requires fulfillment of the selected work’s legitimate expected result. Completion additionally requires fulfillment of the overall mandate.
>
> REVISE requires an authorized successor approach that preserves the mandate. ASK_GUIDANCE applies when a material unresolved hurdle remains or continuation requires authority the Director lacks. Seeking adviser input does not authorize changing user requirements.

The prompts should additionally require the Director’s existing `reason` to explain:

- what the result establishes;
- whether it fulfills the selected work;
- what remains for the overall objective;
- why continuation is authorized, or what guidance is required.

#### Gate changes

Extend the existing assessor to compare the candidate’s authoritative semantics with the **complete original request**, alongside the existing architecture invariants.

Use the existing findings shape:

```text
compliant
violations:
    finding
    affected_step_or_field
```

A fidelity finding should identify the relevant request clause and conflicting Plan field within `finding`. No new semantic classification field is necessary.

Reuse the existing one Director correction, structural reassembly, and reassessment. Correct the identified fidelity violation while preserving truthful failure instructions and unaffected semantics.

A second unsuccessful semantic assessment must prevent final acceptance.

### 4. Minimal proposed patch scope

| File | Proposed change |
|---|---|
| `protocols/planning/planning_policy.yaml` | Add the shared mandate-fidelity rule; extend semantic acceptance/correction scope to architecture and request fidelity. |
| `src/planning.py` | Project that rule into proposals, reciprocal assessment, disposition, synthesis, and semantic acceptance/correction. Add required original-request input to the gate and correction renderer. Preserve assembly semantics. |
| `src/director.py` | Pass the original request through the existing gate; update the enforced correction scope. Supply resolved mandate contents to execution selection, evaluation, and successor synthesis; clarify outcome/completion semantics. |
| `src/orchestrator.py` | Add the smallest mechanical request-resolution check using the existing persisted input mapping, including checking the generated request digest where applicable. No semantic interpretation. |
| Existing focused test files | Add projection, gate, correction, outcome, persistence, and lineage regressions described below. |
| Checkpoint and ledger, after approval | Record the approved rule and only behavior actually implemented and validated. |

The original request already has a storage route: Normal planning generates `current_work_ref` from its contents, and managed persistence stores `resolved_inputs` in immutable `request.json`. Reuse that route; resolve the root request independently of later Plan wording. Missing mandate contents must be reported explicitly, rather than reconstructed from a Plan summary. See `src/director.py:3332` and `src/orchestrator.py:1287`.

I also recommend reusing the expanded semantic gate for successor candidates **before publishing the successor revision**. A prompt alone would leave a known bypass around fidelity assessment. This uses the same configured assessor and Director correction, charges existing reasoning budgets, and creates only one transition when the accepted successor is published.

No Plan, DirectorTask, or TaskExecution field addition is needed for these judgments. Existing `continue_work`, guidance content, and checkpoint fields are sufficient.

#### Genuine limitation: unresolved planning has no resumable seam

After a second failed semantic assessment, `run_normal_planning()` raises `ValueError`; it does not return or persist an awaiting-guidance planning state. See `src/director.py:3598`.

The existing execution guidance seam requires a certified root and a real TaskExecution outcome. It cannot truthfully represent a planning failure before `@r1`. See `src/orchestrator.py:1222`.

For this narrow correction, I recommend retaining explicit failure with unresolved fidelity findings and withholding final acceptance. A resumable pre-certification guidance mechanism would require a separately reviewed representation change.

### 5. Regression tests and later live validation

#### Deterministic regression coverage

These tests verify projection and controller behavior using supplied model decisions; they do not prove model reasoning.

| Case | Required regression |
|---|---|
| **A — Deliverable** | Every relevant prompt receives the original success condition and shared rule. Corrected semantics preserve feasible-configuration success and truthful failure reporting separately. |
| **B — Broadening** | Supply a model assessment identifying the observed alternative-success violation. Verify one Director semantic correction and reassessment; persistent noncompliance blocks final acceptance. |
| **C — Diagnostic objective** | A feasibility-assessment mandate and compliant negative-answer candidate pass when the supplied semantic assessment accepts them. No Python phrase rejection. |
| **D — Guidance** | Completed impossibility evidence plus a Director ASK_GUIDANCE decision produces complete guidance, persisted awaiting state, zero transitions, and successful reload. Adviser authorization remains separate from mandate authority. |
| **E — Revision** | An authorized alternative produces REVISE, a faithful successor, unchanged prior artifacts, correct checkpoint links, and exactly one transition. Test successor fidelity rejection/correction too. |
| **F — Deferred evidence** | Prompts preserve explicit unknowns and dependencies. No invented constraint contents or automatic escalation is introduced by Python. |

Also test intermediate ACCEPT with `continue_work=true`, and ensure the evaluation prompt distinguishes that acceptance from overall completion. Existing correction and guidance tests provide the starting fixtures.

#### Separately: live-validation plan, after implementation approval

Freeze and preserve the requests before running. Record every attempt and actual prompt/response, including failed runs.

1. **Fidelity assessment:** present the saved broadened candidate and exact original request to the expanded semantic gate. Observe whether it identifies the violation and whether bounded correction succeeds.
2. **Legitimate negative answer:** use an explicit feasibility-assessment objective and authoritative incompatible constraints. A sound negative answer may satisfy it.
3. **ASK_GUIDANCE scenario:** require a feasible configuration; reveal incompatible mandatory constraints during execution with no authorized relaxation. Observe the Director’s decision and persist it.
4. **REVISE scenario:** invalidate a specific planning assumption while leaving an explicitly authorized alternative approach available. Observe whether the Director revises within the unchanged mandate.
5. Verify artifacts, preservation, transition accounting, and resume state for whatever outcome actually occurs.

ASK_GUIDANCE and REVISE should remain separate proof cases. An unexpected outcome is a result to inspect, not a reason to keep reshaping the request.

### 6. Decisions for review

Two scope choices need approval:

- **Include successor semantic assessment now:** recommended, so revisions cannot bypass the new fidelity gate. It adds reasoning calls within existing budgets.
- **Leave pre-certification guidance persistence outside this patch:** recommended. Report unresolved fidelity explicitly after bounded correction; do not create a synthetic root or execution outcome.

The execution-time guidance seam already supports the requested evidence/options/question record and persisted waiting state. Incorporating returned guidance remains a previously documented later seam.

Analysis complete. I’ll wait for approval before editing or running live validation.

## Subsequent user approval

Both recommendations were approved. The existing semantic architecture mechanism is conceptually the semantic Plan acceptance gate, covering architecture fidelity and original-mandate fidelity with the same configured assessor and Director correction. ACCEPT means selected-work fulfillment; completed state also requires Director judgment that the overall original mandate is fulfilled. The immutable resolved request remains semantic authority. Implement incremental deterministic regressions, update the checkpoint and ledger after validation, and stop before live scenarios. Frozen TARGET remains unchanged.

