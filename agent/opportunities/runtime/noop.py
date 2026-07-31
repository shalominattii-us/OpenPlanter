from __future__ import annotations

from dataclasses import dataclass

from ..execution import ExecutionStep
from ..lifecycle import ExecutionContext
from .capabilities import Capability
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

    def execute(
        self,
        context: ExecutionContext,
        step: ExecutionStep,
    ) -> ExecutionResult:
        return ExecutionResult.succeeded(
            message=f"No-op execution completed for {step.step_id}",
            metadata={
                "execution_run_id": context.execution_run.execution_run_id,
                "step_id": step.step_id,
            },
        )
