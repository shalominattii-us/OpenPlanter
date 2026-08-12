from __future__ import annotations

import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .result import ExecutionArtifactResult


@dataclass(frozen=True)
class MaterializedArtifact:
    """A plugin artifact written to durable local storage."""

    uri: str
    checksum_sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ArtifactMaterializer:
    """Write plugin-produced artifact bytes beneath a controlled root.

    Plugins provide content but never choose arbitrary filesystem locations.
    The runtime derives the final path from run, step, and artifact identity,
    writes atomically, and returns the exact checksum recorded by the ledger.
    """

    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root))

    def materialize(
        self,
        execution_run_id: str,
        step_id: str,
        artifact: ExecutionArtifactResult,
    ) -> MaterializedArtifact:
        if artifact.content is None:
            raise ValueError("artifact content is required for materialization")

        run_segment = _safe_segment(execution_run_id, "execution_run_id")
        step_segment = _safe_segment(step_id, "step_id")
        name = _safe_name(artifact.name)
        destination = self.root / run_segment / step_segment / name
        destination.parent.mkdir(parents=True, exist_ok=True)

        payload = artifact.content_bytes
        temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
        try:
            temporary.write_bytes(payload)
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()

        return MaterializedArtifact(
            uri=destination.resolve().as_uri(),
            checksum_sha256=sha256(payload).hexdigest(),
            size_bytes=len(payload),
        )


def _safe_segment(value: str, field: str) -> str:
    text = value.strip()
    if not text or text in {".", ".."} or "/" in text or "\\" in text:
        raise ValueError(f"{field} contains an unsafe path segment")
    return text


def _safe_name(value: str) -> str:
    name = Path(value).name
    if name != value or name in {"", ".", ".."}:
        raise ValueError("artifact name must be a safe file name")
    return name
