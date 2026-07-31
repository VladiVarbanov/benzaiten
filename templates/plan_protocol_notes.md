### Implementation and future optimization note

This schema defines the complete authoritative representation of a plan. An implementation is not required to expose, transmit, populate, or update every field during every planning operation.

Agents may receive role-specific or phase-specific projections containing only the fields relevant to their current responsibility. They may also return partial contributions that update only selected sections, such as proposals, critiques, suggested changes, synthesis decisions, or execution outcomes.

The deterministic orchestrator remains responsible for validating these partial contributions, resolving their references, merging them into the authoritative plan, and maintaining derived or administrative fields.

Fields may therefore be classified in future versions as:

* required for all plans
* required only for normal or deep planning
* conditionally required
* orchestrator-generated
* derived from other records
* optional archival metadata

Omitted fields do not imply deletion or reset. Unless explicitly changed, values already stored in the authoritative revision remain unchanged.

Future optimization may introduce compact agent views, field masks, role-specific projections, or partial-update operations without changing the meaning of the canonical plan schema.

TODO: ADD self speculation mode