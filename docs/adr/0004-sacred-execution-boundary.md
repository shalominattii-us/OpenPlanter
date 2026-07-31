# ADR-0004: The Sacred Execution Boundary

- Status: Accepted
- Date: 2026-07-31

## Context

The Universal Execution Engine needs extensible plugins for external systems,
document generation, submissions, intelligence services, and future AEGENTIX
capabilities. Those plugins may fail, evolve independently, or execute code that
is less trusted than the orchestration core.

Allowing a plugin to mutate execution state would make workflow history depend
on hidden side effects. That would weaken replayability, approval enforcement,
auditability, deterministic recovery, and the ability to reason about a run from
its append-only record.

## Decision

Execution plugins execute work and return immutable `ExecutionResult` values.
They do not control workflow state.

The deterministic orchestrator is the sole authority that may:

- advance or terminate a run;
- start, complete, fail, approve, or reject a step;
- append authoritative execution events;
- enforce plan order, dependencies, and approval gates.

Plugins may:

- perform the work represented by one execution step;
- produce artifact references, metrics, observations, and diagnostics;
- report success or failure to the caller.

Plugins must never:

- mutate `ExecutionContext`;
- write orchestration events directly;
- advance, skip, or reorder workflow steps;
- bypass approval gates;
- invoke another plugin as an orchestration shortcut;
- rewrite execution history.

The communication flow is one-directional:

```text
ExecutionContext + ExecutionStep
              |
              v
        Plugin Runtime
              |
              v
       ExecutionResult
              |
              v
         Orchestrator
              |
              v
        ExecutionEvent
```

`ExecutionResult` is information. `ExecutionEvent` is authority.

## Consequences

### Positive

- deterministic replay and recovery remain possible;
- approval gates cannot be bypassed by plugin code;
- plugins are independently testable and replaceable;
- audit history reflects authoritative orchestration decisions;
- runtime-wide tracing, timing, policy, and sandboxing can be added centrally;
- AEGENTIX intelligence can evolve without controlling execution history.

### Trade-offs

- every plugin result requires an explicit orchestration decision;
- plugins cannot optimize workflows by silently chaining work;
- integration code must translate results into orchestrator transitions.

These costs are intentional. Explicit transitions are preferable to hidden
coupling in a trustworthy execution platform.
