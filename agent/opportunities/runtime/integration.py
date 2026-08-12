from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..execution import ExecutionStep
from ..lifecycle import ExecutionContext
from ..orchestrator import DeterministicExecutionOrchestrator, StepStatus
from .materialization import ArtifactMaterializer
from .result import ExecutionResult


@dataclass(frozen=True)
class ExecutionResultIntegrator:
    """Translate plugin information into authoritative execution records.

    Plugins remain authority-poor: they return an ``ExecutionResult``. This
    service optionally materializes artifact payloads, records the exact durable
    files, and delegates all state transitions to the orchestrator and recorder.
    """

    orchestrator: DeterministicExecutionOrchestrator
    materializer: ArtifactMaterializer | None = None

    def apply(
        self,
        context: ExecutionContext,
        step: ExecutionStep,
        result: ExecutionResult,
        *,
        actor: str,
        occurred_at: datetime | None = None,
    ) -> ExecutionContext:
        timestamp = occurred_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")

        fresh = self.orchestrator.lifecycle.refresh(context)
        if step.step_id not in {
            planned.step_id for planned in fresh.execution_plan.steps
        }:
            raise ValueError("step does not belong to execution context plan")
        if self.orchestrator.state(fresh).step(step.step_id).status != StepStatus.RUNNING:
            raise ValueError("step must be running before applying a result")

        if not result.success:
            return self.orchestrator.fail_step(
                fresh,
                step.step_id,
                actor=actor,
                reason=result.message or "executor returned an unsuccessful result",
                occurred_at=timestamp,
            )

        artifact_ids: list[str] = []
        for artifact in result.artifacts:
            uri = artifact.uri
            checksum = None
            materialization_metadata: dict[str, Any] = {}
            if self.materializer is not None and artifact.content is not None:
                materialized = self.materializer.materialize(
                    fresh.execution_run.execution_run_id,
                    step.step_id,
                    artifact,
                )
                uri = materialized.uri
                checksum = materialized.checksum_sha256
                materialization_metadata = {
                    "materialized": True,
                    "size_bytes": materialized.size_bytes,
                    "logical_uri": artifact.uri,
                }

            recorded = self.orchestrator.recorder.record_artifact(
                fresh.execution_run.execution_run_id,
                name=artifact.name,
                uri=uri,
                media_type=artifact.media_type or "application/octet-stream",
                actor=actor,
                created_at=timestamp,
                checksum_sha256=checksum,
                step_id=step.step_id,
                metadata={
                    "plugin_id": result.metadata_map.get("plugin_id"),
                    "plugin_version": result.metadata_map.get("plugin_version"),
                    "request_id": result.metadata_map.get("request_id"),
                    "trace_id": result.metadata_map.get("trace_id"),
                    **materialization_metadata,
                },
            )
            artifact_ids.append(recorded.artifact_id)

        details: dict[str, Any] = {
            "message": result.message,
            "artifact_ids": artifact_ids,
            "metrics": result.metrics_map,
            "result_metadata": result.metadata_map,
        }
        return self.orchestrator.complete_step(
            fresh,
            step.step_id,
            actor=actor,
            occurred_at=timestamp,
            details=details,
        )
