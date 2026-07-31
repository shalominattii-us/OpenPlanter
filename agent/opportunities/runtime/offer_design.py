from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..execution import ExecutionStep, ExecutionStepKind
from .capabilities import Capability
from .request import ExecutionRequest
from .result import ExecutionArtifactResult, ExecutionResult


_REQUIRED_ARTIFACTS = frozenset(
    {"validated-opportunity-brief.json", "eligibility-matrix.json"}
)


@dataclass(frozen=True)
class OfferDesignExecutorPlugin:
    """Design a deterministic, mutually beneficial offer from prior work."""

    plugin_id: str = "offer-design-executor"
    version: str = "1.0.0"

    def capabilities(self) -> frozenset[Capability]:
        return frozenset({Capability.OFFER_DESIGN})

    def supports(self, step: ExecutionStep) -> bool:
        return step.kind is ExecutionStepKind.DESIGN_OFFER

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not self.supports(request.step):
            return ExecutionResult.failed(
                message=(
                    "offer design executor does not support step kind "
                    f"{request.step.kind.value}"
                ),
                metadata={"request_id": request.request_id, "step_id": request.step.step_id},
            )

        available = frozenset(item.name for item in request.execution_memory.artifacts)
        missing = tuple(sorted(_REQUIRED_ARTIFACTS - available))
        if missing:
            return ExecutionResult.failed(
                message="offer design requires completed research and eligibility artifacts",
                metadata={
                    "request_id": request.request_id,
                    "step_id": request.step.step_id,
                    "missing_artifacts": missing,
                },
            )

        title = str(request.inputs.get("title") or "Untitled opportunity")
        issuer = request.inputs.get("issuer")
        deadline = request.inputs.get("deadline")
        submission_path = request.inputs.get("submission_path")

        offer = {
            "schema_version": "universal-offer-design-v1",
            "opportunity_id": request.inputs.get("opportunity_id"),
            "title": title,
            "recipient": issuer,
            "recipient_outcome": (
                f"Provide {issuer or 'the recipient'} a reviewable, evidence-backed solution "
                f"for {title}."
            ),
            "provider_outcome": (
                "Create a bounded delivery engagement with measurable value, reusable "
                "intellectual property, and a documented path to sustainable revenue."
            ),
            "delivery_model": {
                "phase_1": "validate scope, constraints, and acceptance criteria",
                "phase_2": "build and review the minimum complete deliverable",
                "phase_3": "deliver, measure outcomes, and capture reusable learning",
            },
            "success_criteria": (
                "recipient requirements are mapped to evidence",
                "deliverables have explicit acceptance criteria",
                "cost, schedule, and risk assumptions are reviewable",
                "external submission remains approval gated",
            ),
            "deadline": deadline,
            "submission_path": submission_path,
            "source_artifacts": tuple(sorted(available)),
        }
        value_model = {
            "schema_version": "universal-value-model-v1",
            "opportunity_id": request.inputs.get("opportunity_id"),
            "value_exchange": {
                "recipient_receives": (
                    "a validated solution, transparent delivery plan, measurable outcomes, "
                    "and lower execution uncertainty"
                ),
                "provider_receives": (
                    "revenue, validated product knowledge, reusable delivery assets, and "
                    "referenceable performance evidence subject to agreement"
                ),
            },
            "commercial_model": {
                "pricing_status": "requires_operator_review",
                "recommended_structure": "milestone-based fixed scope with controlled change",
                "payment_triggers": (
                    "scope acceptance",
                    "reviewable prototype or draft delivery",
                    "final acceptance",
                ),
            },
            "risk_controls": (
                "no external commitment without explicit approval",
                "eligibility gaps must be resolved before submission",
                "assumptions must be converted into acceptance criteria",
            ),
        }

        artifacts = (
            ExecutionArtifactResult(
                name="offer-design.json",
                uri=(
                    f"execution://{request.execution_run_id}/steps/"
                    f"{request.step.step_id}/offer-design.json"
                ),
                media_type="application/json",
                content=_json_bytes(offer),
            ),
            ExecutionArtifactResult(
                name="value-model.json",
                uri=(
                    f"execution://{request.execution_run_id}/steps/"
                    f"{request.step.step_id}/value-model.json"
                ),
                media_type="application/json",
                content=_json_bytes(value_model),
            ),
        )
        return ExecutionResult.succeeded(
            message="Mutually beneficial offer and value model designed for review.",
            artifacts=artifacts,
            metrics={
                "offer.source_artifacts": float(len(available)),
                "offer.success_criteria": float(len(offer["success_criteria"])),
                "offer.output_count": float(len(artifacts)),
            },
            metadata={
                "request_id": request.request_id,
                "execution_run_id": request.execution_run_id,
                "step_id": request.step.step_id,
                "offer": offer,
                "value_model": value_model,
                "requires_operator_review": True,
                "trace_id": request.trace_id,
            },
        )


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
