from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from ..execution_record import ExecutionRunStatus
from ..lifecycle import ExecutionContext
from .service import DeterministicExecutionService


class ExecutionCheckpoint(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    AWAITING_APPROVAL = "awaiting_approval"
    STEP_LIMIT_REACHED = "step_limit_reached"


@dataclass(frozen=True)
class ExecutionRunReport:
    context: ExecutionContext
    checkpoint: ExecutionCheckpoint
    steps_attempted: int
    initial_event_count: int
    final_event_count: int

    @property
    def events_recorded(self) -> int:
        return self.final_event_count - self.initial_event_count


@dataclass(frozen=True)
class DeterministicRunLoop:
    """Advance execution until a terminal or human-controlled checkpoint.

    The loop coordinates repeated calls to ``execute_next_step``. It never
    approves work, bypasses gates, invokes plugins directly, or records events.
    """

    service: DeterministicExecutionService
    default_max_steps: int = 100

    def __post_init__(self) -> None:
        if self.default_max_steps < 1:
            raise ValueError("default_max_steps must be at least 1")

    def execute_until_checkpoint(
        self,
        context: ExecutionContext,
        *,
        actor: str,
        occurred_at: datetime | None = None,
        configuration: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        trace_id: str = "",
        max_steps: int | None = None,
    ) -> ExecutionRunReport:
        limit = self.default_max_steps if max_steps is None else max_steps
        if limit < 1:
            raise ValueError("max_steps must be at least 1")

        current = self.service.orchestrator.lifecycle.refresh(context)
        initial_event_count = len(current.events)
        attempted = 0

        checkpoint = _checkpoint(current.execution_run.status)
        if checkpoint is not None:
            return _report(current, checkpoint, attempted, initial_event_count)

        while attempted < limit:
            current = self.service.execute_next_step(
                current,
                actor=actor,
                occurred_at=occurred_at,
                configuration=configuration,
                metadata=metadata,
                trace_id=trace_id,
            )
            attempted += 1

            checkpoint = _checkpoint(current.execution_run.status)
            if checkpoint is not None:
                return _report(current, checkpoint, attempted, initial_event_count)

        return _report(
            current,
            ExecutionCheckpoint.STEP_LIMIT_REACHED,
            attempted,
            initial_event_count,
        )


def _checkpoint(status: ExecutionRunStatus) -> ExecutionCheckpoint | None:
    return {
        ExecutionRunStatus.COMPLETED: ExecutionCheckpoint.COMPLETED,
        ExecutionRunStatus.FAILED: ExecutionCheckpoint.FAILED,
        ExecutionRunStatus.CANCELLED: ExecutionCheckpoint.CANCELLED,
        ExecutionRunStatus.BLOCKED: ExecutionCheckpoint.BLOCKED,
        ExecutionRunStatus.AWAITING_APPROVAL: ExecutionCheckpoint.AWAITING_APPROVAL,
    }.get(status)


def _report(
    context: ExecutionContext,
    checkpoint: ExecutionCheckpoint,
    attempted: int,
    initial_event_count: int,
) -> ExecutionRunReport:
    return ExecutionRunReport(
        context=context,
        checkpoint=checkpoint,
        steps_attempted=attempted,
        initial_event_count=initial_event_count,
        final_event_count=len(context.events),
    )
