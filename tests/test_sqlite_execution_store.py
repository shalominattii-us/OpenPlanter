from datetime import datetime, timezone

import pytest

from agent.opportunities import (
    ExecutionArtifact,
    ExecutionEvent,
    ExecutionEventType,
    ExecutionOutcome,
    ExecutionOutcomeStatus,
    ExecutionRun,
    ExecutionRunStatus,
    SQLiteExecutionEventStore,
)


NOW = datetime(2026, 7, 31, 20, 0, tzinfo=timezone.utc)


def run() -> ExecutionRun:
    return ExecutionRun(
        execution_run_id="run-1",
        execution_plan_id="plan-1",
        mission_candidate_id="mission-1",
        opportunity_id="opportunity-1",
        status=ExecutionRunStatus.RUNNING,
        created_at=NOW,
        started_at=NOW,
    )


def test_store_reopens_with_run_and_append_only_events(tmp_path) -> None:
    path = tmp_path / "execution.db"
    store = SQLiteExecutionEventStore(path)
    store.create_run(run())
    store.append_event(
        ExecutionEvent(
            event_id="event-1",
            execution_run_id="run-1",
            sequence=1,
            event_type=ExecutionEventType.RUN_STARTED,
            occurred_at=NOW,
            actor="engine",
            details={"nested": {"value": 7}},
        )
    )

    reopened = SQLiteExecutionEventStore(path)

    assert reopened.get_run("run-1") == run()
    assert reopened.events_for_run("run-1")[0].details == {"nested": {"value": 7}}


def test_store_persists_artifacts_and_outcome_across_restart(tmp_path) -> None:
    path = tmp_path / "execution.db"
    store = SQLiteExecutionEventStore(path)
    store.create_run(run())
    artifact = ExecutionArtifact(
        artifact_id="artifact-1",
        execution_run_id="run-1",
        name="brief.json",
        uri="execution://run-1/brief.json",
        media_type="application/json",
        created_at=NOW,
        step_id="step-1",
        metadata={"plugin_id": "research"},
    )
    outcome = ExecutionOutcome(
        outcome_id="outcome-1",
        execution_run_id="run-1",
        status=ExecutionOutcomeStatus.DELIVERED,
        recorded_at=NOW,
        summary="Delivered successfully.",
        value=1250.0,
        currency="USD",
        metrics={"quality": 0.95},
        lessons=("Preserve evidence lineage.",),
    )
    store.record_artifact(artifact)
    store.record_outcome(outcome)

    reopened = SQLiteExecutionEventStore(path)

    assert reopened.artifacts_for_run("run-1") == (artifact,)
    assert reopened.outcome_for_run("run-1") == outcome


def test_store_enforces_event_sequence_and_unique_artifacts(tmp_path) -> None:
    store = SQLiteExecutionEventStore(tmp_path / "execution.db")
    store.create_run(run())
    invalid = ExecutionEvent(
        event_id="event-2",
        execution_run_id="run-1",
        sequence=2,
        event_type=ExecutionEventType.STEP_STARTED,
        occurred_at=NOW,
        actor="engine",
        step_id="step-1",
    )

    with pytest.raises(ValueError, match="event sequence must be 1"):
        store.append_event(invalid)

    artifact = ExecutionArtifact(
        artifact_id="artifact-1",
        execution_run_id="run-1",
        name="brief.json",
        uri="execution://run-1/brief.json",
        media_type="application/json",
        created_at=NOW,
    )
    store.record_artifact(artifact)
    with pytest.raises(ValueError, match="artifact already exists"):
        store.record_artifact(artifact)


def test_store_updates_run_and_rejects_unknown_records(tmp_path) -> None:
    path = tmp_path / "execution.db"
    store = SQLiteExecutionEventStore(path)
    original = run()
    store.create_run(original)
    completed = ExecutionRun(
        execution_run_id=original.execution_run_id,
        execution_plan_id=original.execution_plan_id,
        mission_candidate_id=original.mission_candidate_id,
        opportunity_id=original.opportunity_id,
        status=ExecutionRunStatus.COMPLETED,
        created_at=original.created_at,
        started_at=original.started_at,
        completed_at=NOW,
    )
    store.update_run(completed)

    assert SQLiteExecutionEventStore(path).get_run("run-1") == completed
    with pytest.raises(KeyError, match="unknown execution run"):
        store.get_run("missing")
