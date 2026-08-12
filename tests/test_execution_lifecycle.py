from datetime import date, datetime, timezone

import pytest

from agent.opportunities.domain import (
    EvidenceAssessment,
    EvidencePacket,
    MissionCandidate,
    Opportunity,
    ProvenanceRecord,
    QualificationDecision,
    QualificationStatus,
)
from agent.opportunities.execution_record import ExecutionEventType, ExecutionRunStatus
from agent.opportunities.integration import UniversalDailyIntakeBridge
from agent.opportunities.lifecycle import ExecutionLifecycle
from agent.opportunities.pipeline import QualificationPolicy, UniversalIntakeAdapter


NOW = datetime(2026, 7, 30, 22, 30, tzinfo=timezone.utc)


def build_domain_inputs(
    status: QualificationStatus = QualificationStatus.QUALIFIED,
) -> tuple[Opportunity, EvidencePacket, MissionCandidate]:
    opportunity = Opportunity.create(
        title="Deliver an execution-engine pilot",
        source="test",
        jurisdiction="US",
        opportunity_type="partnership",
        status="open",
        provenance=ProvenanceRecord(
            source_name="test",
            source_url="https://example.test/opportunity",
            source_record_id="execution-lifecycle-1",
            retrieved_at=NOW,
        ),
        issuer="Example Agency",
        deadline=date(2026, 9, 15),
        eligibility=("US business",),
        submission_path="mailto:pilot@example.test",
        amount_max=500_000,
    )
    packet = EvidencePacket.create(
        opportunity=opportunity,
        assessments=(
            EvidenceAssessment("strategic_fit", 0.95, 0.95),
            EvidenceAssessment("urgency", 0.80, 0.90),
        ),
        created_at=NOW,
    )
    candidate = MissionCandidate.create(
        opportunity=opportunity,
        evidence_packet=packet,
        decision=QualificationDecision(
            status=status,
            score=0.90 if status == QualificationStatus.QUALIFIED else 0.10,
            reasons=("fixture",),
            rule_version="test-v1",
        ),
        created_at=NOW,
    )
    return opportunity, packet, candidate


def test_initialize_returns_complete_execution_context() -> None:
    opportunity, packet, candidate = build_domain_inputs()
    lifecycle = ExecutionLifecycle.in_memory(actor="test-engine")

    context = lifecycle.initialize(
        opportunity,
        packet,
        candidate,
        occurred_at=NOW,
    )

    assert context.execution_plan.mission_candidate_id == candidate.mission_candidate_id
    assert context.execution_run.execution_plan_id == context.execution_plan.execution_plan_id
    assert context.execution_run.status == ExecutionRunStatus.CREATED
    assert len(context.events) == 1
    assert context.events[0].event_type == ExecutionEventType.PLAN_CREATED
    assert context.events[0].actor == "test-engine"


def test_rejected_candidate_does_not_initialize_execution() -> None:
    opportunity, packet, candidate = build_domain_inputs(QualificationStatus.REJECTED)

    with pytest.raises(ValueError, match="rejected"):
        ExecutionLifecycle.in_memory().initialize(
            opportunity,
            packet,
            candidate,
            occurred_at=NOW,
        )


def test_refresh_returns_latest_run_and_events() -> None:
    opportunity, packet, candidate = build_domain_inputs()
    lifecycle = ExecutionLifecycle.in_memory()
    context = lifecycle.initialize(opportunity, packet, candidate, occurred_at=NOW)

    lifecycle.recorder.start_run(
        context.execution_run.execution_run_id,
        actor="operator",
        occurred_at=NOW,
    )
    refreshed = lifecycle.refresh(context)

    assert refreshed.execution_run.status == ExecutionRunStatus.RUNNING
    assert [event.event_type for event in refreshed.events] == [
        ExecutionEventType.PLAN_CREATED,
        ExecutionEventType.RUN_STARTED,
    ]


def test_daily_intake_initializes_execution_for_qualified_record() -> None:
    bridge = UniversalDailyIntakeBridge(
        adapter=UniversalIntakeAdapter(
            source_name="test-source",
            source_url="https://example.test/feed",
        ),
        policy=QualificationPolicy(qualify_threshold=0.50),
    )
    record = {
        "external_id": "daily-qualified-1",
        "title": "High-value execution opportunity",
        "jurisdiction": "US",
        "type": "procurement",
        "status": "open",
        "issuer": "Example Agency",
        "deadline": "2026-09-15",
        "eligibility": ["US business"],
        "submission_path": "https://example.test/submit",
        "strategic_fit": "very high",
        "urgency": "high",
        "complexity": "low",
        "eligibility_fit": "high",
        "amount_max": 750_000,
    }

    result = bridge.run(
        [record],
        render_report=lambda records: f"records={len(records)}",
        generated_at=NOW,
    )

    assert result.report == "records=1"
    assert len(result.execution_contexts) == 1
    context = result.execution_contexts[0]
    assert context.events[0].event_type == ExecutionEventType.PLAN_CREATED
    assert result.artifacts[0].execution_context is context


def test_daily_intake_skips_execution_for_rejected_record() -> None:
    bridge = UniversalDailyIntakeBridge(
        adapter=UniversalIntakeAdapter(
            source_name="test-source",
            source_url="https://example.test/feed",
        ),
        policy=QualificationPolicy(review_threshold=0.90, qualify_threshold=0.95),
    )
    record = {
        "external_id": "daily-rejected-1",
        "title": "Low-fit opportunity",
        "jurisdiction": "US",
        "type": "grant",
        "status": "open",
        "strategic_fit": "very low",
        "urgency": "low",
        "complexity": "very high",
        "eligibility_fit": "low",
        "amount_max": 1_000,
    }

    result = bridge.run(
        [record],
        render_report=lambda records: "ok",
        generated_at=NOW,
    )

    assert result.execution_contexts == ()
    assert result.artifacts[0].execution_context is None
    assert result.artifacts[0].mission_candidate.decision.status == QualificationStatus.REJECTED
