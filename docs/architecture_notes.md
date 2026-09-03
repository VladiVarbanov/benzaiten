# Benzaiten Architecture Notes

**Status:** Working architectural baseline  
**Version:** 0  
**Purpose:** Record the current system boundaries, terminology, execution paths, and implementation principles before the communication layer is redesigned.

---

## 1. Design intent

Benzaiten should support both casual model use and managed project work without forcing every interaction through the same machinery.

The system therefore has two distinct execution paths:

1. **Direct inference** for lightweight requests
2. **Managed execution** for project, research, extraction, planning, and other stateful work

The architecture should remain compact. Architectural roles describe responsibilities; they do not automatically require separate processes, classes, or files.

> Create a new module only when its logic is independently substantial. Do not create one file for every architectural noun.

---

## 2. Execution modes

### 2.1 Direct inference: `/light`

`/light` is an explicit short-circuit around the managed Benzaiten workflow.

It is intended for lightweight use of Gemma, Qwen, or another model where the user does not need planning, workflow state, artifact promotion, capability validation, or persistent project execution.

```text
User
  |
  | /light
  v
Direct model selection
  |
  v
model_client
  |
  v
Model endpoint
  |
  v
Plain model response
```

The `/light` path should not require:

- a Workflow Director
- planning levels or iterations
- a capability workflow
- the complete orchestrator communication envelope
- artifact validation
- project state or artifact promotion
- agent or tool orchestration

It may retain minimal operational metadata internally:

- request ID
- selected model ID
- timestamp
- latency
- finish reason
- normalized error information

`/light` is not an inferior version of managed execution. It is a deliberate direct-inference mode for requests that do not justify the rest of Benzaiten.

### 2.2 Managed execution

Managed execution is used for work that benefits from explicit capability selection, bounded autonomy, multiple steps, iteration, validation, tools, agents, persistent artifacts, or project context.

Examples include:

- knowledge extraction
- planning
- document preparation
- web research
- review and synthesis
- project-level deep work

```text
User or runtime entrypoint
          |
          v
     Orchestrator
          |
          v
       Director
          |
    +-----+-----+
    |     |     |
    v     v     v
  Model  Agent  Tool
          |
          v
Validated workflow result
```

The full Benzaiten communication contract belongs primarily to this managed path.

---

## 3. Core terminology

### 3.1 Orchestrator

The **Orchestrator** is the global Benzaiten execution authority.

It owns:

- entry into managed execution
- explicit capability selection and dispatch
- delegation of a bounded job to the Director
- the authority and resource limits granted to that job
- global execution context
- escalation handling
- final workflow outcome
- integration with persistence or an execution ledger

In Version 0, capability selection is primarily explicit and manual. Benzaiten does not need an intelligent capability router before there are enough capabilities to justify one.

The Orchestrator should not micromanage every model, agent, or tool call after it has delegated a bounded job.

### 3.2 Director

The **Director** is the middle-management layer between the Orchestrator and the workers.

There should be one generic Director mechanism, not one separate Director implementation for every capability.

The Orchestrator delegates a job together with a mandate:

```text
job objective
allowed models
allowed agents
allowed tools
iteration bounds
execution limits
validation requirements
```

Within that mandate, the Director may decide:

- what should happen next
- whether a model, agent, or tool is required
- which permitted worker is appropriate
- what task and expected output to provide
- whether an intermediate result advances the workflow
- whether another iteration is required
- when the delegated job is complete
- when it must escalate to the Orchestrator

The Director should be autonomous within its mandate. It should not ask the Orchestrator for permission before every permitted call.

The Director must escalate when it needs authority or resources outside the mandate.

### 3.3 Model

A **Model** performs inference.

Examples:

- Gemma
- Qwen

A model is not automatically an agent. It receives model-facing messages and returns an artifact or answer.

### 3.4 Agent

An **Agent** performs goal-directed action in the environment.

An agent may:

- use CPU rather than GPU
- use one or more tools
- use a small model
- use no model at all
- carry out a bounded action with some local autonomy

Examples:

- web-search agent
- scraper agent
- crawler agent
- document-fetch agent

An agent is not merely another name for a model deployment.

### 3.5 Tool

A **Tool** is a narrow callable operation.

Examples:

- fetch one URL
- parse one document
- read one file
- query one search endpoint
- extract metadata

The distinction is:

```text
Tool:
    perform a narrow operation

Agent:
    pursue a bounded goal, potentially by using several tools
```

The Director may call a model, an agent, or a tool directly when the delegated mandate allows it.

### 3.6 Communication layer

The **communication layer** handles the generic mechanics of an already-decided interaction.

It owns:

- canonical message construction
- message IDs and timestamps
- sender, receiver, thread, and reply correlation
- trusted execution trace attachment
- validation entrypoints
- conversion to model-client input
- wrapping model responses and transport failures
- serialization and deserialization where required

It does not decide what the workflow should do next.

### 3.7 Model client and model server

`model_client.py` owns transport to an already-running OpenAI-compatible endpoint.

It handles:

- request construction
- HTTP transport
- timeouts
- endpoint-response parsing
- normalized transport errors

`model_server.py`, `qwen_server.py`, and `gemma_server.py` own model deployment and lifecycle.

They do not participate in workflow semantics or per-message orchestration.

---

## 4. Authority boundaries

The most important separation is:

> **The Orchestrator delegates authority.  
> The Director decides what happens next within that authority.  
> Communication executes an already-decided interaction.**

### 4.1 Orchestrator versus Director

The Orchestrator knows which managed capability is being run and what authority it receives.

The Director knows how the delegated workflow should progress.

```text
Orchestrator:
    "Run this bounded knowledge-extraction job using these resources."

Director:
    "The next useful step is a Gemma analysis at this angle."
```

The Director is not a second Orchestrator because it has no global authority. It cannot silently expand its own mandate, enable new capabilities, change global policy, or take control of unrelated workflows.

### 4.2 Director versus communication

The Director produces semantic work intent:

```text
target kind
target identity or role
task
context
expected output
workflow correlation
```

It must not:

- construct raw communication envelopes
- know endpoint URLs
- issue HTTP requests
- manage Docker
- serialize model-server payloads
- interpret network exceptions
- generate trusted routing or provenance claims

The communication layer receives the already-decided work intent and performs the generic interaction.

It must not:

- choose the next extraction angle
- advance workflow iteration
- judge whether a partial domain artifact is useful
- select capability semantics
- construct domain prompts independently
- decide when a workflow is complete

### 4.3 A practical placement test

A function belongs to communication or infrastructure when it works identically across capabilities.

Examples:

- generate a message ID
- validate `reply_to`
- wrap a timeout
- convert a model response
- attach trusted route metadata

A function belongs to workflow semantics when it understands the meaning of the job.

Examples:

- choose the next extraction angle
- determine whether planning should continue
- accept or reject a partial extraction
- choose a review stage
- decide that sufficient evidence has been collected

---

## 5. Generic Director and capability flavours

The Director should remain generic.

Capability-specific modules provide the **job flavour**, not a second copy of workflow mechanics.

Conceptually:

```text
knowledge_extraction.py
    objective
    prompts
    angles
    granularity
    artifact rules
    completion semantics

document_preparation.py
    preparation stages
    parser operations
    package validation
    promotion rules

generic Director
    bounded progression
    iteration bookkeeping
    model/agent/tool requests
    intermediate outcome handling
    escalation
    completion
```

The capability description may initially be ordinary Python functions and data. It should not become a new workflow programming language unless repeated real use demonstrates that one is needed.

A generic Director may live in a dedicated `director.py` only when the shared logic justifies it. Until then, the generic directing mechanics may remain in an existing module.

Architectural roles do not imply architectural files.

---

## 6. Communication contract

### 6.1 Scope

The orchestrator communication protocol is an internal Benzaiten control-plane contract for managed execution.

It is not:

- the OpenAI/vLLM request format
- a model-authored object
- a planning artifact
- an OKF artifact
- a Docker/server-management contract
- a mandatory wrapper around `/light`

Models return capability artifacts. Benzaiten constructs the trusted surrounding message.

```text
Benzaiten order
      |
      v
model-facing messages
      |
      v
model-generated capability artifact
      |
      v
Benzaiten response or error
```

A model must never author trusted:

- message identity
- route
- execution trace
- host or node identity
- model-deployment identity
- lifecycle state
- retry state
- system provenance

### 6.2 Internal API versus protocol representation

The Director should not manually construct a large JSON protocol object for every call.

It should use a compact internal request such as a work intent. The communication layer may then construct and validate the canonical managed-execution envelope internally.

This keeps the Python interface simple while preserving correlation, auditability, and validation where managed work requires them.

### 6.3 Message kinds

Managed communication should distinguish at least:

- `request`
- `order`
- `response`
- `error`

Each kind must have explicit required and forbidden payloads.

A model response cannot simultaneously be a successful result and an error.

### 6.4 Iteration and delivery

Workflow iteration and transport delivery are different concepts.

Retain the established workflow contract:

```json
"iteration": {
  "current": 1,
  "maximum": 3
}
```

Represent delivery attempts separately.

A timeout retry must not automatically advance the workflow iteration.

### 6.5 Result content

When the output contract expects JSON, the result should contain a JSON value rather than a JSON-encoded string.

When it expects Markdown or plain text, the result should contain a string.

Capability-specific validation remains outside the generic communication validator.

### 6.6 Errors

Errors should use:

- a broad stable category
- a detailed machine-readable code
- the component or layer where the failure originated
- retryability
- safe human-readable detail
- correlation to the failed request or order

Raw exceptions, credentials, sensitive endpoint details, and Docker diagnostics belong in internal logs or an execution ledger, not ordinary communication envelopes.

---

## 7. Compact implementation principle

Benzaiten should not become a collection of tiny enterprise-style modules whose names repeat the same responsibility in different words.

Avoid unnecessary proliferation such as:

```text
ThingManager
ThingController
ThingResolver
ThingService
ThingFactory
ThingAdapter
```

Use conceptual separation first. Extract a physical module only when it improves:

- independent testing
- reuse
- clarity
- lifecycle separation
- dependency control

The likely compact Version 0 structure remains close to:

```text
src/
├── orchestrator.py
├── orchestrator_communication.py
├── orchestrator_communication_validator.py
├── model_client.py
├── model_server.py
├── qwen_server.py
├── gemma_server.py
├── knowledge_extraction.py
└── document_preparation.py
```

A generic `director.py` may be introduced later if shared workflow mechanics become large enough to justify it.

Likewise, target resolution may begin as a generic function in the Orchestrator and be extracted only when it becomes independently substantial.

---

## 8. Version 0 decisions

The following decisions form the current baseline:

1. `/light` bypasses managed Benzaiten workflow logic.
2. Managed execution uses the full orchestration architecture.
3. Capability selection is explicit and primarily manual.
4. The Orchestrator delegates a bounded mandate.
5. The Director is generic middle management.
6. The Director may call permitted models, agents, and tools without per-call escalation.
7. Requests outside the mandate are escalated to the Orchestrator.
8. Models perform inference.
9. Agents perform goal-directed actions and may use tools.
10. Tools are narrow callable operations.
11. The communication layer handles mechanics, not workflow semantics.
12. Models return capability artifacts, not trusted Benzaiten envelopes.
13. Architectural roles do not automatically require separate files.
14. Remote model endpoints are assumed to be already running.
15. Remote Docker or host lifecycle management is outside the communication layer.
16. Automatic capability discovery and intelligent routing are deferred.
17. Synchronous execution is sufficient for Version 0.
18. Workflow iteration remains separate from transport attempts and retries.

---

## 9. Deferred work

The following are deliberately deferred until demonstrated need exists:

- automatic capability selection
- role-based intelligent model routing
- asynchronous distributed scheduling
- remote host lifecycle management
- general worker daemons
- event-sourced communication traces
- agents as separately networked services
- adaptive workflow stopping
- autonomous internet research without an explicit research capability
- a declarative workflow language

---

## 10. Immediate architectural sequence

The next implementation sequence is:

1. use this document as the architectural baseline;
2. revise the managed communication protocol and vocabulary;
3. make the structural contract machine-definable;
4. rewrite `orchestrator_communication_validator.py`;
5. implement or revise `orchestrator_communication.py`;
6. add the `/light` direct-inference path;
7. integrate the Director mechanics only as far as current workflows require;
8. test managed and direct execution separately.

The architecture should be revised when implementation evidence contradicts it, but new complexity should be introduced only in response to a concrete requirement.
