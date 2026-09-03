# Benzaiten Architecture Decisions — Frozen So Far

## 1. Core hierarchy

Benzaiten uses two distinct control layers:

### Director

The Director is the semantic/intellectual manager of the job.

It decides:

- what task is needed next;
- what is missing or weak;
- what questions should be asked;
- whether another critique or revision is needed;
- whether disagreement is material;
- whether the work has converged;
- whether the result is good enough to proceed or stop.

Model A may act both as:

- the reasoning engine behind the Director;
- an active worker on the problem.

Model B is primarily a worker, reviewer, critic, or challenger.

The Director does not manage infrastructure.

### Task Executive

The Task Executive is trusted deterministic Python machinery.

It is responsible for executing the Director's requested tasks within predefined system rules.

Current and future responsibilities include:

- runtime filesystem contract;
- predefined Python states and algorithms;
- execution of tasks;
- retries and failures;
- resource limits;
- later scheduling;
- later GPU/resource management.

The current `orchestrator.py` is conceptually the beginning of the Task Executive. Renaming/refactoring can happen later.

The Task Executive does not decide what intellectual work is needed.

### Fundamental distinction

> **Director decides WHAT needs to be done.**  
> **Task Executive determines HOW that task is executed within system constraints.**

---

## 2. Capabilities and job structure

Initial focus is on articles.

The first major semantic capabilities/jobs are:

- `knowledge_extraction`
- `knowledge_synthesis`

`knowledge_extraction` turns source material into structured, reliable information.

`knowledge_synthesis` is the problem-solving process: comparison, questioning, critique, improvement, reconciliation, and synthesis.

The system should remain lean.

Avoid proliferation of capability-specific management modules such as:

- `knowledge_extraction_coordinator.py`
- `knowledge_synthesis_coordinator.py`
- `review_coordinator.py`
- similar manager/controller layers

The generic Director coordinates semantic subprocesses across capabilities.

Capabilities define the kinds of semantic operations available; the Director decides which are needed.

---

## 3. Communication layer

The generic communication modules should be named:

- `communication.py`
- `communication_validator.py`

Communication belongs neither to the Director nor to the Task Executive.

Its purpose is to carry and validate trusted managed interactions between:

- Task Executive and Director;
- Director and models;
- Director and agents;
- Director and tools.

Communication does not:

- decide what task is needed;
- judge semantic quality;
- select capabilities;
- advance reasoning;
- manage Docker or model-server lifecycle;
- expose endpoint/network details.

`/light` remains outside managed communication:

```text
/light
    → model_client
    → selected model
    → plain response

# 1. Core Architecture

Benzaiten uses two distinct control layers:

```text
                         Director
                    Gemma — leader context
                      ↑           \
                      |            ↓
              semantic job     Task Executive
        extraction / synthesis      |
                      ↑              ↓
                      |      model / agent / tool
                      |         ↙           ↘
                      |   Gemma worker    Qwen worker
                      |         \           /
                      └──── reasoning/results ────┘
```

## Director

The Director is the semantic/intellectual manager of the job.

Initially, Gemma provides the Director reasoning context while also being available as a separate worker context.

The Director:

* defines the semantic job;
* decides what tasks are needed;
* writes or constructs the initial worker prompts;
* identifies weaknesses, contradictions, and missing knowledge;
* asks questions and requests critique or revision;
* evaluates whether worker results are coherent and useful;
* decides what constitutes meaningful semantic progress;
* determines when an iteration has advanced;
* decides whether more tools, knowledge, or worker effort are required;
* determines when planning or execution is good enough to continue or finish.

The Director decides **WHAT should be done**.

## Semantic Jobs

Initial semantic jobs are:

* `knowledge_extraction`
* `knowledge_synthesis`

Knowledge extraction produces reliable structured knowledge from source material.

Knowledge synthesis performs problem solving using extracted knowledge, discussion, critique, planning, revision, and synthesis.

Initially Benzaiten focuses primarily on articles.

## Task Executive

The Task Executive is trusted deterministic Python machinery.

The current `orchestrator.py` is conceptually the beginning of the Task Executive.

The Task Executive receives the Director's requested task together with predefined execution constraints such as:

* permitted models, agents, and tools;
* reasoning/iteration budget;
* runtime filesystem contract;
* knowledge and Vault locations;
* predefined Python states and algorithms;
* resource limits.

The Task Executive:

* checks whether required models and resources are available;
* initializes them when necessary;
* manages communication with local and remote workers;
* maintains separate worker contexts;
* executes model, agent, and tool calls;
* handles execution failures and retries;
* later may manage scheduling and GPU/resource allocation.

The Task Executive determines **HOW the Director's task is executed within system constraints**.

It does not decide what intellectual work is required.

## Initial Model Roles

Initially there are three separate model contexts, but only two model personalities:

```text
Gemma Director context
Gemma Worker context
Qwen Worker context
```

Gemma therefore acts as both:

* Director reasoning model;
* working team member.

Qwen acts primarily as:

* independent worker;
* reviewer;
* critic;
* challenger.

The Task Executive is Python machinery and is **not** another model personality.

## Planning and Work Cycle

A typical managed job proceeds approximately as follows:

1. The Director defines the semantic objective.
2. The Director creates the initial tasks/prompts.
3. The Task Executive prepares the required resources and worker contexts.
4. Gemma Worker and Qwen begin the planning phase.
5. Workers reason, discuss, critique, read available knowledge, and ask questions.
6. The Director evaluates their progress and determines what remains weak or unresolved.
7. If more knowledge, tools, or work are needed, the Director requests them through the Task Executive.
8. The cycle continues until the Director considers the plan good enough or the predefined budget is exhausted.
9. The accepted planning state is persisted.
10. Temporary worker context may then be released from GPU memory.
11. Fresh worker contexts are created for execution using the accepted plan and relevant persisted knowledge.
12. The same Director → Task Executive → worker loop continues during execution.

## Iteration

An iteration is **not a model call**.

An iteration is a Director-recognized meaningful advancement of the semantic state.

Several model calls, questions, critiques, tool calls, and revisions may occur inside one iteration.

The Task Executive enforces the predefined maximum reasoning/iteration budget, while the Director determines whether meaningful semantic progress has occurred.

## Vault and Context Lifetime

LLM working context is temporary and expensive.

Accepted knowledge and workflow state are persistent.

```text
working model context
        ↓
Director accepts useful state
        ↓
persist to Vault
        ↓
optional compression/distillation later
        ↓
release temporary context / KV cache from GPU
```

The Vault may contain:

* accepted plans;
* validated knowledge;
* important intermediate conclusions;
* decisions;
* unresolved questions;
* progress state;
* useful synthesis artifacts.

Later phases can start with fresh model contexts rehydrated only with the relevant Vault state.

This creates two distinct memory classes:

* **Working context** — temporary, GPU-resident, disposable.
* **Vault state** — persistent, structured, and potentially compressible.

## Fundamental Boundary

> **Director decides WHAT needs to be done.**
> **Task Executive determines HOW it is executed.**
> **Semantic jobs define the kind of intellectual work being performed.**
> **The Vault preserves accepted state between temporary model contexts.**


Your flow, slightly tightened
Director defines the semantic job
extraction or synthesis;
objective;
initial questions/tasks.
Director creates the initial prompts/tasks
and asks Task Executive to execute them.

Task Executive receives the execution mandate

allowed models/tools;
reasoning/iteration budget;
required knowledge/database locations;
resource limits.

Initially these limits are mostly hard-coded by us/protocols.

Task Executive prepares resources
checks Gemma;
checks Qwen on PC2;
starts models if required;
establishes the separate worker contexts;
later may check a third tool/GPU resource.
Planning begins
Gemma Worker and Qwen reason, critique, ask questions;
Director observes results;
Director decides what is coherent, weak, missing, or contradictory;
Director decides what constitutes a meaningful iteration.

Director may request additional resources

more knowledge;
another tool;
another question;
another critique.

It tells Task Executive what is needed. Task Executive determines how to execute it.

Planning finishes when the Director judges the plan good enough, subject to the hard maximum budget imposed by Task Executive/protocol.
Execution phase begins
planning worker contexts can be cleared;
the accepted plan is persisted;
fresh worker contexts receive the plan and required knowledge;
the same Director → Task Executive → workers loop repeats during actual work.
One thing I would protect carefully

When you say “context is freed”, I would not let the knowledge gained disappear.

