from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ..execution import ExecutionStep
from ..execution_record import ExecutionRunStatus
from ..lifecycle import ExecutionContext
from ..orchestrator import DeterministicExecutionOrchestrator, StepStatus
from .executor import PluginRuntime
from .integration import ExecutionResultIntegrator
from .materialization import ArtifactMaterializer


_TERMINAL_RUN_STATUSES = frozenset(
    {
        ExecutionRunStatus.COMPLETED,
        ExecutionRunStatus.FAILED,
        ExecutionRunStatus.CANCELLED,
        ExecutionRunStatus.BLOCKED,
    }
)


@dataclass(frozen=True)
class DeterministicExecutionService:
    """Execute one eligible plan step through the established boundaries."""

    orchestrator: DeterministicExecutionOrchestrator
    runtime: PluginRuntime
    integrator: ExecutionResultIntegrator

    @classmethod
    def create(
        cls,
        orchestrator: DeterministicExecutionOrchestrator,
        runtime: PluginRuntime,
        *,
        artifact_root: str | Path | None = None,
    ) -> "DeterministicExecutionService":
        materializer = (
            None if artifact_root is None else ArtifactMaterializer(Path(artifact_root))
        )
        return cls(
            orchestrator=orchestrator,
            runtime=runtime,
            integrator=ExecutionResultIntegrator(orchestrator, materializer),
        )

    def execute_next_step(
        self,
        context: ExecutionContext,
        *,
        actor: str,
        occurred_at: datetime | None = None,
        configuration: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        trace_id: str = "",
    ) -> ExecutionContext:
        """Execute at most one step and return the refreshed execution context.

        Created runs are started automatically. Explicit-approval steps stop at
        ``AWAITING_APPROVAL``. Once approved, the already-running approved step
        is dispatched before any later dependent step is considered.
        """

        timestamp = _time(occurred_at)
        fresh = self.orchestrator.lifecycle.refresh(context)

        if fresh.execution_run.status in _TERMINAL_RUN_STATUSES:
            raise ValueError(
                f"execution run cannot advance from {fresh.execution_run.status.value}"
            )
        if fresh.execution_run.status == ExecutionRunStatus.AWAITING_APPROVAL:
            return fresh
        if fresh.execution_run.status == ExecutionRunStatus.CREATED:
            fresh = self.orchestrator.start_run(
                fresh,
                actor=actor,
                occurred_at=timestamp,
            )

        state = self.orchestrator.state(fresh)
        running = tuple(item.step_id for item in state.steps if item.status == StepStatus.RUNNING)
        if len(running) > 1:
            raise ValueError("execution state contains multiple running steps")

        if running:
            step = _step(fresh, running[0])
        else:
            step_id = state.next_step_id
            if step_id is None:
                return fresh
            step = _step(fresh, step_id)
            fresh = self.orchestrator.start_step(
                fresh,
                step.step_id,
                actor=actor,
                occurred_at=timestamp,
            )
            if self.orchestrator.state(fresh).step(step.step_id).status == StepStatus.AWAITING_APPROVAL:
                return fresh

        try:
            result = self.runtime.execute(
                fresh,
                step,
                configuration=configuration,
                metadata=metadata,
                trace_id=trace_id,
            )
        except Exception as exc:
            return self.orchestrator.fail_step(
                fresh,
                step.step_id,
                actor=actor,
                reason=f"executor raised {type(exc).__name__}: {exc}",
                occurred_at=timestamp,
            )

        return self.integrator.apply(
            fresh,
            step,
            result,
            actor=actor,
            occurred_at=timestamp,
        )


def _step(context: ExecutionContext, step_id: str) -> ExecutionStep:
    for step in context.execution_plan.steps:
        if step.step_id == step_id:
            return step
    raise KeyError(f"unknown execution step: {step_id}")


def _time(value: datetime | None) -> datetime:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        raise ValueError("occurred_at must be timezone-aware")
    return timestamp
