from __future__ import annotations

from dataclasses import dataclass

from ..execution import ExecutionStep
from .capabilities import Capability
from .request import ExecutionRequest
from .result import ExecutionResult


@dataclass(frozen=True)
class NoOpPlugin:
    """Reference plugin for validation, tests, and plugin-author guidance."""

    declared_capabilities: frozenset[Capability]
    plugin_id: str = "noop"
    version: str = "1.0.0"

    def capabilities(self) -> frozenset[Capability]:
        return self.declared_capabilities

    def supports(self, step: ExecutionStep) -> bool:
        return True

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult.succeeded(
            message=f"No-op execution completed for {request.step.step_id}",
            metadata={
                "execution_run_id": request.execution_run_id,
                "request_id": request.request_id,
                "step_id": request.step.step_id,
                "trace_id": request.trace_id,
            },
        )
