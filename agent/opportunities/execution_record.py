from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from threading import RLock
from typing import Any, Mapping, Protocol, Sequence

from .execution import ExecutionPlan, ExecutionPlanStatus


EXECUTION_RECORD_SCHEMA_VERSION = "universal-execution-record-v1"


class ExecutionRunStatus(str, Enum):
    CREATED = "created"
    BLOCKED = "blocked"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionEventType(str, Enum):
    PLAN_CREATED = "plan_created"
    RUN_STARTED = "run_started"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARTIFACT_RECORDED = "artifact_recorded"
    OUTCOME_RECORDED = "outcome_recorded"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"


class ExecutionOutcomeStatus(str, Enum):
    WON = "won"
    LOST = "lost"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REVISION_REQUESTED = "revision_requested"
    CLOSED = "closed"


@dataclass(frozen=True)
class ExecutionRun:
    execution_run_id: str
    execution_plan_id: str
    mission_candidate_id: str
    opportunity_id: str
    status: ExecutionRunStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    schema_version: str = EXECUTION_RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")
        if self.started_at is not None:
            _require_aware(self.started_at, "started_at")
        if self.completed_at is not None:
            _require_aware(self.completed_at, "completed_at")
        if not self.execution_run_id.strip():
            raise ValueError("execution_run_id is required")
        if self.completed_at is not None and self.started_at is None:
            raise ValueError("completed runs must have started_at")


@dataclass(frozen=True)
class ExecutionEvent:
    event_id: str
    execution_run_id: str
    sequence: int
    event_type: ExecutionEventType
    occurred_at: datetime
    actor: str
    step_id: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = EXECUTION_RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("sequence must be at least 1")
        _require_aware(self.occurred_at, "occurred_at")
        if not self.actor.strip():
            raise ValueError("actor is required")


@dataclass(frozen=True)
class ExecutionArtifact:
    artifact_id: str
    execution_run_id: str
    name: str
    uri: str
    media_type: str
    created_at: datetime
    checksum_sha256: str | None = None
    step_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = EXECUTION_RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_aware(self.created_at, "created_at")
        if not self.name.strip():
            raise ValueError("name is required")
        if not self.uri.strip():
            raise ValueError("uri is required")
        if not self.media_type.strip():
            raise ValueError("media_type is required")


@dataclass(frozen=True)
class ExecutionOutcome:
    outcome_id: str
    execution_run_id: str
    status: ExecutionOutcomeStatus
    recorded_at: datetime
    summary: str
    value: float | None = None
    currency: str | None = None
    metrics: Mapping[str, float] = field(default_factory=dict)
    lessons: tuple[str, ...] = ()
    schema_version: str = EXECUTION_RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_aware(self.recorded_at, "recorded_at")
        if not self.summary.strip():
            raise ValueError("summary is required")
        if self.value is not None and self.value < 0:
            raise ValueError("value cannot be negative")
        if self.currency is not None and len(self.currency.strip()) != 3:
            raise ValueError("currency must be a three-letter code")


class ExecutionEventStore(Protocol):
    def create_run(self, run: ExecutionRun) -> None: ...

    def get_run(self, execution_run_id: str) -> ExecutionRun: ...

    def update_run(self, run: ExecutionRun) -> None: ...

    def append_event(self, event: ExecutionEvent) -> None: ...

    def events_for_run(self, execution_run_id: str) -> tuple[ExecutionEvent, ...]: ...

    def record_artifact(self, artifact: ExecutionArtifact) -> None: ...

    def artifacts_for_run(self, execution_run_id: str) -> tuple[ExecutionArtifact, ...]: ...

    def record_outcome(self, outcome: ExecutionOutcome) -> None: ...

    def outcome_for_run(self, execution_run_id: str) -> ExecutionOutcome | None: ...


class InMemoryExecutionEventStore:
    """Thread-safe reference store for tests, local use, and adapter development."""

    def __init__(self) -> None:
        self._runs: dict[str, ExecutionRun] = {}
        self._events: dict[str, list[ExecutionEvent]] = {}
        self._artifacts: dict[str, list[ExecutionArtifact]] = {}
        self._outcomes: dict[str, ExecutionOutcome] = {}
        self._lock = RLock()

    def create_run(self, run: ExecutionRun) -> None:
        with self._lock:
            if run.execution_run_id in self._runs:
                raise ValueError(f"execution run already exists: {run.execution_run_id}")
            self._runs[run.execution_run_id] = run
            self._events[run.execution_run_id] = []
            self._artifacts[run.execution_run_id] = []

    def get_run(self, execution_run_id: str) -> ExecutionRun:
        with self._lock:
            try:
                return self._runs[execution_run_id]
            except KeyError as exc:
                raise KeyError(f"unknown execution run: {execution_run_id}") from exc

    def update_run(self, run: ExecutionRun) -> None:
        with self._lock:
            if run.execution_run_id not in self._runs:
                raise KeyError(f"unknown execution run: {run.execution_run_id}")
            self._runs[run.execution_run_id] = run

    def append_event(self, event: ExecutionEvent) -> None:
        with self._lock:
            events = self._events.get(event.execution_run_id)
            if events is None:
                raise KeyError(f"unknown execution run: {event.execution_run_id}")
            expected = len(events) + 1
            if event.sequence != expected:
                raise ValueError(
                    f"event sequence must be {expected} for run {event.execution_run_id}"
                )
            events.append(event)

    def events_for_run(self, execution_run_id: str) -> tuple[ExecutionEvent, ...]:
        with self._lock:
            if execution_run_id not in self._events:
                raise KeyError(f"unknown execution run: {execution_run_id}")
            return tuple(self._events[execution_run_id])

    def record_artifact(self, artifact: ExecutionArtifact) -> None:
        with self._lock:
            artifacts = self._artifacts.get(artifact.execution_run_id)
            if artifacts is None:
                raise KeyError(f"unknown execution run: {artifact.execution_run_id}")
            if any(existing.artifact_id == artifact.artifact_id for existing in artifacts):
                raise ValueError(f"artifact already exists: {artifact.artifact_id}")
            artifacts.append(artifact)

    def artifacts_for_run(self, execution_run_id: str) -> tuple[ExecutionArtifact, ...]:
        with self._lock:
            if execution_run_id not in self._artifacts:
                raise KeyError(f"unknown execution run: {execution_run_id}")
            return tuple(self._artifacts[execution_run_id])

    def record_outcome(self, outcome: ExecutionOutcome) -> None:
        with self._lock:
            if outcome.execution_run_id not in self._runs:
                raise KeyError(f"unknown execution run: {outcome.execution_run_id}")
            if outcome.execution_run_id in self._outcomes:
                raise ValueError("an execution outcome has already been recorded")
            self._outcomes[outcome.execution_run_id] = outcome

    def outcome_for_run(self, execution_run_id: str) -> ExecutionOutcome | None:
        with self._lock:
            if execution_run_id not in self._runs:
                raise KeyError(f"unknown execution run: {execution_run_id}")
            return self._outcomes.get(execution_run_id)


class ExecutionRecorder:
    """Authoritative service for append-only execution history."""

    def __init__(self, store: ExecutionEventStore) -> None:
        self.store = store

    def create_for_plan(
        self,
        plan: ExecutionPlan,
        *,
        actor: str = "universal-execution-engine",
        occurred_at: datetime | None = None,
    ) -> ExecutionRun:
        timestamp = occurred_at or datetime.now(timezone.utc)
        initial_status = (
            ExecutionRunStatus.BLOCKED
            if plan.status in {ExecutionPlanStatus.BLOCKED, ExecutionPlanStatus.NOT_ACTIONABLE}
            else ExecutionRunStatus.CREATED
        )
        run = ExecutionRun(
            execution_run_id=_stable_id("exr", plan.execution_plan_id),
            execution_plan_id=plan.execution_plan_id,
            mission_candidate_id=plan.mission_candidate_id,
            opportunity_id=plan.opportunity_id,
            status=initial_status,
            created_at=timestamp,
        )
        self.store.create_run(run)
        self.append_event(
            run.execution_run_id,
            ExecutionEventType.PLAN_CREATED,
            actor=actor,
            occurred_at=timestamp,
            details={
                "execution_plan_id": plan.execution_plan_id,
                "plan_status": plan.status.value,
                "step_count": len(plan.steps),
                "blockers": list(plan.blockers),
            },
        )
        return run

    def start_run(
        self,
        execution_run_id: str,
        *,
        actor: str,
        occurred_at: datetime | None = None,
    ) -> ExecutionRun:
        run = self.store.get_run(execution_run_id)
        if run.status == ExecutionRunStatus.BLOCKED:
            raise ValueError("blocked execution runs cannot be started")
        if run.started_at is not None:
            raise ValueError("execution run has already started")
        timestamp = occurred_at or datetime.now(timezone.utc)
        updated = replace(
            run,
            status=ExecutionRunStatus.RUNNING,
            started_at=timestamp,
        )
        self.store.update_run(updated)
        self.append_event(
            execution_run_id,
            ExecutionEventType.RUN_STARTED,
            actor=actor,
            occurred_at=timestamp,
        )
        return updated

    def append_event(
        self,
        execution_run_id: str,
        event_type: ExecutionEventType,
        *,
        actor: str,
        occurred_at: datetime | None = None,
        step_id: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> ExecutionEvent:
        timestamp = occurred_at or datetime.now(timezone.utc)
        sequence = len(self.store.events_for_run(execution_run_id)) + 1
        event = ExecutionEvent(
            event_id=_stable_id(
                "exe", execution_run_id, str(sequence), event_type.value, timestamp.isoformat()
            ),
            execution_run_id=execution_run_id,
            sequence=sequence,
            event_type=event_type,
            occurred_at=timestamp,
            actor=actor,
            step_id=step_id,
            details=dict(details or {}),
        )
        self.store.append_event(event)
        return event

    def record_artifact(
        self,
        execution_run_id: str,
        *,
        name: str,
        uri: str,
        media_type: str,
        actor: str,
        created_at: datetime | None = None,
        checksum_sha256: str | None = None,
        step_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ExecutionArtifact:
        timestamp = created_at or datetime.now(timezone.utc)
        artifact = ExecutionArtifact(
            artifact_id=_stable_id("exa", execution_run_id, name, uri),
            execution_run_id=execution_run_id,
            name=name,
            uri=uri,
            media_type=media_type,
            created_at=timestamp,
            checksum_sha256=checksum_sha256,
            step_id=step_id,
            metadata=dict(metadata or {}),
        )
        self.store.record_artifact(artifact)
        self.append_event(
            execution_run_id,
            ExecutionEventType.ARTIFACT_RECORDED,
            actor=actor,
            occurred_at=timestamp,
            step_id=step_id,
            details={"artifact_id": artifact.artifact_id, "name": name, "uri": uri},
        )
        return artifact

    def record_outcome(
        self,
        execution_run_id: str,
        *,
        status: ExecutionOutcomeStatus,
        summary: str,
        actor: str,
        recorded_at: datetime | None = None,
        value: float | None = None,
        currency: str | None = None,
        metrics: Mapping[str, float] | None = None,
        lessons: Sequence[str] = (),
    ) -> ExecutionOutcome:
        timestamp = recorded_at or datetime.now(timezone.utc)
        outcome = ExecutionOutcome(
            outcome_id=_stable_id("exo", execution_run_id, status.value),
            execution_run_id=execution_run_id,
            status=status,
            recorded_at=timestamp,
            summary=summary,
            value=value,
            currency=currency.upper() if currency else None,
            metrics=dict(metrics or {}),
            lessons=tuple(lessons),
        )
        self.store.record_outcome(outcome)
        self.append_event(
            execution_run_id,
            ExecutionEventType.OUTCOME_RECORDED,
            actor=actor,
            occurred_at=timestamp,
            details={
                "outcome_id": outcome.outcome_id,
                "status": status.value,
                "value": value,
                "currency": outcome.currency,
            },
        )
        return outcome

    def complete_run(
        self,
        execution_run_id: str,
        *,
        actor: str,
        occurred_at: datetime | None = None,
    ) -> ExecutionRun:
        run = self.store.get_run(execution_run_id)
        if run.started_at is None:
            raise ValueError("execution run must be started before completion")
        timestamp = occurred_at or datetime.now(timezone.utc)
        updated = replace(
            run,
            status=ExecutionRunStatus.COMPLETED,
            completed_at=timestamp,
        )
        self.store.update_run(updated)
        self.append_event(
            execution_run_id,
            ExecutionEventType.RUN_COMPLETED,
            actor=actor,
            occurred_at=timestamp,
        )
        return updated

    def timeline(self, execution_run_id: str) -> tuple[ExecutionEvent, ...]:
        return self.store.events_for_run(execution_run_id)


def derive_status(events: Sequence[ExecutionEvent]) -> ExecutionRunStatus:
    """Replay events to derive the latest execution status without mutating history."""

    status = ExecutionRunStatus.CREATED
    for event in events:
        if event.event_type == ExecutionEventType.RUN_STARTED:
            status = ExecutionRunStatus.RUNNING
        elif event.event_type == ExecutionEventType.APPROVAL_REQUESTED:
            status = ExecutionRunStatus.AWAITING_APPROVAL
        elif event.event_type == ExecutionEventType.APPROVED:
            status = ExecutionRunStatus.RUNNING
        elif event.event_type in {ExecutionEventType.STEP_FAILED, ExecutionEventType.RUN_FAILED}:
            status = ExecutionRunStatus.FAILED
        elif event.event_type == ExecutionEventType.RUN_CANCELLED:
            status = ExecutionRunStatus.CANCELLED
        elif event.event_type == ExecutionEventType.RUN_COMPLETED:
            status = ExecutionRunStatus.COMPLETED
    return status


def _stable_id(prefix: str, *parts: str) -> str:
    digest = sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
