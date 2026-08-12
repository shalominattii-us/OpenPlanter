from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..execution import ExecutionStep
from .capabilities import Capability
from .request import ExecutionRequest
from .result import ExecutionResult


@runtime_checkable
class ExecutionPlugin(Protocol):
    """Pure execution provider contract.

    Plugins perform work from an immutable request and return information. They
    never receive orchestration services or advance workflow state.
    """

    plugin_id: str
    version: str

    def capabilities(self) -> frozenset[Capability]:
        ...

    def supports(self, step: ExecutionStep) -> bool:
        ...

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        ...
