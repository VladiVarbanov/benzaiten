# Managed-Work Iteration 3 adversarial review — 2026-09-15

Historical record of the complete review delivered before the repair pass. Findings remain intact below; repair progress and validation are recorded separately in the implementation ledger.

Serious defects remain despite the **195-passing suite**.

Reviewed the combined change set `b4824ca..a628833`, including both Iteration-3 commits. The worktree was clean. I made no edits and ran no live model calls. Findings below are confirmed through source tracing and deterministic, in-memory probes—not inferred live-model behavior.

## Confirmed defects

### 1. P1 — Evaluation repair can invent the overall-completion judgment without the original mandate

**Location:** `validate_director_evaluation_semantics()` at [director.py:1456](/home/vladi/local_ai/benzaiten/src/director.py:1456); `evaluate_task_execution()` at [director.py:2123](/home/vladi/local_ai/benzaiten/src/director.py:2123).

An omitted `continue_work` is classified as a representation defect. The repair call receives the incomplete response and reference identifiers, but not the original request, selected-work context, or execution contents.

Whether work should continue is a semantic judgment—not missing punctuation.

**Reproduction:** An ACCEPT response omitted `continue_work`; the representation-repair response supplied `false`. The controller accepted it and terminated. The repair prompt contained no original mandate.

**Smallest correction:** Classify missing semantic decisions separately and use bounded, same-Director semantic completion with the complete evaluation context. Keep representation repair limited to representation. Apply this distinction to omitted decisions/reasons as well as completion.

The newly shared Plan gate’s completion context is grounded correctly; the execution-evaluation recovery path bypasses that improvement.

### 2. P1 — Prior execution/checkpoint evidence does not reach successor task selection or its worker

**Location:** `run_iteration_3()` at [director.py:2777](/home/vladi/local_ai/benzaiten/src/director.py:2777); `numbered_managed_inputs()` at [director.py:974](/home/vladi/local_ai/benzaiten/src/director.py:974); successor synthesis at [director.py:2404](/home/vladi/local_ai/benzaiten/src/director.py:2404).

After a transition, selection receives the successor Plan and original request, but no preceding execution results. Its input catalog offers the request and configured resources—not historical TaskExecution evidence.

Successor synthesis receives the triggering execution, but an earlier execution checkpoint is projected as its **Plan**, without resolving that checkpoint’s accepting execution evidence.

**Reproduction:** A unique value returned by the first worker was absent from both the second Director-selection prompt and second worker prompt.

This breaks ordinary continuation such as “use the previously accepted analysis to produce the deliverable.” Encoding that evidence informally into Plan instructions is not a reliable substitute.

**Smallest correction:** Make relevant historical execution/checkpoint evidence available through the existing trusted numbered-input mechanism. Resolve the selected checkpoint’s actual accepting evidence for successor reasoning. Preserve Director selection of which evidence to use.

### 3. P1 — Exhausted worker conformance repair still permits successful acceptance

**Location:** `_build_task_execution()` at [orchestrator.py:667](/home/vladi/local_ai/benzaiten/src/orchestrator.py:667); existing regression at [test_managed_work_iteration3.py:625](/home/vladi/local_ai/benzaiten/smoke_tests/test_managed_work_iteration3.py:625).

After both worker responses fail the trusted JSON contract, the builder records:

```text
control.status = completed
result.status = partial
validation_outcome = failed
error = null
```

The controller then permits ordinary ACCEPT/checkpoint creation.

**Reproduction:** Two non-JSON responses followed by a supplied ACCEPT judgment produced:

```text
accepted / completed / validation failed / ACCEPT
```

The existing test explicitly expects this inconsistent terminal profile.

**Smallest correction:** Exhausted structural repair should produce a validation-failed TaskExecution, preserving raw responses as failure evidence. Enforce the structural prerequisites for successful result acceptance; leave semantic reasoning about the failure to the Director.

### 4. P1 — Failures outside the successor gate discard completed work and accepted transitions

**Location:** `run_iteration_3()` around [director.py:2822](/home/vladi/local_ai/benzaiten/src/director.py:2822), [director.py:2898](/home/vladi/local_ai/benzaiten/src/director.py:2898), and its sole persistence call at [director.py:2988](/home/vladi/local_ai/benzaiten/src/director.py:2988).

Persistence happens only after the entire loop exits normally. Most stage exceptions escape before that point.

**Confirmed scenarios:**

- Worker finishes; reasoning budget prevents evaluation.
- Worker finishes; Director evaluation endpoint fails.
- Successor passes semantic acceptance; the next selection exhausts the budget.

All three made **zero persistence calls**. The last scenario loses an already-accepted successor as well as its triggering execution.

The new successor-gate failure handling covers only one portion of the lifecycle.

**Smallest correction:** Persist durable execution boundaries and preserve accumulated artifacts on explicit failure exits. Record a completed worker execution before relying on evaluation succeeding. Commit an accepted successor before invoking its next work. Do not fabricate outcomes for stages that never produced one.

### 5. P1 — Reload accepts lineage and completion states that were never validated

**Location:** `load_managed_work_state()` at [orchestrator.py:1543](/home/vladi/local_ai/benzaiten/src/orchestrator.py:1543); outcome assembly at [director.py:2259](/home/vladi/local_ai/benzaiten/src/director.py:2259).

Reload performs revision-accounting checks and partial checkpoint validation, but does not reconstruct the complete authoritative relationships:

- Successors are not passed through contextual successor validation.
- DirectorTask artifacts are read without validation.
- Task/job/step and resulting-Plan relationships are insufficiently cross-checked.
- Completed status is not verified against an explicit terminal Director judgment.

**Confirmed reloads:**

- `status=completed` with **zero TaskExecutions or outcomes**.
- A purported `@r2` with **empty steps and pending certification**, no triggering execution, and no acceptance evidence. Reload counted one transition.

There is also a persistence limitation: `continue_work` survives in the returned evaluation semantics, but is not stored in the outcome or ordinary evaluation call artifacts. Thus terminal ACCEPT and interrupted intermediate ACCEPT cannot be reliably distinguished from persisted evidence alone.

**Smallest correction:** Reuse contextual validators during reload; verify unique identities, job/task/step links, successor-trigger links and lifecycle consistency. Persist the explicit completion judgment in a linked existing artifact, then mechanically verify it before accepting `completed`. This requires no Python judgment of semantic fulfillment.

### 6. P2 — Normally certified Plans with independent steps fail before Director selection

**Location:** `numbered_managed_inputs()` at [director.py:994](/home/vladi/local_ai/benzaiten/src/director.py:994).

Normal Plan assembly assigns the original request as every step’s `target_ref`. When two independent steps are eligible, input numbering rejects that shared reference.

**Reproduction:** A two-step Plan generated through the normal deterministic planning/certification path failed with:

```text
Eligible Plan steps must not reuse target_ref.
```

No Director call occurred.

**Smallest correction:** Deduplicate input references while allowing multiple eligible steps to map to the same trusted input number. Do not impose an unsupported uniqueness constraint on Plan targets.

### 7. P2 — Recovery dispatch rejects recoverable execution/successor outputs

**Locations:** evaluation validation at [director.py:1505](/home/vladi/local_ai/benzaiten/src/director.py:1505); successor recovery at [director.py:2512](/home/vladi/local_ai/benzaiten/src/director.py:2512); repair classifier at [planning.py:1036](/home/vladi/local_ai/benzaiten/src/planning.py:1036).

Two confirmed cases terminate with `Validation issues include a non-conformance problem`:

- ACCEPT contains a checkpoint number instead of required null. The conditional-field violation is emitted as unmapped `invalid_semantics`; no representation repair runs.
- Successor synthesis omits `overall_synthesis.goal`. Its `missing_semantic_decision` is sent to representation repair, which correctly refuses it—but no semantic completion is attempted.

**Smallest correction:** Classify conditional representation inconsistencies appropriately, and route genuinely missing successor meaning through the existing grounded semantic-completion mechanism. Preserve one-attempt limits and zero transition consumption during recovery.

### 8. P2 — Reasoning consumption can reset or disappear across persistence boundaries

**Locations:** launcher default at [run_managed_work.py:82](/home/vladi/local_ai/benzaiten/src/run_managed_work.py:82); successor-gate invocation at [director.py:2591](/home/vladi/local_ai/benzaiten/src/director.py:2591); reload accounting at [orchestrator.py:1619](/home/vladi/local_ai/benzaiten/src/orchestrator.py:1619).

Two confirmed bookkeeping gaps:

- Normal planning consumed seven calls; invoking the launcher without its optional count argument passed **zero** into execution.
- A failed successor-assessor invocation produced in-memory consumption **5**, but the highest persistable call number was **4**. The call record is appended only after a response returns, while reload reconstructs consumption from those records.

**Smallest correction:** Recover prior consumption from trusted planning records, or require an explicit count until that handoff exists. Record attempted model calls—including failed attempts—with their assigned reasoning number before returning an unresolved result. Do not introduce another mutable transition counter.

### 9. P2 — Re-persisting unchanged history violates its own immutable-artifact check

**Location:** `persist_managed_work_run()` at [orchestrator.py:1373](/home/vladi/local_ai/benzaiten/src/orchestrator.py:1373).

Every persistence call replaces historical execution timestamps with the new `written_at`, then submits those changed objects to `_write_json_once()`.

**Reproduction:** Persisting the identical run at two timestamps raises `FileExistsError` on the existing TaskExecution.

This prevents idempotent retry and would block continuation that carries previously persisted executions.

**Smallest correction:** Preserve already-established artifact timestamps/content. Assign persistence metadata once; update only the passive resume pointer for later operational progress.

## Test gaps and remaining risks

The confirmed cases above are missing from the suite; the twice-malformed-worker test actually encodes the problematic behavior. Add regressions at the combined controller/persistence boundaries, not only isolated builders.

A separate **carry-over grounding risk** remains in Normal planning: disposition/overall/step semantic-completion calls pass request contents and reference catalogs, but omit the proposal/assessment or synthesis context needed for some missing judgments. See [director.py:3725](/home/vladi/local_ai/benzaiten/src/director.py:3725). This predates the new shared gate; I have not established a resulting live semantic failure.

No style or broad-refactoring recommendations are included.

## What remains sound

- ModelClient and frozen TARGET are unchanged across the review range.
- No JobContext, third intelligent manager, hidden fallback, or active same-Plan REVISE controller was found.
- Ordinary semantic calls receive the original request; generated request digests are checked. The important exceptions are recovery/context paths described above.
- Successful successor publication preserves chronological revisions, immutable prior Plans, root/execution checkpoint distinctions, and lineage-derived transitions.
- Failed successor semantic acceptance itself correctly withholds publication.
- Frontier authorization remains operationally separate from permission to change the mandate.

## Validation limits

I reran the full deterministic suite: **195 passed**.

Still not live-validated: the new mandate-fidelity behavior, semantic REVISE and backtracking, execution ASK_GUIDANCE, resource execution, and Qwen as the selected execution worker. Frontier-provider behavior and agent-process execution remain unimplemented/configuration-dependent.

ASK_GUIDANCE currently provides a reloadable waiting record—not an implemented answer-to-successor continuation. Returned-guidance incorporation and resumable pre-certification guidance remain explicitly deferred.
