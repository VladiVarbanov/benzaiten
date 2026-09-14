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

Iteration 3 design and runtime behavior are not part of this checkpoint.
