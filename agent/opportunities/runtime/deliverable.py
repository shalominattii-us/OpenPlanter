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
        "validated-opportunity-brief.json",
        "eligibility-matrix.json",
        "offer-design.json",
        "value-model.json",
    }
)


@dataclass(frozen=True)
class DeliverableBuilderExecutorPlugin:
    """Build a deterministic response package for operator review."""

    plugin_id: str = "deliverable-builder-executor"
    version: str = "1.0.0"

    def capabilities(self) -> frozenset[Capability]:
        return frozenset({Capability.DOCUMENT})

    def supports(self, step: ExecutionStep) -> bool:
        return step.kind is ExecutionStepKind.BUILD_DELIVERABLE

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not self.supports(request.step):
            return ExecutionResult.failed(
                message=(
                    "deliverable builder does not support step kind "
                    f"{request.step.kind.value}"
                ),
                metadata={"request_id": request.request_id, "step_id": request.step.step_id},
            )

        available = frozenset(item.name for item in request.execution_memory.artifacts)
        missing = tuple(sorted(_REQUIRED_ARTIFACTS - available))
        if missing:
            return ExecutionResult.failed(
                message="response package requires research, eligibility, offer, and value artifacts",
                metadata={
                    "request_id": request.request_id,
                    "step_id": request.step.step_id,
                    "missing_artifacts": missing,
                },
            )

        title = str(request.inputs.get("title") or "Untitled opportunity")
        issuer = str(request.inputs.get("issuer") or "Opportunity issuer")
        deadline = request.inputs.get("deadline")
        submission_path = request.inputs.get("submission_path")

        proposal = _proposal_markdown(
            title=title,
            issuer=issuer,
            deadline=deadline,
            submission_path=submission_path,
        )
        implementation_plan = {
            "schema_version": "universal-implementation-plan-v1",
            "opportunity_id": request.inputs.get("opportunity_id"),
            "title": title,
            "phases": (
                {
                    "name": "discovery_and_validation",
                    "objective": "confirm scope, constraints, evidence, and acceptance criteria",
                    "exit_criteria": "operator-approved scope and evidence map",
                },
                {
                    "name": "minimum_complete_delivery",
                    "objective": "produce the smallest complete solution satisfying approved criteria",
                    "exit_criteria": "reviewable deliverable with verification evidence",
                },
                {
                    "name": "acceptance_and_learning",
                    "objective": "support acceptance, measure outcomes, and capture reusable knowledge",
                    "exit_criteria": "accepted outcome record and documented lessons",
                },
            ),
            "governance": {
                "external_submission": "explicit_approval_required",
                "scope_changes": "operator_review_required",
                "commercial_commitments": "operator_review_required",
            },
        }
        budget_assumptions = {
            "schema_version": "universal-budget-assumptions-v1",
            "opportunity_id": request.inputs.get("opportunity_id"),
            "pricing_status": "requires_operator_review",
            "currency": "USD",
            "cost_categories": (
                "discovery_and_requirements",
                "engineering_and_delivery",
                "verification_and_quality",
                "project_governance",
                "contingency",
            ),
            "assumptions": (
                "final price requires validated scope and delivery schedule",
                "third-party costs are excluded until identified and approved",
                "changes to acceptance criteria require controlled re-estimation",
            ),
            "committed_amount": None,
        }

        artifacts = (
            ExecutionArtifactResult(
                name="proposal-draft.md",
                uri=_uri(request, "proposal-draft.md"),
                media_type="text/markdown",
                content=proposal,
            ),
            ExecutionArtifactResult(
                name="implementation-plan.json",
                uri=_uri(request, "implementation-plan.json"),
                media_type="application/json",
                content=_json_bytes(implementation_plan),
            ),
            ExecutionArtifactResult(
                name="budget-assumptions.json",
                uri=_uri(request, "budget-assumptions.json"),
                media_type="application/json",
                content=_json_bytes(budget_assumptions),
            ),
        )
        return ExecutionResult.succeeded(
            message="Reviewable response package prepared without external commitment.",
            artifacts=artifacts,
            metrics={
                "deliverable.source_artifacts": float(len(available)),
                "deliverable.output_count": float(len(artifacts)),
                "deliverable.phase_count": float(len(implementation_plan["phases"])),
            },
            metadata={
                "request_id": request.request_id,
                "execution_run_id": request.execution_run_id,
                "step_id": request.step.step_id,
                "source_artifacts": tuple(sorted(available)),
                "requires_operator_review": True,
                "external_action_performed": False,
                "trace_id": request.trace_id,
            },
        )


def _uri(request: ExecutionRequest, name: str) -> str:
    return (
        f"execution://{request.execution_run_id}/steps/"
        f"{request.step.step_id}/{name}"
    )


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _proposal_markdown(*, title: str, issuer: str, deadline: Any, submission_path: Any) -> str:
    return f"""# Proposal Draft: {title}

## Recipient
{issuer}

## Executive Summary
This draft proposes a bounded, evidence-backed engagement designed to produce measurable value for {issuer} while preserving transparent scope, governance, and acceptance criteria.

## Proposed Outcomes
- Validate the recipient's requirements, constraints, and success measures.
- Deliver the minimum complete solution required to satisfy approved acceptance criteria.
- Provide verification evidence, implementation documentation, and reusable operational learning.

## Delivery Approach
1. Discovery and validation.
2. Minimum complete delivery.
3. Acceptance, measurement, and learning.

## Governance and Risk Controls
- No external submission or contractual commitment occurs without explicit approval.
- Pricing, schedule, scope, and legal terms remain subject to operator review.
- Eligibility and evidence gaps must be resolved before submission.

## Opportunity Details
- Deadline: {deadline or 'Not specified'}
- Submission path: {submission_path or 'Not specified'}

## Review Status
Draft for operator review. Not submitted. Not contractually binding.
"""