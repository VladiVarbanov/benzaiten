# Managed-Work V0 Iteration-3 design record — 2026-09-14

This document preserves the complete substantive Iteration-3 design recovered on 2026-09-15. It is the detailed authority behind the concise frozen decisions in `2026-09-11_managed_work_v0_checkpoint.md`. The implementation ledger remains the record of what source code actually implements.

## Frozen architectural boundary

- The Director decides **what** semantic work should happen and judges whether evidence is adequate.
- Deterministic Python owns trusted IDs, references, timestamps, schema validation, authorization checks, numeric budgets, lineage checks, and protocol assembly.
- Task Executive determines **how** an authorized DirectorTask is executed through configuration.
- Plan remains passive data. It is never an active manager.
- ModelClient remains a generic transport client.
- No `JobContext`, graph database, Checkpoint manager, research coordinator, intelligent router, or third semantic manager is introduced.
- The frozen Managed-Work V0 TARGET remains unchanged.

## 1. Planning iterations and execution transitions

Normal planning's existing three semantic iterations are planning-cycle only. They end when a certified Plan is produced and must not become the managed job's lifetime semantic budget.

The execution phase has a distinct deterministic budget dimension:

```text
planning iteration
    = deliberation toward a certified Plan

execution transition
    = movement from one Plan semantic state/revision to another
      after execution evidence, revision, or incorporated guidance
```

Python enforces the configured execution-transition maximum. The Director determines whether meaningful semantic continuation or revision is needed.

Managed-Work V0 uses a lineage-derived budget rather than another mutable counter:

```text
@r1 is always the planning-created certified Plan.
Every later chronological Plan revision represents exactly one execution transition.
execution transitions consumed = highest chronological revision - 1
```

Consequences:

- `@r1` consumes zero execution transitions.
- `@r2` consumes one.
- `@r4` based on `@r1` consumes three even though it backtracks.
- `ASK_GUIDANCE` without a new Plan consumes no transition.
- Terminal `ACCEPT` without further semantic work consumes no transition.
- `ACCEPT`, `REVISE`, or incorporated guidance followed by a successor Plan consumes one transition.
- The configured V0 default is three execution transitions.
- Existing reasoning-call accounting continues across the execution seam and is not reset. On resume it is recovered from persisted call artifacts.

If a future architecture permits administrative or non-execution Plan revisions, this V0 accounting rule must be revisited rather than silently generalized.

## 2. Post-execution outcomes

The one semantic decision vocabulary is:

```text
ACCEPT
REVISE
ASK_GUIDANCE
```

`ASK_USER` and `ASK_FRONTIER` are not separate semantic decisions. Guidance target and authorization are attributes of `ASK_GUIDANCE`.

The smallest useful outcome record is equivalent to:

```json
{
  "id": "<trusted-outcome-id>",
  "decision": "<ACCEPT | REVISE | ASK_GUIDANCE>",
  "decided_by_ref": "<configured-director-context>",
  "reason": "<director-semantic-reason>",
  "evidence_refs": [],
  "checkpoint_revision_ref": "<accepted-or-backtracking-revision-ref>",
  "checkpoint_outcome_ref": "<accepting-outcome-ref>",
  "resulting_plan_ref": null,
  "guidance": null,
  "created_at": "<python-generated-utc-timestamp>"
}
```

For `ASK_GUIDANCE`, `guidance` is equivalent to:

```json
{
  "hurdle": "<semantic>",
  "materiality": "<semantic>",
  "attempts": [
    {
      "description": "<semantic>",
      "established": "<semantic>",
      "evidence_refs": []
    }
  ],
  "remaining_unresolved": "<semantic>",
  "evidence_refs": [],
  "options": [],
  "recommendation": "<semantic>",
  "question": "<semantic>",
  "target": "<user | frontier>",
  "policy": "<USER_ONLY | ASK_BEFORE_FRONTIER | FRONTIER_ALLOWED>",
  "frontier_authorized": false
}
```

Authority is split as follows:

- The Director authors the semantic decision, reason, evidence selection, hurdle, materiality, attempts and findings, unresolved issue, options, recommendation, smallest useful question, and requested target.
- Python assigns IDs, timestamps, trusted references, configured policy, actual target, and authorization state.
- With no configured frontier provider, the actual target remains the user regardless of policy.
- `resulting_plan_ref` is populated only after a valid successor Plan exists.
- No separate Evaluation, AskUser, or AskFrontier protocol is introduced.

### ACCEPT

`ACCEPT` does not mean “accept the Plan”; the Plan was already certified. It means the TaskExecution result sufficiently satisfies the expected semantic result.

Record the accepted execution state as a checkpoint. If further semantic work follows, the Director creates a successor Plan state rather than silently mutating the current Plan.

### REVISE

`REVISE` is semantic. It is neither a transport retry nor representation repair.

The Director selects an earlier accepted checkpoint and creates a new Plan state from it. The current accepted Plan remains unchanged, and the failed branch plus TaskExecution evidence remain preserved.

### ASK_GUIDANCE

`ASK_GUIDANCE` is non-terminal. The managed task remains active and resumable.

The user may answer the same technical or reasoning question that could be sent to a frontier adviser. The user controls frontier escalation through:

- `USER_ONLY`: always ask the user.
- `ASK_BEFORE_FRONTIER`: ask the user whether this hurdle may be sent upward.
- `FRONTIER_ALLOWED`: after reasonable authorized resources have been exhausted, the Director may request frontier advice when a provider is configured.

No frontier call occurs unless persisted user authorization and a configured provider both exist. A frontier model is an adviser, never a replacement Director.

After guidance returns:

```text
guidance → evidence/context → Director reasoning → successor Plan → continue
```

For the minimum Iteration-3 implementation, `ASK_GUIDANCE` may stop at a persisted and resumable user-guidance seam when no frontier provider exists. No provider is invented.

## 3. Accepted checkpoint identity

An accepted checkpoint is not merely a Plan revision. It identifies:

```text
accepted Plan revision + accepting TaskExecution/outcome evidence
```

The planning-created certified `@r1` is the distinguished root checkpoint. It is identified by the certified Plan revision plus its trusted planning finalization and deterministic certification evidence. It does not require, and must never fabricate, a TaskExecution ACCEPT outcome.

Every checkpoint created after execution identifies both the Plan revision and a real ACCEPT TaskExecution outcome. Therefore:

```text
root checkpoint
    = certified Plan state + trusted planning certification evidence

execution checkpoint
    = Plan state + real ACCEPT execution evidence
```

The root remains semantically distinct from an execution-accepted checkpoint. A first execution may truthfully REVISE and branch from `@r1` before any execution checkpoint exists.

Both references must otherwise be preserved. The V0 outcome representation uses `checkpoint_revision_ref` and `checkpoint_outcome_ref`. A null `checkpoint_outcome_ref` is legal only for the distinguished root, with contextual validation proving that the referenced Plan is the planning-certified `@r1`. Every non-root checkpoint reference must resolve to a real ACCEPT outcome.

```text
Plan r1
   ↓
TaskExecution E1
   ↓
ACCEPT outcome O1   ← checkpoint

Plan r2
   ↓
...
```

Backtracking to `O1` therefore identifies both the semantic state and the evidence already accepted. No Checkpoint class, protocol, manager, or database is introduced.

## 4. Plan graph and lineage semantics

Graph behavior is represented through ordinary Plan references:

- One managed mandate keeps the same `plan_id`.
- Each `revision_ref` is a Plan semantic state/node.
- Revisions increase chronologically.
- `based_on_revision_ref` identifies the accepted checkpoint Plan from which the new node descends.
- A later revision may be based on a much earlier accepted revision.
- Abandoned or failed branches remain immutable historical evidence.
- `parent_plan_ref` remains for genuinely separate Plan identity, not ordinary backtracking.

```text
plan-A@r1 → plan-A@r2 → plan-A@r3
    │                           × semantic dead end
    │
    └──────────────────────→ plan-A@r4
                              based_on = plan-A@r1
```

“New step = new Plan” means a new Plan revision/state node, not a new managed mandate and not mutation of the current artifact.

## 5. Director resources and escalation

Whenever semantically useful, the Director may normally use:

- its own configured local reasoning;
- Knowledge Vault / OKF;
- available supplied or local sources;
- internet research;
- other configured local workers.

These are ordinary resources, not a mandatory escalation sequence. The Director should request upward guidance only when reasonable authorized local and evidence avenues have been exhausted and a material uncertainty remains.

Retrieval and search mechanics belong to Task Executive and configuration. No research coordinator or intelligent routing layer is introduced.

`planning_policy.question_policy.resolution_order` is stale if it hard-codes an escalation order or places a higher model before the user. Iteration 3 must replace that contradiction with the user-controlled policy.

A model-backed worker is acceptable for the first live proof. Iteration 3 is not architecturally complete until the same DirectorTask → Task Executive → TaskExecution mechanism can represent and execute configured resource/retrieval work. Agent or tool roles may initially report unsupported mechanics explicitly, provided the seam remains generic and no fallback is invented.

## 6. Minimal Director task selection

The Director's semantic selection shape is:

```text
selected_step_number
capability
participant_role
objective
instruction
action
selected_input_numbers
anchors
entities
focus
reason
requirements
acceptance
output_contract_kind
```

The Director sees the certified current Plan; numbered accepted checkpoints; relevant TaskExecutions; numbered evidence, source, OKF, and guidance references; semantically named available resources and worker roles; and remaining numeric limits. It does not see endpoints, hosts, filesystem paths, model IDs, or routing details.

Python maps semantic numbers and keys into trusted task identity, job, work kind, exact Plan revision, selected step, validated inputs, output-contract reference, and external authority fields. The existing DirectorTask protocol remains unchanged.

One same-Director representation repair is permitted. It may not change the selected semantic work.

## 7. Minimal Director evaluation

The focused semantic result contains:

```text
decision
reason
evidence_numbers
continue_work
backtrack_checkpoint_number
guidance
```

Conditional behavior:

- `ACCEPT`: the current revision becomes an accepted checkpoint; `continue_work` determines whether successor Plan semantics are requested.
- `REVISE`: a valid numbered accepted checkpoint is required and successor Plan semantics are always requested.
- `ASK_GUIDANCE`: complete guidance semantics are required, no immediate successor is created, and execution pauses at the persisted resume seam.
- Python maps evidence and checkpoint numbers to trusted references.
- One same-producer representation-only repair is allowed for malformed evaluation.
- A structurally valid but intellectually poor evaluation is not rejected by Python.

Successor Plan semantics are obtained through a separate focused Director call, reusing existing synthesis and Plan-step semantic shapes.

## 8. Task Executive invocation and output contracts

The existing orchestrator's focused managed-task execution function:

- revalidates the complete DirectorTask;
- cross-checks job, Plan revision, selected step, action, inputs, and output contract;
- resolves `participant_role` through configuration;
- resolves the output contract mechanically;
- renders a bounded worker prompt from the validated task and referenced inputs;
- invokes the configured logical model context through the generic ModelClient;
- applies structural output validation;
- permits one same-worker representation repair when malformed;
- builds a completed or failed TaskExecution.

The first live slice supports configured model-backed execution. Configured agent or tool roles remain representable but fail explicitly as unavailable until mechanics exist. There is no fallback worker or automatic routing. ModelClient does not change.

A small deterministic output-contract registry initially supports `text` and `json_object`. The Director chooses the semantic output kind; Python resolves it to a stable contract reference and structural validator. For `json_object`, Python verifies that the response is a JSON object and stores it as JSON. Python does not decide whether its keys, argument, or conclusion are semantically correct.

## 9. TaskExecution assembly

TaskExecution support includes protocol and vocabulary loading; exact validation; success and failure builders; configured execution trace assembly; authorization; Plan/revision/step validation; expected-result snapshot; result/error profiles; output-contract validation evidence; and Director outcome validation and recording.

For direct model calls, `trace.deployment.agent` may be null. Transport and structural failures become failed TaskExecutions. Semantically inadequate but structurally valid results remain completed until the Director returns `REVISE`.

## 10. Successor and backtracking Plan assembly

Add a focused successor assembler and generalized revision validation to planning support.

Inputs:

- immutable current Plan history;
- selected accepted checkpoint Plan;
- Director successor semantics;
- triggering TaskExecution and outcome references;
- next chronological revision number.

Behavior:

- preserve `plan_id`;
- assign the next chronological `revision` and `revision_ref`;
- set `based_on_revision_ref` to the selected checkpoint revision;
- retain `parent_plan_ref`;
- create revision-qualified, non-reused step IDs;
- append trusted decision and revision records;
- include triggering execution/outcome references in decision artifact references;
- replace only the new Plan artifact's current semantic fields and steps;
- never edit prior Plan artifacts.

Validation enforces chronological uniqueness, a valid accepted-checkpoint ancestor, acyclic lineage, current-revision selection, and revision-qualified non-reused step IDs. No Plan protocol field additions are required.

## 11. Persistence and resume

The managed-work layout is:

```text
workspace/artifacts/managed_work/{job_ref}/
    request.json
    plans/rev-0001.json
    tasks/{task_id}.json
    executions/{execution_id}.json
    calls/{call_id}.request.json
    calls/{call_id}.response.json
    resume.json
```

Immutable protocol artifacts are written once. `resume.json` is the only atomically replaced pointer and contains operational state only:

```text
job_ref
current_plan_ref
accepted_checkpoint_ref
pending_guidance_outcome_ref
status: active | awaiting_guidance | completed | unresolved
guidance_policy
frontier_authorized
updated_at
```

It contains no semantic content, mutable transition counter, routing decision, or management behavior. Execution transitions are recovered from Plan revisions; reasoning calls are recovered from call artifacts. The user may change the persisted guidance policy later.

Guidance detail remains within the TaskExecution outcome. No guidance database is introduced.

## 12. Minimal file-level implementation plan

Runtime and contracts:

- `src/config.py`
- `src/director.py`
- `src/orchestrator.py`
- `src/task_execution.py`
- `src/planning.py`
- `protocols/execution/task_execution_protocol_v0.json`
- `protocols/execution/task_execution_vocabulary.yaml`
- `protocols/planning/planning_policy.yaml`
- `workspace/.benzaiten_layout.json`

Bootstrap:

- `src/run_managed_work.py`

Tests extend DirectorTask, TaskExecution, Task Executive, managed execution lifecycle, Plan lineage, initialization, and a separate live managed-execution smoke.

After implementation, update the implementation ledger and CURRENT Archify source/HTML/validation receipt. Do not modify the frozen TARGET.

Intentionally unchanged:

- `src/model_client.py`
- `src/structures.py`
- `src/communication.py`
- legacy communication validator/protocol;
- DirectorTask and Plan protocol field inventories;
- document-preparation and knowledge-extraction paths.

## 13. Required proof tests

### ACCEPT

- Semantic selection cannot supply trusted IDs or concrete routing.
- Configured execution routes through Task Executive/configuration.
- Structurally valid output reaches Director evaluation.
- `ACCEPT` records the current revision plus accepting outcome as the checkpoint.
- Terminal acceptance creates no Plan and consumes no transition.
- Continued work creates exactly one successor revision.

### REVISE

- Semantic inadequacy is returned by Director reasoning, not Python.
- The original accepted Plan remains byte-for-byte unchanged.
- A new chronological revision may be based on an earlier accepted revision.
- The failed branch and TaskExecution remain persisted.
- The successor revision consumes exactly one execution transition.

### ASK_GUIDANCE

- Complete guidance content is required.
- Default policy resolves the actual target to the user.
- No frontier call occurs without authorization and a provider.
- No Plan or transition is created while waiting.
- `resume.json` points to the pending guidance outcome.
- Reloading persisted artifacts reconstructs the resumable state.

### Boundary and regression

- Malformed task selection, worker result, and Director evaluation each receive at most one same-producer representation repair.
- Semantic disagreement never enters conformance repair.
- Execution-transition and reasoning budgets are mechanically enforced.
- No endpoint or concrete-model branch enters Director logic.
- No semantic choice enters Task Executive.
- Existing Iteration-1/2 behavior and the 147-test Iteration-3 foundation remain green.
