# ADR-0001: Append-only execution record

- Status: Accepted
- Date: 2026-07-30
- Scope: Universal Execution Engine core

## Context

The opportunity pipeline already converts normalized opportunities into evidence, qualification decisions, mission candidates, mission graphs, and deterministic execution plans. Future orchestrators, agents, connectors, and industry plugins need a durable and domain-neutral way to record what actually happened during execution.

Mutable status rows alone are insufficient because they discard intermediate history and weaken auditability, replay, debugging, analytics, and governance.

## Decision

The Universal Execution Engine will treat an append-only execution record as the authoritative history of execution activity.

Each `ExecutionPlan` creates one or more `ExecutionRun` records. A run owns:

- ordered immutable `ExecutionEvent` records;
- references to `ExecutionArtifact` outputs;
- at most one terminal `ExecutionOutcome` in v1.

The planner decides what should happen. The orchestrator coordinates what is happening. The execution record preserves what did happen.

The core domain is storage-neutral. `ExecutionEventStore` defines the persistence contract. `InMemoryExecutionEventStore` is the reference implementation for tests and local development; production adapters may use PostgreSQL, DynamoDB, Cosmos DB, SQLite, or another durable store.

## Invariants

1. Events are append-only and strictly sequenced per execution run.
2. All timestamps are timezone-aware.
3. External artifacts are represented by immutable metadata and storage URIs; the core does not require a particular blob store.
4. Current run status can be replayed from the event stream.
5. Blocked or non-actionable plans create blocked runs and cannot start until a future governed transition resolves the blockers.
6. Outcome recording emits an audit event and is single-assignment in schema v1.
7. No event, artifact, or outcome performs an external action by itself.

## Consequences

### Positive

- Complete audit and governance history
- Deterministic replay and debugging
- Domain-neutral commercial packaging
- Foundation for metrics, learning, and outcome analysis
- Storage adapters can evolve without changing the domain model

### Tradeoffs

- Event stores require concurrency controls around sequence assignment
- Derived status must be tested against all event transitions
- Schema evolution and event migration require explicit versioning

## Canonical lifecycle

```text
Opportunity
    ↓
Evidence
    ↓
Qualification
    ↓
MissionCandidate
    ↓
ExecutionPlan
    ↓
ExecutionRun
    ├── ExecutionEvents
    ├── ExecutionArtifacts
    └── ExecutionOutcome
```

## Follow-on work

- Integrate execution-record creation into the intake artifact pipeline
- Add a durable JSON or database event-store adapter
- Implement governed state transitions and approval gates
- Add execution timeline and metrics projections
- Define plugin interfaces for AEGENTIX and third-party execution strategies
