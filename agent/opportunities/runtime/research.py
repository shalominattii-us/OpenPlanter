from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from ..execution import ExecutionStep, ExecutionStepKind
from .capabilities import Capability
from .request import ExecutionRequest
from .result import ExecutionArtifactResult, ExecutionResult


_REQUIRED_FACTS = (
    "opportunity_id",
    "title",
    "issuer",
    "deadline",
    "submission_path",
)


@dataclass(frozen=True)
class ResearchExecutorPlugin:
    """Deterministically prepare a validated opportunity research brief.

    This executor consumes only the immutable plugin request. It performs no
    orchestration, persistence, network access, or state mutation. The returned
    result is information for the runtime and orchestrator to interpret.
    """

    plugin_id: str = "research-executor"
    version: str = "1.0.0"

    def capabilities(self) -> frozenset[Capability]:
        return frozenset({Capability.RESEARCH})

    def supports(self, step: ExecutionStep) -> bool:
        return step.kind is ExecutionStepKind.RESEARCH

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not self.supports(request.step):
            return ExecutionResult.failed(
                message=(
                    f"research executor does not support step kind "
                    f"{request.step.kind.value}"
                ),
                metadata={
                    "request_id": request.request_id,
                    "step_id": request.step.step_id,
                },
            )

        facts = _opportunity_facts(request.inputs)
        present = tuple(key for key in _REQUIRED_FACTS if facts[key] not in (None, ""))
        missing = tuple(key for key in _REQUIRED_FACTS if facts[key] in (None, ""))
        completeness = len(present) / len(_REQUIRED_FACTS)
        brief = {
            "schema_version": "validated-opportunity-brief-v1",
            "execution_run_id": request.execution_run_id,
            "step_id": request.step.step_id,
            "facts": facts,
            "validated_fields": list(present),
            "missing_fields": list(missing),
            "fact_completeness": completeness,
        }

        artifact = ExecutionArtifactResult(
            name="validated-opportunity-brief.json",
            uri=(
                f"execution://{request.execution_run_id}/"
                f"steps/{request.step.step_id}/validated-opportunity-brief.json"
            ),
            media_type="application/json",
            content=json.dumps(brief, indent=2, sort_keys=True) + "\n",
        )

        return ExecutionResult.succeeded(
            message="Opportunity research brief prepared.",
            artifacts=(artifact,),
            metrics={
                "research.fact_completeness": completeness,
                "research.facts_present": float(len(present)),
                "research.facts_missing": float(len(missing)),
                "research.prior_artifacts": float(
                    len(request.execution_memory.artifacts)
                ),
                "research.prior_findings": float(
                    len(request.execution_memory.findings)
                ),
            },
            metadata={
                "request_id": request.request_id,
                "execution_run_id": request.execution_run_id,
                "step_id": request.step.step_id,
                "brief": facts,
                "validated_fields": present,
                "missing_fields": missing,
                "memory_is_empty": request.execution_memory.is_empty,
                "trace_id": request.trace_id,
            },
        )


def _opportunity_facts(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Project the stable research facts supplied by the execution plan."""

    return {key: inputs.get(key) for key in _REQUIRED_FACTS}
