from datetime import date, datetime, timedelta, timezone

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
from agent.opportunities.execution import ExecutionPolicy
from agent.opportunities.execution_record import (
    ExecutionEvent,
    ExecutionEventType,
    ExecutionOutcomeStatus,
    ExecutionRecorder,
    ExecutionRunStatus,
    InMemoryExecutionEventStore,
    derive_status,
)


NOW = datetime(2026, 7, 30, 18, 0, tzinfo=timezone.utc)


def build_plan(*, complete: bool = True):
    opportunity = Opportunity.create(
        title="Commercial execution engine pilot",
        source="test-source",
        jurisdiction="US",
        opportunity_type="partnership",
        status="open",
        provenance=ProvenanceRecord(
            source_name="test-source",
            source_url="https://example.test/opportunity/record-v1",
            source_record_id="record-v1",
            retrieved_at=NOW,
        ),
        issuer="Example Corporation",
        deadline=date(2026, 9, 30) if complete else None,
        eligibility=("Qualified supplier",) if complete else (),
        submission_path="https://example.test/submit" if complete else None,
        amount_max=500_000,
    )
    packet = EvidencePacket.create(
        opportunity=opportunity,
        assessments=(EvidenceAssessment("strategic_fit", 0.92, 0.9),),
        created_at=NOW,
    )
    candidate = MissionCandidate.create(
        opportunity=opportunity,
        evidence_packet=packet,
        decision=QualificationDecision(
            status=QualificationStatus.QUALIFIED,
            score=0.88,
            reasons=("fixture",),
            rule_version="test-v1",
        ),
        created_at=NOW,
    )
    return ExecutionPolicy().plan(opportunity, candidate, created_at=NOW)


def test_plan_creation_creates_run_and_initial_event() -> None:
    store = InMemoryExecutionEventStore()
    recorder = ExecutionRecorder(store)

    run = recorder.create_for_plan(build_plan(), occurred_at=NOW)

    assert run.status == ExecutionRunStatus.CREATED
    assert run.started_at is None
    timeline = recorder.timeline(run.execution_run_id)
    assert len(timeline) == 1
    assert timeline[0].event_type == ExecutionEventType.PLAN_CREATED
    assert timeline[0].sequence == 1
    assert timeline[0].details["step_count"] == 7


def test_blocked_plan_creates_blocked_run() -> None:
    recorder = ExecutionRecorder(InMemoryExecutionEventStore())

    run = recorder.create_for_plan(build_plan(complete=False), occurred_at=NOW)

    assert run.status == ExecutionRunStatus.BLOCKED
    with pytest.raises(ValueError, match="blocked"):
        recorder.start_run(run.execution_run_id, actor="operator", occurred_at=NOW)


def test_events_are_append_only_and_strictly_ordered() -> None:
    store = InMemoryExecutionEventStore()
    recorder = ExecutionRecorder(store)
    run = recorder.create_for_plan(build_plan(), occurred_at=NOW)
    recorder.start_run(run.execution_run_id, actor="operator", occurred_at=NOW + timedelta(seconds=1))

    recorder.append_event(
        run.execution_run_id,
        ExecutionEventType.STEP_STARTED,
        actor="research-agent",
        occurred_at=NOW + timedelta(seconds=2),
        step_id="step-1",
    )

    assert [event.sequence for event in recorder.timeline(run.execution_run_id)] == [1, 2, 3]
    with pytest.raises(ValueError, match="event sequence"):
        store.append_event(
            ExecutionEvent(
                event_id="bad-sequence",
                execution_run_id=run.execution_run_id,
                sequence=5,
                event_type=ExecutionEventType.STEP_COMPLETED,
                occurred_at=NOW + timedelta(seconds=3),
                actor="research-agent",
            )
        )


def test_artifact_recording_appends_audit_event() -> None:
    store = InMemoryExecutionEventStore()
    recorder = ExecutionRecorder(store)
    run = recorder.create_for_plan(build_plan(), occurred_at=NOW)

    artifact = recorder.record_artifact(
        run.execution_run_id,
        name="validated-opportunity-brief.json",
        uri="s3://execution-records/run/brief.json",
        media_type="application/json",
        actor="research-agent",
        created_at=NOW + timedelta(seconds=1),
        checksum_sha256="abc123",
        step_id="step-1",
    )

    assert store.artifacts_for_run(run.execution_run_id) == (artifact,)
    assert recorder.timeline(run.execution_run_id)[-1].event_type == ExecutionEventType.ARTIFACT_RECORDED


def test_outcome_is_recorded_once_with_business_value() -> None:
    store = InMemoryExecutionEventStore()
    recorder = ExecutionRecorder(store)
    run = recorder.create_for_plan(build_plan(), occurred_at=NOW)

    outcome = recorder.record_outcome(
        run.execution_run_id,
        status=ExecutionOutcomeStatus.WON,
        summary="Pilot engagement awarded.",
        actor="operator",
        recorded_at=NOW + timedelta(days=1),
        value=125_000,
        currency="usd",
        metrics={"days_to_decision": 1.0},
        lessons=("Early eligibility validation reduced review time.",),
    )

    assert outcome.currency == "USD"
    assert store.outcome_for_run(run.execution_run_id) == outcome
    assert recorder.timeline(run.execution_run_id)[-1].event_type == ExecutionEventType.OUTCOME_RECORDED
    with pytest.raises(ValueError, match="already been recorded"):
        recorder.record_outcome(
            run.execution_run_id,
            status=ExecutionOutcomeStatus.CLOSED,
            summary="Duplicate outcome.",
            actor="operator",
            recorded_at=NOW + timedelta(days=2),
        )


def test_replay_derives_current_status_from_event_history() -> None:
    store = InMemoryExecutionEventStore()
    recorder = ExecutionRecorder(store)
    run = recorder.create_for_plan(build_plan(), occurred_at=NOW)
    recorder.start_run(run.execution_run_id, actor="operator", occurred_at=NOW + timedelta(seconds=1))
    recorder.append_event(
        run.execution_run_id,
        ExecutionEventType.APPROVAL_REQUESTED,
        actor="orchestrator",
        occurred_at=NOW + timedelta(seconds=2),
    )

    assert derive_status(recorder.timeline(run.execution_run_id)) == ExecutionRunStatus.AWAITING_APPROVAL

    recorder.append_event(
        run.execution_run_id,
        ExecutionEventType.APPROVED,
        actor="operator",
        occurred_at=NOW + timedelta(seconds=3),
    )
    recorder.complete_run(
        run.execution_run_id,
        actor="orchestrator",
        occurred_at=NOW + timedelta(seconds=4),
    )

    assert derive_status(recorder.timeline(run.execution_run_id)) == ExecutionRunStatus.COMPLETED
    assert store.get_run(run.execution_run_id).status == ExecutionRunStatus.COMPLETED
