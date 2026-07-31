from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from ..execution_record import ExecutionArtifact
from .request import _freeze_mapping, _freeze_value


def _freeze_records(
    records: tuple[Mapping[str, Any], ...],
) -> tuple[Mapping[str, Any], ...]:
    return tuple(_freeze_mapping(record) for record in records)


@dataclass(frozen=True)
class ExecutionMemory:
    """Immutable accumulated knowledge supplied to an execution plugin.

    Memory is a read-only snapshot assembled by the runtime. It exposes prior
    completed-step summaries, structured findings, recorded artifacts, and
    shared variables without granting access to orchestration services or the
    mutable event store.
    """

    completed_steps: tuple[Mapping[str, Any], ...] = ()
    findings: tuple[Mapping[str, Any], ...] = ()
    artifacts: tuple[ExecutionArtifact, ...] = ()
    variables: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "completed_steps",
            _freeze_records(tuple(self.completed_steps)),
        )
        object.__setattr__(
            self,
            "findings",
            _freeze_records(tuple(self.findings)),
        )
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        object.__setattr__(self, "variables", _freeze_mapping(self.variables))

    @property
    def is_empty(self) -> bool:
        return not (
            self.completed_steps
            or self.findings
            or self.artifacts
            or self.variables
        )
