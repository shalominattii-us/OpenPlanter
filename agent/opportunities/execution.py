from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Mapping, Sequence

from .domain import MissionCandidate, Opportunity, QualificationStatus


EXECUTION_PLAN_SCHEMA_VERSION = "universal-opportunity-execution-plan-v1"


class ExecutionPlanStatus(str, Enum):
    READY_FOR_REVIEW = "ready_for_review"
    BLOCKED = "blocked"
    NOT_ACTIONABLE = "not_actionable"


class ExecutionStepKind(str, Enum):
    RESEARCH = "research"
    VERIFY_ELIGIBILITY = "verify_eligibility"
    DESIGN_OFFER = "design_offer"
    BUILD_DELIVERABLE = "build_deliverable"
    PREPARE_OUTREACH = "prepare_outreach"
    SUBMIT_RESPONSE = "submit_response"
    TRACK_OUTCOME = "track_outcome"


class ApprovalRequirement(str, Enum):
    NONE = "none"
    OPERATOR_REVIEW = "operator_review"
    EXPLICIT_APPROVAL = "explicit_approval"


@dataclass(frozen=True)
class ExecutionStep:
    step_id: str
    sequence: int
    kind: ExecutionStepKind
    title: str
    objective: str
    approval: ApprovalRequirement
    depends_on: tuple[str, ...] = ()
    inputs: Mapping[str, Any] = field(default_factory=dict)
    outputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.sequence < 1:
            raise ValueError("sequence must be at least 1")
        if not self.step_id.strip():
            raise ValueError("step_id is required")
        if not self.title.strip():
            raise ValueError("title is required")
        if not self.objective.strip():
            raise ValueError("objective is required")


@dataclass(frozen=True)
class ExecutionPlan:
    execution_plan_id: str
    mission_candidate_id: str
    opportunity_id: str
    opportunity_version: int
    status: ExecutionPlanStatus
    created_at: datetime
    steps: tuple[ExecutionStep, ...]
    blockers: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    schema_version: str = EXECUTION_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        sequences = [step.sequence for step in self.steps]
        if sequences != list(range(1, len(self.steps) + 1)):
            raise ValueError("execution steps must have contiguous sequence numbers")
        known_ids = {step.step_id for step in self.steps}
        for step in self.steps:
            missing = set(step.depends_on) - known_ids
            if missing:
                raise ValueError(f"unknown step dependencies: {sorted(missing)}")

    @property
    def requires_explicit_approval(self) -> bool:
        return any(
            step.approval == ApprovalRequirement.EXPLICIT_APPROVAL
            for step in self.steps
        )


@dataclass(frozen=True)
class ExecutionPolicy:
    """Build deterministic, review-gated plans without performing external actions."""

    policy_version: str = "universal-execution-v1"
    require_approval_for_external_actions: bool = True

    def plan(
        self,
        opportunity: Opportunity,
        candidate: MissionCandidate,
        *,
        created_at: datetime | None = None,
    ) -> ExecutionPlan:
        if candidate.opportunity_id != opportunity.opportunity_id:
            raise ValueError("mission candidate does not belong to opportunity")
        if candidate.opportunity_version != opportunity.version:
            raise ValueError("mission candidate references another opportunity version")

        created = created_at or datetime.now(timezone.utc)
        plan_id = _plan_id(candidate, self.policy_version)

        if candidate.decision.status == QualificationStatus.REJECTED:
            return ExecutionPlan(
                execution_plan_id=plan_id,
                mission_candidate_id=candidate.mission_candidate_id,
                opportunity_id=opportunity.opportunity_id,
                opportunity_version=opportunity.version,
                status=ExecutionPlanStatus.NOT_ACTIONABLE,
                created_at=created,
                steps=(),
                blockers=("qualification decision rejected the opportunity",),
            )

        blockers = _derive_blockers(opportunity)
        steps = _build_steps(opportunity, plan_id, self)
        status = (
            ExecutionPlanStatus.BLOCKED
            if blockers
            else ExecutionPlanStatus.READY_FOR_REVIEW
        )
        assumptions = (
            "All externally visible communications require human review.",
            "No funds, credentials, contracts, or submissions are committed by this plan.",
            "Source facts must be revalidated before execution.",
        )
        return ExecutionPlan(
            execution_plan_id=plan_id,
            mission_candidate_id=candidate.mission_candidate_id,
            opportunity_id=opportunity.opportunity_id,
            opportunity_version=opportunity.version,
            status=status,
            created_at=created,
            steps=steps,
            blockers=blockers,
            assumptions=assumptions,
        )


def _plan_id(candidate: MissionCandidate, policy_version: str) -> str:
    digest = sha256(
        f"{candidate.mission_candidate_id}|{policy_version}".encode("utf-8")
    ).hexdigest()[:20]
    return f"exp_{digest}"


def _step_id(plan_id: str, sequence: int, kind: ExecutionStepKind) -> str:
    digest = sha256(f"{plan_id}|{sequence}|{kind.value}".encode("utf-8")).hexdigest()[:16]
    return f"exs_{digest}"


def _derive_blockers(opportunity: Opportunity) -> tuple[str, ...]:
    blockers: list[str] = []
    if opportunity.deadline is None:
        blockers.append("submission deadline is unknown")
    if not opportunity.submission_path:
        blockers.append("submission or contact path is unknown")
    if not opportunity.eligibility:
        blockers.append("eligibility requirements are not recorded")
    return tuple(blockers)


def _build_steps(
    opportunity: Opportunity,
    plan_id: str,
    policy: ExecutionPolicy,
) -> tuple[ExecutionStep, ...]:
    specs: Sequence[tuple[ExecutionStepKind, str, str, ApprovalRequirement, tuple[str, ...]]] = (
        (
            ExecutionStepKind.RESEARCH,
            "Validate opportunity facts",
            "Confirm the issuer, scope, deadline, value, and authoritative source materials.",
            ApprovalRequirement.NONE,
            ("validated-opportunity-brief.json",),
        ),
        (
            ExecutionStepKind.VERIFY_ELIGIBILITY,
            "Verify eligibility and constraints",
            "Map every eligibility requirement to evidence, gaps, and an owner.",
            ApprovalRequirement.OPERATOR_REVIEW,
            ("eligibility-matrix.md",),
        ),
        (
            ExecutionStepKind.DESIGN_OFFER,
            "Design the mutually beneficial offer",
            "Define the recipient outcome, business value, delivery model, economics, and measurable success criteria.",
            ApprovalRequirement.OPERATOR_REVIEW,
            ("offer-design.md", "value-model.json"),
        ),
        (
            ExecutionStepKind.BUILD_DELIVERABLE,
            "Build the response package",
            "Produce the proposal, product concept, implementation plan, budget, and supporting evidence required for review.",
            ApprovalRequirement.OPERATOR_REVIEW,
            ("response-package/",),
        ),
        (
            ExecutionStepKind.PREPARE_OUTREACH,
            "Prepare contact and submission materials",
            "Draft concise outreach and assemble the final submission checklist without sending anything.",
            ApprovalRequirement.OPERATOR_REVIEW,
            ("outreach-draft.md", "submission-checklist.md"),
        ),
        (
            ExecutionStepKind.SUBMIT_RESPONSE,
            "Submit or send the approved response",
            "Perform the external submission only after explicit operator approval and a final validation pass.",
            (
                ApprovalRequirement.EXPLICIT_APPROVAL
                if policy.require_approval_for_external_actions
                else ApprovalRequirement.OPERATOR_REVIEW
            ),
            ("submission-receipt.json",),
        ),
        (
            ExecutionStepKind.TRACK_OUTCOME,
            "Track outcomes and learning",
            "Record responses, revenue signals, costs, decisions, and lessons for future qualification and execution.",
            ApprovalRequirement.NONE,
            ("outcome-record.json",),
        ),
    )

    steps: list[ExecutionStep] = []
    for index, (kind, title, objective, approval, outputs) in enumerate(specs, start=1):
        previous = (steps[-1].step_id,) if steps else ()
        steps.append(
            ExecutionStep(
                step_id=_step_id(plan_id, index, kind),
                sequence=index,
                kind=kind,
                title=title,
                objective=objective,
                approval=approval,
                depends_on=previous,
                inputs={
                    "opportunity_id": opportunity.opportunity_id,
                    "title": opportunity.title,
                    "issuer": opportunity.issuer,
                    "deadline": opportunity.deadline.isoformat() if opportunity.deadline else None,
                    "submission_path": opportunity.submission_path,
                },
                outputs=outputs,
            )
        )
    return tuple(steps)
