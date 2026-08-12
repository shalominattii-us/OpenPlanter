from __future__ import annotations

import json
from dataclasses import dataclass

from ..execution import ExecutionStep, ExecutionStepKind
from .capabilities import Capability
from .request import ExecutionRequest
from .result import ExecutionArtifactResult, ExecutionResult


@dataclass(frozen=True)
class EligibilityExecutorPlugin:
    """Build a deterministic eligibility matrix from request facts and memory."""

    plugin_id: str = "eligibility-executor"
    version: str = "1.0.0"

    def capabilities(self) -> frozenset[Capability]:
        return frozenset({Capability.ELIGIBILITY})

    def supports(self, step: ExecutionStep) -> bool:
        return step.kind is ExecutionStepKind.VERIFY_ELIGIBILITY

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not self.supports(request.step):
            return ExecutionResult.failed(
                message=(
                    f"eligibility executor does not support step kind "
                    f"{request.step.kind.value}"
                ),
                metadata={
                    "request_id": request.request_id,
                    "step_id": request.step.step_id,
                },
            )

        requirements = tuple(
            str(item).strip()
            for item in request.metadata.get("eligibility", ())
            if str(item).strip()
        )
        matrix = tuple(
            {
                "requirement": requirement,
                "status": "requires_evidence",
                "evidence": [],
                "gap": f"Evidence has not yet been attached for: {requirement}",
                "owner": None,
            }
            for requirement in requirements
        )
        prior_research_completed = bool(request.execution_memory.completed_steps)
        payload = {
            "schema_version": "eligibility-matrix-v1",
            "execution_run_id": request.execution_run_id,
            "step_id": request.step.step_id,
            "requires_operator_review": True,
            "prior_research_completed": prior_research_completed,
            "requirements": list(requirements),
            "matrix": list(matrix),
        }

        artifact = ExecutionArtifactResult(
            name="eligibility-matrix.json",
            uri=(
                f"execution://{request.execution_run_id}/steps/"
                f"{request.step.step_id}/eligibility-matrix.json"
            ),
            media_type="application/json",
            content=json.dumps(payload, indent=2, sort_keys=True) + "\n",
        )

        return ExecutionResult.succeeded(
            message="Eligibility requirements mapped for operator review.",
            artifacts=(artifact,),
            metrics={
                "eligibility.requirement_count": float(len(requirements)),
                "eligibility.evidence_gaps": float(len(matrix)),
                "eligibility.prior_steps": float(
                    len(request.execution_memory.completed_steps)
                ),
            },
            metadata={
                "request_id": request.request_id,
                "execution_run_id": request.execution_run_id,
                "step_id": request.step.step_id,
                "requirements": requirements,
                "matrix": matrix,
                "requires_operator_review": True,
                "prior_research_completed": prior_research_completed,
                "trace_id": request.trace_id,
            },
        )
