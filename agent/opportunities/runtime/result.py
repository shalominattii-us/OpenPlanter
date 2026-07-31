from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ExecutionArtifactResult:
    """A plugin-produced artifact payload and logical reference.

    The payload is information only. Plugins do not choose the authoritative
    storage location; a runtime materializer may replace the logical URI with a
    durable URI before the artifact is recorded.
    """

    name: str
    uri: str
    media_type: str | None = None
    content: str | bytes | None = None
    encoding: str = "utf-8"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("artifact name is required")
        if not self.uri.strip():
            raise ValueError("artifact uri is required")
        if isinstance(self.content, str) and not self.encoding.strip():
            raise ValueError("artifact encoding is required for text content")
        if self.content is not None and not isinstance(self.content, (str, bytes)):
            raise TypeError("artifact content must be text, bytes, or None")

    @property
    def content_bytes(self) -> bytes:
        if self.content is None:
            raise ValueError("artifact content is not available")
        if isinstance(self.content, bytes):
            return self.content
        return self.content.encode(self.encoding)


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
