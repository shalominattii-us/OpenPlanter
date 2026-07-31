from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from ..execution import ExecutionStep
from .memory import ExecutionMemory


def _freeze_value(value: Any) -> Any:
    """Recursively detach and freeze values crossing the plugin boundary."""

    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, tuple):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze_value(item) for item in value)
    return value


def _freeze_mapping(values: Mapping[str, Any]) -> Mapping[str, Any]:
    copied = {
        str(key): _freeze_value(value)
        for key, value in values.items()
    }
    return MappingProxyType(copied)


@dataclass(frozen=True)
class ExecutionRequest:
    """Immutable working package supplied to one execution plugin.

    The request contains information, not orchestration authority. Runtime code
    constructs it; plugins may inspect it but cannot use it to mutate engine
    state or the caller-owned mappings from which it was built.
    """

    request_id: str
    execution_run_id: str
    step: ExecutionStep
    execution_memory: ExecutionMemory = field(default_factory=ExecutionMemory)
    inputs: Mapping[str, Any] = field(default_factory=dict)
    configuration: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    trace_id: str = ""

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("request_id is required")
        if not self.execution_run_id.strip():
            raise ValueError("execution_run_id is required")

        trace_id = self.trace_id.strip() or self.request_id
        object.__setattr__(self, "trace_id", trace_id)
        object.__setattr__(self, "inputs", _freeze_mapping(self.inputs))
        object.__setattr__(
            self,
            "configuration",
            _freeze_mapping(self.configuration),
        )
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))
