from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..execution import ExecutionStep, ExecutionStepKind
from .capabilities import Capability
from .request import ExecutionRequest
from .result import ExecutionArtifactResult, ExecutionResult


_REQUIRED_ARTIFACTS = frozenset({"submission-receipt.json"})


@dataclass(frozen=True)
class OutcomeTrackingExecutorPlugin:
    """Close the deterministic lifecycle with a durable outcome baseline.

    This executor records what the engine can prove at execution time. It does
    not invent acceptance, revenue, award, or response outcomes that have not
    occurred. Later field adapters can append observed outcome evidence while
    preserving this original baseline record.
    """

    plugin_id: str = "outcome-tracking-executor"
    version: str = "1.0.0"

    def capabilities(self) -> frozenset[Capability]:
        return frozenset({Capability.REPORTING})

    def supports(self, step: ExecutionStep) -> bool:
        return step.kind is ExecutionStepKind.TRACK_OUTCOME

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not self.supports(request.step):
            return ExecutionResult.failed(
                message=(
                    "outcome tracker does not support step kind "
                    f"{request.step.kind.value}"
                ),
                metadata={"request_id": request.request_id, "step_id": request.step.step_id},
            )

        available = frozenset(item.name for item in request.execution_memory.artifacts)
        missing = tuple(sorted(_REQUIRED_ARTIFACTS - available))
        if missing:
            return ExecutionResult.failed(
                message="outcome tracking requires a completed submission receipt",
                metadata={
                    "request_id": request.request_id,
                    "step_id": request.step.step_id,
                    "missing_artifacts": missing,
                },
            )

        outcome = {
            "schema_version": "universal-execution-outcome-v1",
            "execution_run_id": request.execution_run_id,
            "step_id": request.step.step_id,
            "opportunity_id": request.inputs.get("opportunity_id"),
            "title": request.inputs.get("title"),
            "issuer": request.inputs.get("issuer"),
            "submission_path": request.inputs.get("submission_path"),
            "execution_status": "completed",
            "submission_status": "simulated_not_sent",
            "external_action_performed": False,
            "observed_outcome": "awaiting_real_transport_and_external_response",
            "financial_outcome": {
                "revenue_recognized": 0,
                "currency": "USD",
                "award_status": "not_observed",
            },
            "evidence_status": "baseline_recorded",
            "source_artifacts": tuple(sorted(available)),
            "next_actions": (
                "configure an approved real submission transport",
                "record external acknowledgment or response evidence",
                "update award, revenue, and delivery outcomes when observed",
            ),
        }
        artifact = ExecutionArtifactResult(
            name="outcome-record.json",
            uri=(
                f"execution://{request.execution_run_id}/steps/"
                f"{request.step.step_id}/outcome-record.json"
            ),
            media_type="application/json",
            content=_json_bytes(outcome),
        )
        return ExecutionResult.succeeded(
            message="Execution outcome baseline recorded without inventing external results.",
            artifacts=(artifact,),
            metrics={
                "outcome.output_count": 1.0,
                "outcome.external_actions": 0.0,
                "outcome.revenue_recognized": 0.0,
                "outcome.source_artifacts": float(len(available)),
            },
            metadata={
                "request_id": request.request_id,
                "execution_run_id": request.execution_run_id,
                "step_id": request.step.step_id,
                "observed_outcome": "awaiting_real_transport_and_external_response",
                "external_action_performed": False,
                "source_artifacts": tuple(sorted(available)),
                "trace_id": request.trace_id,
            },
        )


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
