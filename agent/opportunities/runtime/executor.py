from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from time import perf_counter
from typing import Any, Mapping

from ..execution import ExecutionStep
from ..execution_record import ExecutionEventType
from ..lifecycle import ExecutionContext
from .memory import ExecutionMemory
from .registry import PluginRegistry
from .request import ExecutionRequest
from .result import ExecutionResult
from .routing import route_plugin


def _request_id(execution_run_id: str, step_id: str) -> str:
    digest = sha256(f"{execution_run_id}|{step_id}".encode("utf-8")).hexdigest()[:20]
    return f"req_{digest}"


def _build_memory(context: ExecutionContext) -> ExecutionMemory:
    completed_steps = tuple(
        {
            "event_id": event.event_id,
            "sequence": event.sequence,
            "step_id": event.step_id,
            "occurred_at": event.occurred_at.isoformat(),
            "details": dict(event.details),
        }
        for event in context.events
        if event.event_type == ExecutionEventType.STEP_COMPLETED
    )
    return ExecutionMemory(
        completed_steps=completed_steps,
        artifacts=context.artifacts,
        variables={
            "execution_plan_id": context.execution_plan.execution_plan_id,
            "mission_candidate_id": context.mission_candidate.mission_candidate_id,
            "opportunity_id": context.opportunity.opportunity_id,
            "opportunity_version": context.opportunity.version,
        },
    )


@dataclass(frozen=True)
class PluginRuntime:
    """Build immutable requests and execute plugins without mutating state."""

    registry: PluginRegistry

    def build_request(
        self,
        context: ExecutionContext,
        step: ExecutionStep,
        *,
        configuration: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        trace_id: str = "",
    ) -> ExecutionRequest:
        if step.step_id not in {
            planned_step.step_id for planned_step in context.execution_plan.steps
        }:
            raise ValueError("step does not belong to execution context plan")

        request_id = _request_id(
            context.execution_run.execution_run_id,
            step.step_id,
        )
        request_metadata = {
            "execution_plan_id": context.execution_plan.execution_plan_id,
            "mission_candidate_id": context.mission_candidate.mission_candidate_id,
            "opportunity_id": context.opportunity.opportunity_id,
            "eligibility": tuple(context.opportunity.eligibility),
            **dict(metadata or {}),
        }
        return ExecutionRequest(
            request_id=request_id,
            execution_run_id=context.execution_run.execution_run_id,
            step=step,
            execution_memory=_build_memory(context),
            inputs=step.inputs,
            configuration=configuration or {},
            metadata=request_metadata,
            trace_id=trace_id,
        )

    def execute(
        self,
        context: ExecutionContext,
        step: ExecutionStep,
        *,
        configuration: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        trace_id: str = "",
    ) -> ExecutionResult:
        plugin = route_plugin(self.registry, step)
        request = self.build_request(
            context,
            step,
            configuration=configuration,
            metadata=metadata,
            trace_id=trace_id,
        )
        started = perf_counter()
        result = plugin.execute(request)
        if not isinstance(result, ExecutionResult):
            raise TypeError(
                f"plugin {plugin.plugin_id} returned {type(result).__name__}; "
                "expected ExecutionResult"
            )
        elapsed_ms = (perf_counter() - started) * 1000
        result_metadata = result.metadata_map
        result_metadata.update(
            {
                "plugin_id": plugin.plugin_id,
                "plugin_version": plugin.version,
                "request_id": request.request_id,
                "step_id": step.step_id,
                "trace_id": request.trace_id,
            }
        )
        metrics = result.metrics_map
        metrics.setdefault("runtime.elapsed_ms", elapsed_ms)
        return ExecutionResult(
            success=result.success,
            message=result.message,
            artifacts=result.artifacts,
            metrics=tuple(sorted(metrics.items())),
            metadata=tuple(sorted(result_metadata.items())),
        )
