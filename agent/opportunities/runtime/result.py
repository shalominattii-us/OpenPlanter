from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ExecutionArtifactResult:
    """A plugin-produced artifact reference, not orchestration state."""

    name: str
    uri: str
    media_type: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("artifact name is required")
        if not self.uri.strip():
            raise ValueError("artifact uri is required")


@dataclass(frozen=True)
class ExecutionResult:
    """Immutable information returned by a plugin to the runtime.

    Results never advance execution state. The orchestrator remains the sole
    authority for workflow transitions and event recording.
    """

    success: bool
    message: str | None = None
    artifacts: tuple[ExecutionArtifactResult, ...] = ()
    metrics: tuple[tuple[str, float], ...] = ()
    metadata: tuple[tuple[str, Any], ...] = ()

    @classmethod
    def succeeded(
        cls,
        *,
        message: str | None = None,
        artifacts: tuple[ExecutionArtifactResult, ...] = (),
        metrics: Mapping[str, float] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "ExecutionResult":
        return cls(
            success=True,
            message=message,
            artifacts=artifacts,
            metrics=_sorted_items(metrics),
            metadata=_sorted_items(metadata),
        )

    @classmethod
    def failed(
        cls,
        *,
        message: str,
        metrics: Mapping[str, float] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "ExecutionResult":
        if not message.strip():
            raise ValueError("failure message is required")
        return cls(
            success=False,
            message=message,
            metrics=_sorted_items(metrics),
            metadata=_sorted_items(metadata),
        )

    @property
    def metrics_map(self) -> dict[str, float]:
        return dict(self.metrics)

    @property
    def metadata_map(self) -> dict[str, Any]:
        return dict(self.metadata)


def _sorted_items(values: Mapping[str, Any] | None) -> tuple[tuple[str, Any], ...]:
    return tuple(sorted((values or {}).items(), key=lambda item: item[0]))
