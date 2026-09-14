• ## 1. Current architecture discovered

  ### Repository baseline

  - Branch: master, tracking origin/master
  - HEAD: 959bdff7b83fec64ee46309db180e691f4501fb3
  - Recent relevant history:
      - f8aa6f5 introduced the current two-PC inference baseline, DirectorTask, TaskExecution, and split
        communication protocols.

      - d987b06 / 959bdff stabilized the Qwen vLLM image configuration.

  - Tests: 26 passed in 0.09s
  - git diff --check: clean
  - This review made no repository changes.

  Pre-existing PC1 working-tree state:

  A  docs/decison_schematic.md
   M smoke_tests/test_model_configuration.py
   M src/config.py
   M src/gemma_server.py
   M src/structures.py
  ?? decison_schematic.md
  ?? prompts/interests_context.md

  These are user-owned. In particular, both decision schematics contain JobContext; that conflicts with the now-
  frozen “no JobContext” decision and must not guide implementation.

  PC2 source state was checked read-only:

  - Branch: master
  - HEAD: same 959bdff7b83fec64ee46309db180e691f4501fb3
  - Working tree: clean

  Therefore, committed source is synchronized, but live working trees are not: PC1 has the changes above, PC2
  does not.

  Hardware was also checked read-only:

  - PC1 GPU0: NVIDIA RTX PRO 4500 Blackwell, 32623 MiB
  - PC2 GPU0: NVIDIA GeForce RTX 5070 Ti, 16303 MiB

  The live hardware agrees with the requested topology, but src/config.py:275 is stale: it still describes PC1
  GPU0 as an RTX 5070 Ti with 16 GB and leaves the RTX PRO 4500 as a commented future GPU1.

  The existing environment validator did not pass because five declared “stable” directories have not been
  initialized, including protocols/planning/old and four runtime artifact/tmp directories. This is an
  initialization-state issue rather than a test failure, although the obsolete protocols/planning/old layout
  entry should be removed instead of being created.

  ### What exists today

  - src/director.py:27 contains only TaskFocus, DirectorTask, basic non-empty-string checks, and serialization.
    There is no intelligent Director loop.

  - src/orchestrator.py:1 already declares itself the deterministic Task Executive foundation. It provides:
      - runtime directory initialization;
      - legacy action-state validation;
      - participant-role resolution;
      - preparation of a task;
      - the existing PDF preparation entry.

  - ModelClient (src/model_client.py:92) is a generic synchronous OpenAI-compatible text client. It handles
    request validation, HTTP transport, parsing, token/latency metadata, and normalized errors.

  - src/config.py:348 correctly configures:
      - Qwen at http://192.168.50.2:8001/v1;
      - DiffusionGemma at http://127.0.0.1:8003/v1;
      - Gemma Director and worker logical contexts;
      - Qwen reviewer/challenger context.

  - The current uncommitted changes correctly make Gemma temperature optional and enable its gemma4 tool parser.
    These should be preserved.

  - src/communication.py is empty.
  - The large orchestrator_communication_validator.py validates the archived legacy envelope, not the current 30-
    line communication protocol.

  - Plan, DirectorTask, and TaskExecution JSON files are templates/contracts, not JSON Schema. They carry the
    authoritative field vocabulary, but do not formally declare required, optional, nullable, or conditional
    fields.

  - No Plan validator, Plan merger, TaskExecution builder, managed-work persistence, prompt projector, budget
    enforcement, or end-to-end managed runtime exists.

  - DEFAULT_JOB_BUDGET is declared at src/config.py:481 but is never read.
  - SQLite is configured but unused.

  The checkout is internally consistent for its tested inference/configuration baseline, but not yet internally
  consistent as the requested managed-work runtime.

  ———

  ## 2. Protocol/runtime mismatches

  ### DirectorTask exact mismatch

  The authoritative DirectorTask protocol contains 19 task fields. Python contains 12.

  Fields present in the protocol but missing from Python are exactly:

  work_kind
  plan_ref
  action
  target
  anchors
  entities
  reason

  There are no Python-only DirectorTask fields. Every existing dataclass field maps to the protocol.

   Concept                Core task identity
   Protocol               task_id, job_ref, capability, participant_role, objective
   Current Python         Present
   Problem                Only non-empty strings are checked
   Recommended authority  Protocol plus vocabulary
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   Concept                Inputs/instructions
   Protocol               input_refs, instruction
   Current Python         Present
   Problem                Type checks only
   Recommended authority  Protocol
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   Concept                Work classification
   Protocol               work_kind, plan_ref
   Current Python         Missing
   Problem                Accepted Plan cannot be tied cleanly to runtime task
   Recommended authority  Protocol
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   Concept                Semantic operation
   Protocol               action
   Current Python         Missing from class; passed separately to prepare_director_task()
   Problem                Two independent sources can disagree
   Recommended authority  DirectorTask.action
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   Concept                Target
   Protocol               target.kind, target.locator
   Current Python         Missing
   Problem                No deterministic connection to selected Plan step or artifact
   Recommended authority  Protocol
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   Concept                Anchors
   Protocol               Array of {kind, value}
   Current Python         Missing
   Problem                Cannot preserve protocol task precision
   Recommended authority  Protocol
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   Concept                Entities
   Protocol               Array of {kind, name}
   Current Python         Missing
   Problem                Cannot preserve named semantic subjects
   Recommended authority  Protocol
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   Concept                Focus
   Protocol               Questions, angles, granularity
   Current Python         TaskFocus
   Problem                Shape maps, but granularity is not vocabulary-validated
   Recommended authority  Protocol; TaskFocus remains an adapter
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   Concept                Rationale
   Protocol               reason
   Current Python         Missing
   Problem                Director rationale is lost
   Recommended authority  Protocol
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   Concept                Requirements/acceptance
   Protocol               Present
   Current Python         Present
   Problem                No vocabulary or conditional checks
   Recommended authority  Protocol
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   Concept                External seam
   Protocol               external_authority_ref
   Current Python         Present
   Problem                Correctly preserved but unused
   Recommended authority  Protocol
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   Concept                Legacy execution state
   Protocol               Not part of DirectorTask
   Current Python         current_kind is separately required by prepare_director_task()
   Problem                Caller-supplied execution state can drift from referenced artifacts
   Recommended authority  Task Executive resolves it mechanically

  Minimum resolution:

  1. Expand the existing DirectorTask; do not add a replacement task struct.
  2. Add one parsing/validation adapter that converts a model-produced task mapping into the existing immutable
     class.

  3. Make semantic_payload() produce the authoritative protocol field names.
  4. Remove the separate semantic action argument from the managed-task preparation path. The task’s validated
     action is authoritative.

  5. Keep current_kind only for the old artifact-state pipeline, resolving it from the target/input artifact
     rather than asking the Director to author it.

  Nested objects should not produce Target, Anchor, Entity, and similar dataclass families. Retain TaskFocus
  because it already exists; represent target and entries in anchors/entities as normalized immutable mappings
  validated directly against the protocol shape.

  ### Wider mismatches

   Concept                   Protocol                     Current runtime              Problem
  ━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Plan                      Full revision,               No runtime implementation    Models cannot yet create,
                             participant, proposal,                                    validate, merge, or
                             critique, decision, step,                                 persist a Plan
                             final, integrity graph
  ────────────────────────  ───────────────────────────  ───────────────────────────  ───────────────────────────
   Normal planning           Policy maximum 3 and         Budget unused                No enforcement or
                             explicit advancement                                      semantic iteration
                             rules                                                     tracking
  ────────────────────────  ───────────────────────────  ───────────────────────────  ───────────────────────────
   TaskExecution             Full execution, result/      No builder or validator      A model response cannot
                             error, trace, plan-                                       become authoritative
                             execution, artifact                                       execution state
                             fields
  ────────────────────────  ───────────────────────────  ───────────────────────────  ───────────────────────────
   Model transport result    N/A                          ModelResponse                Correct transport-level
                                                                                       object; it is not a
                                                                                       duplicate TaskExecution
  ────────────────────────  ───────────────────────────  ───────────────────────────  ───────────────────────────
   Current communication     Small metadata/              No implementation            Plan message_refs and
                             correlation envelope                                      managed correlation
                                                                                       cannot be populated
  ────────────────────────  ───────────────────────────  ───────────────────────────  ───────────────────────────
   Legacy communication      Archived combined            Large active validator       Existing tests validate
                             contract                                                  the archived contract,
                                                                                       not current communication
  ────────────────────────  ───────────────────────────  ───────────────────────────  ───────────────────────────
   Planning policy path      Authoritative                No PLANNING_POLICY_PATH;     Policy cannot be loaded
                             planning_policy.yaml         startup does not require     by the runtime
                                                          it
  ────────────────────────  ───────────────────────────  ───────────────────────────  ───────────────────────────
   Role resolution           Logical roles and            Implemented                  Works, but only reviewer/
                             contexts                                                  challenger currently
                                                                                       resolve to Qwen
  ────────────────────────  ───────────────────────────  ───────────────────────────  ───────────────────────────
   Model capabilities        Static ModelStruct.role      Qwen lacks reasoning/        Metadata and actual
                                                          reviewer tags despite        assignment disagree
                                                          serving those roles
  ────────────────────────  ───────────────────────────  ───────────────────────────  ───────────────────────────
   Prompt context            Store richly; inject         Only a static planning       No stage-specific
                             selectively                  prompt and manual smoke-     projection exists
                                                          test messages
  ────────────────────────  ───────────────────────────  ───────────────────────────  ───────────────────────────
   Persistence               Protocol fields and          No managed-work writer       persistence.location,
                             artifact roots                                            prompt refs, Plans, and
                                                                                       TaskExecutions cannot be
                                                                                       fulfilled
  ────────────────────────  ───────────────────────────  ───────────────────────────  ───────────────────────────
   Hardware trace            TaskExecution expects        PC1 metadata says 5070 Ti    A Gemma trace would
                             node/host/model                                           record incorrect hardware

  Three concrete contradictions exist inside the Plan contract itself:

  1. The JSON template allows critique severities blocking | major | minor | low; the vocabulary allows blocking
     | high | medium | low.

  2. The template initializes integrity validation as not_checked; the vocabulary allows only pending | valid |
     invalid.

  3. Critique/suggested-change target_kind placeholders contain a duplicated revision and omit the vocabulary’s
     plan.

  These should be corrected in the existing protocol files before a validator freezes either interpretation. The
  clean choice is to align the JSON template to the YAML vocabulary: blocking/high/medium/low, pending, and plan/
  proposal/step/revision.

  TaskExecution also needs a minimal semantic clarification: its template shows both result and error populated
  and does not state when artifact_record is optional. V0 needs the existing contract to state that successful
  terminal executions populate result and clear error, while failed executions do the reverse.

  ———

  ## 3. What already works and should be reused

  - Keep ModelClient unchanged. Its endpoint abstraction already makes remote Qwen inference transparent.
  - Keep ModelResponse; map it into TaskExecution rather than replacing it.
  - Keep the Qwen and Gemma server profiles. Server lifecycle is not part of this managed call path.
  - Keep LogicalContextStruct, PARTICIPANT_ROLE_CONTEXTS, and resolve_participant_role() (src/
    orchestrator.py:119).

  - Keep the three logical contexts:
      - Gemma Director;
      - Gemma worker;
      - Qwen worker.

  - Keep TaskFocus, expanding its validation to the protocol vocabulary.
  - Reuse the protocol loaders and immutable-mapping pattern in src/structures.py:234.
  - Reuse ValidationIssue for precise task/plan validation errors rather than introducing a new semantic result
    hierarchy.

  - Reuse ensure_runtime_directories().
  - Retain the existing PDF preparation and legacy action-state machinery unchanged. It is not the V0 planning
    engine.

  - Reuse the Plan protocol’s own projection principle: templates/plan_protocol_notes.md:1 explicitly allows
    role- and phase-specific views and partial contributions.

  - Preserve external_authority_ref; reject unsupported external escalation explicitly rather than silently
    falling back.

  Remote Qwen needs no SSH inference path. What is missing is only:

  1. conversion from resolved ModelStruct to ModelClientConfig;
  2. API-key environment lookup;
  3. invocation by Task Executive;
  4. output parsing/validation;
  5. TaskExecution construction and persistence.

  ———

  ## 4. Minimum architecture changes

  ### 4.1 Make protocol-shaped mappings authoritative

  Persisted and transmitted JSON mappings should be the runtime authority. Python classes are adapters that
  implement those mappings.

  Why required: current dataclass validation cannot reject invalid vocabulary, missing nested objects, unknown
  fields, or bad cross-references.

  Files:

  - src/director.py
  - DirectorTask protocol/vocabulary
  - Plan protocol/vocabulary
  - TaskExecution protocol/vocabulary

  No new semantic schema or result class is needed.

  ### 4.2 Complete DirectorTask without replacing it

  Add the seven missing fields to DirectorTask, using mappings for nested objects. Add:

  - strict JSON parsing;
  - allowed-field checking based on the protocol task template;
  - vocabulary checks;
  - execution-profile checks:
      - work_kind == execution;
      - non-empty plan_ref;
      - job_ref matches the active request;
      - plan_ref identifies the accepted Plan revision;
      - action is a known semantic operation;
      - participant role is configured;
      - target points to the selected Plan step or its external target;
      - output contract/acceptance is present for the first executable step.

  Why current code cannot: prepare_director_task() (src/orchestrator.py:164) only checks a separately supplied
  legacy action and resolves a role.

  Structural repair:

  - exactly one repair call;
  - same Gemma Director context;
  - repair prompt contains the invalid task and deterministic validation issues;
  - it may correct structure only, not silently select a different semantic task;
  - repair consumes one reasoning-task allowance;
  - it does not advance semantic iteration;
  - a second invalid result terminates clearly.

  ### 4.3 Implement the fixed Normal Director loop

  Place the semantic loop in director.py, not orchestrator.py.

  It should:

  - initialize a protocol-shaped Plan mapping;
  - request the two independent proposals;
  - request Qwen critique;
  - request Gemma synthesis;
  - validate and finalize the Plan;
  - ask Gemma to select one Plan step and emit the DirectorTask;
  - evaluate TaskExecution as ACCEPT or REVISE.

  Why current code cannot: no Director behavior exists today.

  The fixed sequence is intentional V0 policy, not a general autonomous conversation engine.

  ### 4.4 Add explicit prompt projections

  Add small functions, not a context subsystem, that build model messages from allowlisted fields.

  The functions should project directly from loaded protocol/policy mappings:

  - proposal schema: one planning_cycle.proposals[] entry;
  - critique schema: one critique plus referenced suggested changes if needed;
  - synthesis schema: final Plan core, revision, decision, steps, and final/integrity fields;
  - task selection: accepted Plan and chosen step;
  - execution: validated DirectorTask and referenced inputs;
  - evaluation: selected Plan step, TaskExecution result, expected result, and validation.

  Per-call output caps should be lower than global model maxima so Gemma’s 4096-token context is not consumed by
  max_tokens=3000.

  Why current code cannot: it only passes manually constructed message lists.

  ### 4.5 Extend the Task Executive mechanically

  Keep the historical filename.

  Add mechanical functions for:

  - resolving any configured logical context, including the Director context;
  - creating ModelClientConfig from ModelStruct;
  - enforcing the reasoning-call budget;
  - invoking a selected model context;
  - validating a DirectorTask before execution;
  - resolving referenced inputs;
  - constructing the exact execution prompt;
  - calling ModelClient;
  - mechanically validating returned content;
  - building the authoritative TaskExecution mapping;
  - persisting artifacts atomically.

  The Task Executive must receive selected context/task/prompt intent. It must not choose proposals, critique
  targets, Plan steps, or ACCEPT/REVISE.

  The existing ACTIONS registry contains Qwen model names and an older document/OKF state machine. Do not use
  those model keys for this managed path. Leave the old pipeline intact and validate V0 semantic operations
  against the DirectorTask vocabulary.

  ### 4.6 Use current role resolution to prove remote execution

  For the first acceptance scenario:

  - proposal A context: gemma_worker;
  - proposal B context: qwen_worker;
  - critic context: qwen_worker;
  - Director: gemma_director;
  - executable DirectorTask role: reviewer;
  - reviewer resolves through configuration to qwen_worker;
  - qwen_worker.worker_ref resolves to MODELS["qwen"];
  - Qwen’s endpoint_url resolves to PC2.

  The selected V0 execution step should genuinely be framed as independent verification/review so
  participant_role="reviewer" remains semantically honest. A later milestone can add phase-specific primary-
  worker assignments if needed.

  ### 4.7 Construct TaskExecution directly

  Do not add TaskExecutionResult.

  On success, populate:

  - task/job references;
  - attempt and completed status;
  - resolved role/context/worker;
  - output contract;
  - parsed content and artifact refs;
  - prompt provenance;
  - model/node/host trace derived from configuration;
  - Plan revision and selected step;
  - expected-result snapshot;
  - achieved result;
  - mechanical validation result/evidence.

  ModelResponse remains the transient transport result.

  For Director evaluation, use existing plan_execution fields:

  - outcomes: normalized ACCEPT or REVISE;
  - validation_outcome;
  - deviation;
  - validation_evidence_refs;
  - replan_requested only when the Plan itself must change.

  No new evaluation protocol field is required.

  ### 4.8 Add minimal persistence

  Use the existing filesystem artifact root rather than implementing SQLite now.

  Add one managed-work directory pattern under workspace/artifacts, grouped by job_ref. Persist separately:

  - original request;
  - exact prompts;
  - raw model responses;
  - canonical Plan;
  - validated DirectorTask;
  - TaskExecution;
  - current communication messages.

  The directory is organizational only; it is not JobContext or a semantic parent object.

  Use atomic writes and stable references. Do not introduce a general repository or event-sourcing framework.

  ———

  ## 5. Explicit non-changes

  - No JobContext, JobState, WorkContext, or ManagedJob.
  - No third intelligent Orchestrator/Coordinator.
  - No broad rename of orchestrator.py; it remains the Task Executive implementation under its historical
    filename.

  - No frontier-model adapter or hidden OpenAI/Ren fallback.
  - No Harness integration or Harness data structures.
  - No vector memory, embeddings, or knowledge graph.
  - No dynamic benchmarking, reliability scoring, or adaptive model routing.
  - No Deep planning implementation.
  - No adaptive stopping.
  - No unrestricted model-to-model conversation.
  - No extra debate round unless the bounded Normal budget is used for one correction.
  - No dynamic plugin/MCP/frontend framework.
  - No SSH-based inference.
  - No ModelClient redesign.
  - No tool/image support added to ModelClient for this text-only slice.
  - No new TaskExecution result abstraction.
  - No SQLite ledger implementation.
  - No replacement Plan or DirectorTask schema layer.
  - No changes to the existing document-preparation pipeline merely to make naming cleaner.

  ———

  ## 6. Proposed runtime sequence

  1. Accept managed request
      - Persist the original text as an input artifact.
      - Assign job_ref.
      - Use its artifact reference as Plan current_work_ref.
      - No JobContext is created.

  2. Initialize Plan
      - Create plan_id, revision 1, participants, Normal process maximum 3, empty planning-cycle collections,
        proposed steps/final/integrity state.

      - Persist the Plan after each validated material update.

  3. Gemma independent proposal
      - Director selects gemma_worker.
      - Task Executive invokes the configured context mechanically.
      - Prompt contains only:
          - original request;
          - Normal constraints;
          - proposal projection.

      - Persist request/response communication and raw response.
      - Validate and merge proposal A into planning_cycle.proposals.

  4. Qwen independent proposal
      - Use the same frozen input snapshot and proposal projection.
      - The prompt must not contain Gemma’s proposal, its ID, summary, or artifact reference.
      - Validate and merge proposal B only after the call returns.
      - The two validated proposals form the first meaningful planning advancement.

  5. Qwen critique
      - Director selects qwen_worker.
      - Prompt contains:
          - original request;
          - Gemma proposal;
          - critique projection and constraints.

      - Omit Qwen’s own proposal in the first slice to minimize context.
      - Validate target references and merge critique/suggested changes.

  6. Gemma Director synthesis
      - Resolve DIRECTOR_CONTEXT.
      - Inject only:
          - original request;
          - proposal A;
          - proposal B;
          - Qwen critique;
          - relevant Normal policy;
          - final Plan projection.

      - Gemma produces synthesis semantics.
      - Deterministic code fills trusted IDs/timestamps and validates references/integrity.
      - Record revision source refs and a finalize decision.
      - Mark the Plan final and select its current revision.

  7. DirectorTask generation
      - Gemma Director receives the accepted Plan and selected step.
      - It emits only the task body, not trusted protocol metadata.
      - Runtime wraps it with the authoritative protocol identity.

  8. DirectorTask validation
      - Parse strict JSON.
      - Validate full structure, vocabulary, job/Plan/step references, role, capability, operation, requirements,
        and output contract.

      - If invalid, perform at most one structural repair.
      - If still invalid, terminate with a current communication error; do not fabricate a TaskExecution for an
        invalid task.

  9. Task Executive preparation
      - Enforce remaining budget.
      - Resolve participant_role="reviewer" through configuration.
      - Resolve Qwen’s ModelStruct, endpoint, model name, node, and host.
      - Resolve only the task’s declared input_refs.
      - Build and persist the exact execution prompt.

  10. Remote Qwen execution
      - Construct ModelClientConfig from the resolved model.
      - Call the existing generic ModelClient.
      - No Qwen-specific branch and no SSH inference.

  11. TaskExecution construction
      - Parse/validate the output contract.
      - Construct the TaskExecution mapping with Qwen/PC2 trace metadata and the Plan expected-result snapshot.
      - On transport failure, construct a failed TaskExecution with normalized error information.

  12. Gemma Director evaluation
      - Inject:
          - original request only if needed;
          - accepted Plan projection;
          - selected step’s expected result and validation;
          - validated DirectorTask;
          - relevant TaskExecution result and mechanical validation.

      - Do not inject unrelated trace events, all messages, raw reasoning, or full history.
      - Require ACCEPT or REVISE plus a concise reason.

  13. Terminal handling
      - ACCEPT: record outcome and passed/partial validation as appropriate; persist final TaskExecution and
        finish.

      - REVISE: allow one new DirectorTask and one follow-up execution under the same Plan expectation.
      - A second REVISE, exhausted budget, or need to change the Plan terminates honestly as unresolved/request-
        replan-not-implemented.

  Budget interpretation:

  - semantic_iterations=3
      - first advancement: validated independent candidate set;
      - second: validated deliberation and final Plan;
      - third remains available for the one bounded post-execution semantic correction.

  - reasoning_tasks=20
      - count every actual model invocation, including Director calls and structural repair;
      - transport/format retries do not advance semantic iteration;
      - enforce with simple scalar counters in the synchronous run, not a state object.

  ———

  ## 7. File-by-file implementation plan

   File                     protocols/director/director_task_protocol_v0.json
   Existing responsibility  Authoritative Director task shape
   Required modification    No new fields; clarify optional/conditional execution requirements only if necessary
   Kind                     Semantic contract
   Expected tests           Protocol/runtime field parity
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     protocols/director/director_task_vocabulary.yaml
   Existing responsibility  Task vocabulary
   Required modification    Reuse for capability, role, operation, work kind, granularity validation
   Kind                     Semantic contract
   Expected tests           Every vocabulary field accepted/rejected correctly
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     protocols/planning/plan_protocol_v0.json
   Existing responsibility  Authoritative Plan graph
   Required modification    Correct severity, validation-status, and target-kind contradictions
   Kind                     Semantic contract
   Expected tests           JSON/vocabulary consistency and final Plan validation
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     protocols/planning/plan_protocol_vocabulary.yaml
   Existing responsibility  Plan vocabulary
   Required modification    Otherwise unchanged
   Kind                     Semantic contract
   Expected tests           Template values are vocabulary-valid
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     protocols/planning/planning_policy.yaml
   Existing responsibility  Planning level and advancement policy
   Required modification    No semantic expansion; load and enforce Normal only
   Kind                     Semantic contract
   Expected tests           Normal max 3; invalid calls do not advance
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     protocols/execution/task_execution_protocol_v0.json
   Existing responsibility  Authoritative execution state
   Required modification    Clarify result/error and optional artifact behavior; no new result field
   Kind                     Semantic contract
   Expected tests           Success and failure profiles
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     protocols/execution/task_execution_vocabulary.yaml
   Existing responsibility  Execution vocabulary
   Required modification    Document terminal result/error exclusivity and ACCEPT/REVISE use of existing outcome
                            fields
   Kind                     Semantic contract
   Expected tests           State/result/error combinations
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     protocols/communication/communication_protocol_v0.json
   Existing responsibility  Current correlation envelope
   Required modification    No field changes expected
   Kind                     Semantic contract
   Expected tests           Builder/validator round trip
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     src/director.py
   Existing responsibility  Current task adapter
   Required modification    Add seven fields, protocol parsing, precise issues, Plan validation/merge, Normal
                            loop, task repair, evaluation, stage-specific prompt projections
   Kind                     Semantic
   Expected tests           DirectorTask, independence, Plan synthesis, evaluation
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     src/orchestrator.py
   Existing responsibility  Task Executive foundation
   Required modification    Add context resolution, model-client factory, budget checks, model invocation, pre-
                            execution validation, TaskExecution construction, mechanical persistence
   Kind                     Mechanical
   Expected tests           Routing, endpoint resolution, errors, budgets, TaskExecution
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     src/communication.py
   Existing responsibility  Empty current communication module
   Required modification    Build/validate trusted current envelopes and correlation IDs; no routing intelligence
   Kind                     Mechanical
   Expected tests           Request/response/error reference rules
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     src/orchestrator_communication_validator.py
   Existing responsibility  Legacy compatibility validator
   Required modification    Leave unchanged
   Kind                     None
   Expected tests           Existing 17 tests remain green
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     src/config.py
   Existing responsibility  Topology, models, contexts, budget
   Required modification    Correct PC1 GPU metadata; add planning-policy path; add explicit Normal stage-context
                            assignments; correct Qwen capability tags
   Kind                     Mechanical configuration
   Expected tests           Hardware/model/context assignments
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     src/structures.py
   Existing responsibility  Generic infrastructure structures
   Required modification    Preserve current optional temperature change; avoid new Plan/TaskExecution semantic
                            classes
   Kind                     Mechanical
   Expected tests           Existing configuration tests
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     src/initialization.py
   Existing responsibility  Resource/layout checks
   Required modification    Require planning policy; validate protocol/vocabulary compatibility at startup;
                            remove dependence on obsolete planning-old directory
   Kind                     Mechanical
   Expected tests           Startup catches missing/contradictory contracts
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     src/model_client.py
   Existing responsibility  Generic OpenAI transport
   Required modification    No functional change
   Kind                     None
   Expected tests           Same client works for both model configs
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     src/qwen_server.py
   Existing responsibility  Qwen deployment profile
   Required modification    No change
   Kind                     None
   Expected tests           Existing profile test
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     src/gemma_server.py
   Existing responsibility  Gemma deployment profile
   Required modification    Preserve current uncommitted parser/tool changes
   Kind                     None
   Expected tests           Existing profile/temperature test
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     workspace/.benzaiten_layout.json
   Existing responsibility  Machine-readable runtime layout
   Required modification    Add one minimal managed-work artifact location; remove obsolete
                            planning_protocols_old entry
   Kind                     Mechanical
   Expected tests           Safe resolution and traversal rejection
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     src/run_managed_work.py
   Existing responsibility  Does not exist
   Required modification    Add a tiny synchronous bootstrap that invokes the Director-owned Normal loop and
                            prints/returns the final trace
   Kind                     Mechanical wiring
   Expected tests           One fully mocked end-to-end test
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     smoke_tests/test_task_executive.py
   Existing responsibility  Role resolution
   Required modification    Extend for validation, client construction, execution, TaskExecution, and budgets
   Kind                     Tests
   Expected tests           All Task Executive requirements
  ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
   File                     New focused tests under smoke_tests/
   Existing responsibility  N/A
   Required modification    DirectorTask, planning, communication, and managed V0 integration tests
   Kind                     Tests
   Expected tests           Coverage below

  The staged/untracked decision schematics should not be consumed by implementation. Because they are user-owned
  and explicitly contain the rejected JobContext design, they should be revised separately rather than silently
  overwritten.

  ———

  ## 8. Test plan

  ### Protocol and task tests

  - Fully populated DirectorTask.semantic_payload() has exactly the protocol’s 19 task keys.
  - Every existing and newly added field round-trips.
  - Unknown fields are rejected.
  - Missing required execution fields are rejected.
  - Invalid capability, role, work kind, operation, and granularity are rejected.
  - Malformed target/anchor/entity/focus objects are rejected.
  - plan_ref and job_ref mismatches are rejected before role resolution.
  - Non-null external_authority_ref produces explicit unsupported-authority failure.

  ### Structural repair tests

  - Valid first output causes no repair.
  - Invalid output invokes exactly one repair.
  - Repair prompt includes deterministic issues and original invalid content.
  - Invalid repair terminates.
  - Repair counts against reasoning tasks but not semantic iterations.

  ### Planning tests

  - Gemma and Qwen proposal calls receive the same request snapshot.
  - Gemma input contains no Qwen proposal.
  - Qwen input contains no Gemma proposal.
  - No proposal is merged before both independent calls have captured inputs.
  - Qwen critique targets Gemma’s proposal by exact reference.
  - Gemma synthesis receives both proposals and the critique.
  - Final Plan contains proposal, critique, revision, decision, steps, expected results, validation, and final
    selection.

  - Plan integrity rules reject duplicate/missing step IDs and invalid dependencies.
  - Normal never exceeds three semantic iterations.

  ### Routing and transport tests

  - Director context resolves to Gemma without endpoint hard-coding.
  - reviewer and challenger resolve to Qwen.
  - Qwen resolves to pc2.gpu0 and http://192.168.50.2:8001/v1.
  - ModelClient construction comes entirely from ModelStruct.
  - Reassigning a logical context in a test changes the model without changing Task Executive code.
  - The same generic client path handles Gemma’s omitted temperature and Qwen’s configured temperature.
  - No qwen/gemma branch exists in ModelClient or managed execution logic.

  ### TaskExecution tests

  - Successful Qwen response produces the required execution, resolved, result, provenance, trace, and plan-
    execution fields.

  - Model/name/node/host are derived from trusted configuration, never model output.
  - JSON result content remains JSON rather than a JSON-encoded string.
  - Transport errors become failed TaskExecution records with normalized categories.
  - ModelResponse is never persisted as a substitute for TaskExecution.
  - Result/error mutual exclusivity is enforced.
  - Prompt and result artifact references resolve to persisted files.

  ### Evaluation/revision tests

  - Evaluation prompt includes only the selected Plan/step, task, execution, expected result, and validation.
  - ACCEPT terminates without another model call.
  - First REVISE permits exactly one follow-up DirectorTask.
  - Second REVISE terminates unresolved.
  - A requested Plan change terminates as replan-not-implemented rather than recursively replanning.
  - Exhausted reasoning or semantic budget prevents further calls.

  ### Architectural boundary tests

  - Task Executive refuses to execute without an already selected, valid task.
  - Task Executive never creates a semantic action, proposal, critique, Plan step, or evaluation decision.
  - Director tests use a fake Task Executive interface and remain independent of endpoint details.
  - Bootstrap only wires the Director and Task Executive; it contains no semantic selection logic.
  - Current legacy validator tests remain unchanged and green.

  A live smoke test should remain separate from deterministic tests and send one full managed request to the
  already-running Gemma and Qwen endpoints.

  ———

  ## 9. First end-to-end acceptance scenario

  Managed request:

  > Alphabetically sort ["pear", "apple", "banana"]. Return only a JSON object with exactly two keys: ordered,
  > containing the sorted array, and count, containing 3.

  Expected Plan step:

  - Action: sort the three strings and return the specified JSON object.
  - Expected result:

  {
    "ordered": ["apple", "banana", "pear"],
    "count": 3
  }

  - Validation:
      - valid JSON object;
      - exactly two keys;
      - exact ordered array;
      - integer count equal to 3;
      - no additional prose.

  Expected trace:

  1. Request persisted and assigned job_ref.
  2. Gemma independent proposal added as proposal A.
  3. Qwen independent proposal added as proposal B, with captured input proving it did not see A.
  4. Qwen critique targets A and checks ordering/output constraints.
  5. Gemma Director synthesizes a final one-step Plan with observable validation.
  6. Gemma emits a valid DirectorTask with:
      - knowledge_synthesis;
      - work_kind=execution;
      - final plan_ref;
      - participant_role=reviewer;
      - selected step target;
      - bounded acceptance/output contract.

  7. Task Executive validates the task and resolves reviewer → qwen_worker → qwen.
  8. Generic ModelClient calls http://192.168.50.2:8001/v1.
  9. TaskExecution records Qwen, pc2.gpu0, PC2 host, exact JSON result, and mechanical validation evidence.
  10. Gemma receives the selected projections and returns ACCEPT.

  This scenario is deliberately trivial: failure would strongly indicate protocol, context, routing, parsing,
  persistence, or budget defects rather than a difficult reasoning problem.

  ———

  ## 10. Risks / unresolved decisions

  ### 1. The protocol files are templates, not formal schemas

  Options:

  - Convert them to full JSON Schema.
  - Add a parallel runtime schema.
  - Keep them authoritative and implement small validators directly against their field inventories/vocabularies.

  Recommendation: the third option. Correct the concrete contradictions in-place and lock the adapters to them
  with parity tests.

  Consequence: conditional rules remain Python validation logic, but there is no duplicate semantic data model or
  new protocol family.

  ### 2. Whether Phase A calls produce TaskExecution records

  Options:

  - Treat every proposal/critique model call as a DirectorTask and TaskExecution.
  - Treat Phase A as Director-owned Plan construction recorded through Plan contributions, current communication
    messages, prompts, and raw artifacts; begin formal DirectorTask/TaskExecution at the accepted-Plan boundary.

  Recommendation: use the second option for this first slice because it exactly matches the requested Phase A/B/C
  boundaries and avoids forcing plan_execution semantics onto calls made before a final executable Plan exists.

  Consequence: Phase A remains auditable through Plan/message/artifact references, but not every planning
  inference has a TaskExecution. If the architectural intention is that every model call must be a TaskExecution,
  the existing TaskExecution contract must first make plan_execution nullable or define a non-final-plan profile.

  ### 3. Where to record ACCEPT/REVISE

  Options:

  - Add a new evaluation protocol/object.
  - Append another Plan decision.
  - Use existing TaskExecution plan_execution.outcomes, validation_outcome, deviation, and related fields.

  Recommendation: use the existing TaskExecution fields.

  Consequence: no new semantic abstraction is needed. The only contract clarification required is the V0 shape of
  an outcomes entry and which fields Task Executive fills from the Director’s decision.

  ### 4. Dirty PC1 architectural documents

  The staged and untracked schematics explicitly encode the rejected JobContext design.

  Recommendation: exclude them from implementation authority now, then revise or remove them in a separately
  authorized cleanup.

  Consequence: leaving them unchanged will continue to mislead later implementation reviews, but overwriting
  staged user work during the implementation pass would be unsafe.
