from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from .execution import ApprovalRequirement, ExecutionStep
from .execution_record import (
    ExecutionEventType,
    ExecutionRecorder,
    ExecutionRunStatus,
)
from .lifecycle import ExecutionContext, ExecutionLifecycle


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass(frozen=True)
class StepState:
    step_id: str
    status: StepStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = None


@dataclass(frozen=True)
class OrchestrationState:
    execution_run_id: str
    run_status: ExecutionRunStatus
    steps: tuple[StepState, ...]

    def step(self, step_id: str) -> StepState:
        for state in self.steps:
            if state.step_id == step_id:
                return state
        raise KeyError(f"unknown execution step: {step_id}")

    @property
    def next_step_id(self) -> str | None:
        for state in self.steps:
            if state.status == StepStatus.PENDING:
                return state.step_id
        return None


class DeterministicExecutionOrchestrator:
    """Validate and record replayable, approval-gated execution transitions.

    The orchestrator does not perform external work. Future executors and plugins
    operate between `start_step` and `complete_step` while this service remains
    the authoritative transition coordinator.
    """

    def __init__(self, lifecycle: ExecutionLifecycle) -> None:
        self.lifecycle = lifecycle
        self.recorder: ExecutionRecorder = lifecycle.recorder

    def state(self, context: ExecutionContext) -> OrchestrationState:
        return replay_orchestration_state(self.lifecycle.refresh(context))

    def start_run(
        self,
        context: ExecutionContext,
        *,
        actor: str,
        occurred_at: datetime | None = None,
    ) -> ExecutionContext:
        self.recorder.start_run(
            context.execution_run.execution_run_id,
            actor=actor,
            occurred_at=_time(occurred_at),
        )
        return self.lifecycle.refresh(context)

    def start_step(
        self,
        context: ExecutionContext,
        step_id: str,
        *,
        actor: str,
        occurred_at: datetime | None = None,
    ) -> ExecutionContext:
        fresh = self.lifecycle.refresh(context)
        state = replay_orchestration_state(fresh)
        step = _step(fresh, step_id)
        if fresh.execution_run.status != ExecutionRunStatus.RUNNING:
            raise ValueError("execution run must be running before a step can start")
        if state.step(step_id).status != StepStatus.PENDING:
            raise ValueError(f"step is not pending: {step_id}")
        _require_dependencies_complete(state, step)
        if state.next_step_id != step_id:
            raise ValueError("steps must start in deterministic plan order")

        timestamp = _time(occurred_at)
        if step.approval == ApprovalRequirement.EXPLICIT_APPROVAL:
            self.recorder.append_event(
                fresh.execution_run.execution_run_id,
                ExecutionEventType.APPROVAL_REQUESTED,
                actor=actor,
                occurred_at=timestamp,
                step_id=step_id,
                details={"approval": step.approval.value},
            )
            self.lifecycle.store.update_run(
                replace(fresh.execution_run, status=ExecutionRunStatus.AWAITING_APPROVAL)
            )
        else:
            self.recorder.append_event(
                fresh.execution_run.execution_run_id,
                ExecutionEventType.STEP_STARTED,
                actor=actor,
                occurred_at=timestamp,
                step_id=step_id,
            )
        return self.lifecycle.refresh(fresh)

    def approve_step(
        self,
        context: ExecutionContext,
        step_id: str,
        *,
        actor: str,
        occurred_at: datetime | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> ExecutionContext:
        fresh = self.lifecycle.refresh(context)
        if replay_orchestration_state(fresh).step(step_id).status != StepStatus.AWAITING_APPROVAL:
            raise ValueError("step is not awaiting approval")
        timestamp = _time(occurred_at)
        self.recorder.append_event(
            fresh.execution_run.execution_run_id,
            ExecutionEventType.APPROVED,
            actor=actor,
            occurred_at=timestamp,
            step_id=step_id,
            details=details,
        )
        self.lifecycle.store.update_run(
            replace(fresh.execution_run, status=ExecutionRunStatus.RUNNING)
        )
        self.recorder.append_event(
            fresh.execution_run.execution_run_id,
            ExecutionEventType.STEP_STARTED,
            actor=actor,
            occurred_at=timestamp,
            step_id=step_id,
        )
        return self.lifecycle.refresh(fresh)

    def reject_step(
        self,
        context: ExecutionContext,
        step_id: str,
        *,
        actor: str,
        reason: str,
        occurred_at: datetime | None = None,
    ) -> ExecutionContext:
        fresh = self.lifecycle.refresh(context)
        if replay_orchestration_state(fresh).step(step_id).status != StepStatus.AWAITING_APPROVAL:
            raise ValueError("step is not awaiting approval")
        timestamp = _time(occurred_at)
        self.recorder.append_event(
            fresh.execution_run.execution_run_id,
            ExecutionEventType.REJECTED,
            actor=actor,
            occurred_at=timestamp,
            step_id=step_id,
            details={"reason": reason},
        )
        self.lifecycle.store.update_run(
            replace(fresh.execution_run, status=ExecutionRunStatus.CANCELLED, completed_at=timestamp)
        )
        self.recorder.append_event(
            fresh.execution_run.execution_run_id,
            ExecutionEventType.RUN_CANCELLED,
            actor=actor,
            occurred_at=timestamp,
            details={"reason": reason, "step_id": step_id},
        )
        return self.lifecycle.refresh(fresh)

    def complete_step(
        self,
        context: ExecutionContext,
        step_id: str,
        *,
        actor: str,
        occurred_at: datetime | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> ExecutionContext:
        fresh = self.lifecycle.refresh(context)
        if replay_orchestration_state(fresh).step(step_id).status != StepStatus.RUNNING:
            raise ValueError("step is not running")
        timestamp = _time(occurred_at)
        self.recorder.append_event(
            fresh.execution_run.execution_run_id,
            ExecutionEventType.STEP_COMPLETED,
            actor=actor,
            occurred_at=timestamp,
            step_id=step_id,
            details=details,
        )
        refreshed = self.lifecycle.refresh(fresh)
        if replay_orchestration_state(refreshed).next_step_id is None:
            self.recorder.complete_run(
                refreshed.execution_run.execution_run_id,
                actor=actor,
                occurred_at=timestamp,
            )
        return self.lifecycle.refresh(refreshed)

    def fail_step(
        self,
        context: ExecutionContext,
        step_id: str,
        *,
        actor: str,
        reason: str,
        occurred_at: datetime | None = None,
    ) -> ExecutionContext:
        fresh = self.lifecycle.refresh(context)
        if replay_orchestration_state(fresh).step(step_id).status != StepStatus.RUNNING:
            raise ValueError("step is not running")
        timestamp = _time(occurred_at)
        self.recorder.append_event(
            fresh.execution_run.execution_run_id,
            ExecutionEventType.STEP_FAILED,
            actor=actor,
            occurred_at=timestamp,
            step_id=step_id,
            details={"reason": reason},
        )
        self.lifecycle.store.update_run(
            replace(fresh.execution_run, status=ExecutionRunStatus.FAILED, completed_at=timestamp)
        )
        self.recorder.append_event(
            fresh.execution_run.execution_run_id,
            ExecutionEventType.RUN_FAILED,
            actor=actor,
            occurred_at=timestamp,
            details={"reason": reason, "step_id": step_id},
        )
        return self.lifecycle.refresh(fresh)


def replay_orchestration_state(context: ExecutionContext) -> OrchestrationState:
    states = {
        step.step_id: StepState(step.step_id, StepStatus.PENDING)
        for step in context.execution_plan.steps
    }
    for event in context.events:
        if event.step_id is None or event.step_id not in states:
            continue
        current = states[event.step_id]
        if event.event_type == ExecutionEventType.APPROVAL_REQUESTED:
            states[event.step_id] = replace(current, status=StepStatus.AWAITING_APPROVAL)
        elif event.event_type == ExecutionEventType.REJECTED:
            states[event.step_id] = replace(current, status=StepStatus.REJECTED)
        elif event.event_type == ExecutionEventType.STEP_STARTED:
            states[event.step_id] = replace(
                current, status=StepStatus.RUNNING, started_at=event.occurred_at
            )
        elif event.event_type == ExecutionEventType.STEP_COMPLETED:
            states[event.step_id] = replace(
                current, status=StepStatus.COMPLETED, completed_at=event.occurred_at
            )
        elif event.event_type == ExecutionEventType.STEP_FAILED:
            states[event.step_id] = replace(
                current,
                status=StepStatus.FAILED,
                completed_at=event.occurred_at,
                failure_reason=str(event.details.get("reason") or "step failed"),
            )
    return OrchestrationState(
        execution_run_id=context.execution_run.execution_run_id,
        run_status=context.execution_run.status,
        steps=tuple(states[step.step_id] for step in context.execution_plan.steps),
    )


def _step(context: ExecutionContext, step_id: str) -> ExecutionStep:
    for step in context.execution_plan.steps:
        if step.step_id == step_id:
            return step
    raise KeyError(f"unknown execution step: {step_id}")


def _require_dependencies_complete(state: OrchestrationState, step: ExecutionStep) -> None:
    incomplete = [
        dependency
        for dependency in step.depends_on
        if state.step(dependency).status != StepStatus.COMPLETED
    ]
    if incomplete:
        raise ValueError(f"step dependencies are incomplete: {incomplete}")


def _time(value: datetime | None) -> datetime:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("occurred_at must be timezone-aware")
    return timestamp
