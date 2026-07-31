from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..execution import ExecutionStep
from ..lifecycle import ExecutionContext
from .capabilities import Capability
from .result import ExecutionResult


@runtime_checkable
class ExecutionPlugin(Protocol):
    """Pure execution provider contract.

    Plugins perform work and return information. They never mutate the supplied
    execution context or advance orchestration state.
    """

    plugin_id: str
    version: str

    def capabilities(self) -> frozenset[Capability]:
        ...

    def supports(self, step: ExecutionStep) -> bool:
        ...

    def execute(
        self,
        context: ExecutionContext,
        step: ExecutionStep,
    ) -> ExecutionResult:
        ...
