from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..execution import ExecutionStep, ExecutionStepKind
from .capabilities import Capability
from .request import ExecutionRequest
from .result import ExecutionArtifactResult, ExecutionResult


_REQUIRED_ARTIFACTS = frozenset(
    {
        "outreach-draft.md",
        "submission-checklist.md",
        "contact-brief.json",
        "proposal-draft.md",
        "implementation-plan.json",
        "budget-assumptions.json",
    }
)


@dataclass(frozen=True)
class ApprovalGatedSubmissionExecutorPlugin:
    """Create a deterministic local submission receipt after approval.

    The orchestrator is responsible for the explicit approval gate. This first
    transport performs no network, email, portal, or API action; it proves the
    complete approved execution path and leaves a durable receipt suitable for
    later replacement by a configured real transport adapter.
    """

    plugin_id: str = "approval-gated-local-submission-executor"
    version: str = "1.0.0"

    def capabilities(self) -> frozenset[Capability]:
        return frozenset({Capability.SUBMISSION})

    def supports(self, step: ExecutionStep) -> bool:
        return step.kind is ExecutionStepKind.SUBMIT_RESPONSE

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not self.supports(request.step):
            return ExecutionResult.failed(
                message=(
                    "submission executor does not support step kind "
                    f"{request.step.kind.value}"
                ),
                metadata={"request_id": request.request_id, "step_id": request.step.step_id},
            )

        available = frozenset(item.name for item in request.execution_memory.artifacts)
        missing = tuple(sorted(_REQUIRED_ARTIFACTS - available))
        if missing:
            return ExecutionResult.failed(
                message="submission requires the completed response and outreach package",
                metadata={
                    "request_id": request.request_id,
                    "step_id": request.step.step_id,
                    "missing_artifacts": missing,
                },
            )

        receipt = {
            "schema_version": "universal-submission-receipt-v1",
            "execution_run_id": request.execution_run_id,
            "step_id": request.step.step_id,
            "opportunity_id": request.inputs.get("opportunity_id"),
            "title": request.inputs.get("title"),
            "issuer": request.inputs.get("issuer"),
            "submission_path": request.inputs.get("submission_path"),
            "transport": "local_receipt",
            "submission_status": "simulated_not_sent",
            "external_action_performed": False,
            "approval_boundary": "satisfied_by_orchestrator_before_dispatch",
            "source_artifacts": tuple(sorted(available)),
            "next_action": "configure and explicitly authorize a real transport adapter",
        }
        artifact = ExecutionArtifactResult(
            name="submission-receipt.json",
            uri=(
                f"execution://{request.execution_run_id}/steps/"
                f"{request.step.step_id}/submission-receipt.json"
            ),
            media_type="application/json",
            content=_json_bytes(receipt),
        )
        return ExecutionResult.succeeded(
            message="Approved submission path validated through local receipt transport.",
            artifacts=(artifact,),
            metrics={
                "submission.output_count": 1.0,
                "submission.external_actions": 0.0,
                "submission.source_artifacts": float(len(available)),
            },
            metadata={
                "request_id": request.request_id,
                "execution_run_id": request.execution_run_id,
                "step_id": request.step.step_id,
                "transport": "local_receipt",
                "submission_status": "simulated_not_sent",
                "external_action_performed": False,
                "source_artifacts": tuple(sorted(available)),
                "trace_id": request.trace_id,
            },
        )


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
