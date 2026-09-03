Remaining Architecture Points to Freeze
Director → Task Executive task contract
What exactly does the Director request, and what information must the Task Executive receive?
Worker assignment
Whether workers are assigned explicitly by configuration/user, by task role, or selected by the Director.
Director internal loop
How Model A switches between Director reasoning and worker reasoning, and how convergence/good-enough decisions are represented.
Message kinds and directions
Request, order, response, error, and who may send each.
Trusted versus untrusted fields
What Python owns versus what models/agents/tools are allowed to return.
Job, task, message, and correlation IDs
Exact meaning and lifetime of each identifier.
Iteration versus delivery/retry
What constitutes one semantic iteration and what does not advance it.
Result representation
JSON, Markdown, text, validation status, partial versus complete results.
Error model
Categories, codes, source, retryability, and sanitization.
Execution trace
Logical worker identity, model deployment, node/host metadata, and what must never enter the protocol.
Protocol authority
JSON Schema versus YAML vocabulary and how they remain synchronized.
Configuration and initialization boundaries
What the Task Executive validates at startup and what /light bypasses.
Final module/file layout
Rename/remove old Orchestrator/coordinator concepts only after responsibilities are fully frozen.
