from datetime import date, datetime, timezone

import pytest

from agent.opportunities.domain import (
    EvidenceAssessment,
    EvidencePacket,
    Opportunity,
    ProvenanceRecord,
    QualificationDecision,
    QualificationStatus,
    MissionCandidate,
)
from agent.opportunities.execution import (
    ApprovalRequirement,
    ExecutionPlanStatus,
    ExecutionPolicy,
    ExecutionStepKind,
)


NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


def build_opportunity(*, complete: bool = True) -> Opportunity:
    return Opportunity.create(
        title="Build a public-sector opportunity intelligence pilot",
        source="chatgpt-task",
        jurisdiction="US",
        opportunity_type="partnership",
        status="open",
        provenance=ProvenanceRecord(
            source_name="chatgpt-task",
            source_url="https://example.test/opportunities/1",
            source_record_id="daily-1",
            retrieved_at=NOW,
        ),
        issuer="Example Agency",
        deadline=date(2026, 9, 15) if complete else None,
        eligibility=("US small business",) if complete else (),
        submission_path="mailto:opportunities@example.test" if complete else None,
        amount_max=250_000,
    )


def build_candidate(
    opportunity: Opportunity,
    status: QualificationStatus = QualificationStatus.QUALIFIED,
) -> MissionCandidate:
    packet = EvidencePacket.create(
        opportunity=opportunity,
        assessments=(
            EvidenceAssessment("strategic_fit", 0.9, 0.9),
            EvidenceAssessment("urgency", 0.7, 0.8),
        ),
        created_at=NOW,
    )
    return MissionCandidate.create(
        opportunity=opportunity,
        evidence_packet=packet,
        decision=QualificationDecision(
            status=status,
            score=0.82 if status == QualificationStatus.QUALIFIED else 0.2,
            reasons=("fixture",),
            rule_version="test-v1",
        ),
        created_at=NOW,
    )


def test_qualified_opportunity_produces_review_gated_plan() -> None:
    opportunity = build_opportunity()
    candidate = build_candidate(opportunity)

    plan = ExecutionPolicy().plan(opportunity, candidate, created_at=NOW)

    assert plan.status == ExecutionPlanStatus.READY_FOR_REVIEW
    assert len(plan.steps) == 7
    assert [step.sequence for step in plan.steps] == list(range(1, 8))
    assert plan.steps[0].kind == ExecutionStepKind.RESEARCH
    assert plan.steps[-1].kind == ExecutionStepKind.TRACK_OUTCOME
    assert plan.requires_explicit_approval is True

    submission = next(
        step for step in plan.steps if step.kind == ExecutionStepKind.SUBMIT_RESPONSE
    )
    assert submission.approval == ApprovalRequirement.EXPLICIT_APPROVAL
    assert submission.depends_on


def test_missing_execution_facts_block_plan_without_removing_steps() -> None:
    opportunity = build_opportunity(complete=False)
    candidate = build_candidate(opportunity)

    plan = ExecutionPolicy().plan(opportunity, candidate, created_at=NOW)

    assert plan.status == ExecutionPlanStatus.BLOCKED
    assert set(plan.blockers) == {
        "submission deadline is unknown",
        "submission or contact path is unknown",
        "eligibility requirements are not recorded",
    }
    assert len(plan.steps) == 7


def test_rejected_candidate_is_not_actionable() -> None:
    opportunity = build_opportunity()
    candidate = build_candidate(opportunity, QualificationStatus.REJECTED)

    plan = ExecutionPolicy().plan(opportunity, candidate, created_at=NOW)

    assert plan.status == ExecutionPlanStatus.NOT_ACTIONABLE
    assert plan.steps == ()
    assert plan.blockers == ("qualification decision rejected the opportunity",)


def test_plan_is_deterministic_for_same_candidate_and_policy() -> None:
    opportunity = build_opportunity()
    candidate = build_candidate(opportunity)
    policy = ExecutionPolicy()

    first = policy.plan(opportunity, candidate, created_at=NOW)
    second = policy.plan(opportunity, candidate, created_at=NOW)

    assert first.execution_plan_id == second.execution_plan_id
    assert [step.step_id for step in first.steps] == [step.step_id for step in second.steps]


def test_candidate_must_match_opportunity() -> None:
    opportunity = build_opportunity()
    other = Opportunity.create(
        title="Other",
        source="other",
        jurisdiction="US",
        opportunity_type="grant",
        status="open",
        provenance=ProvenanceRecord(
            source_name="other",
            source_url="https://example.test/other",
            retrieved_at=NOW,
        ),
    )
    candidate = build_candidate(other)

    with pytest.raises(ValueError, match="does not belong"):
        ExecutionPolicy().plan(opportunity, candidate, created_at=NOW)
