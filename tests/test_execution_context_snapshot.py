import sqlite3
from datetime import datetime, timezone

import pytest

from agent.opportunities import (
    DeterministicExecutionOrchestrator,
    ExecutionLifecycle,
    ExecutionRecorder,
    SQLiteExecutionContextSnapshotStore,
    SQLiteExecutionEventStore,
    UniversalIntakeAdapter,
    build_mission_candidate,
)


NOW = datetime(2026, 7, 31, 20, 0, tzinfo=timezone.utc)


def build_context(database_path):
    adapter = UniversalIntakeAdapter(
        source_name="test-source",
        source_url="https://example.test/opportunities",
    )
    record = {
        "external_id": "snapshot-1",
        "title": "Validate restart-safe execution context",
        "source": "test-source",
        "jurisdiction": "US",
        "type": "partnership",
        "status": "open",
        "issuer": "Example Agency",
        "deadline": "2026-09-15",
        "eligibility": ["US small business"],
        "submission_path": "mailto:opportunities@example.test",
        "strategic_fit": "very high",
        "urgency": "high",
        "complexity": "low",
        "eligibility_fit": "very high",
        "amount_max": 500000,
    }
    opportunity = adapter.opportunity_from_record(record, retrieved_at=NOW)
    packet = adapter.evidence_from_record(opportunity, record, created_at=NOW)
    candidate = build_mission_candidate(opportunity, packet, created_at=NOW)
    event_store = SQLiteExecutionEventStore(database_path)
    lifecycle = ExecutionLifecycle(recorder=ExecutionRecorder(event_store))
    context = lifecycle.initialize(opportunity, packet, candidate, occurred_at=NOW)
    return lifecycle, context


def test_snapshot_rehydrates_complete_context_after_restart(tmp_path) -> None:
    database = tmp_path / "execution.sqlite3"
    lifecycle, context = build_context(database)
    snapshots = SQLiteExecutionContextSnapshotStore(database)
    snapshots.save(context)

    restarted_store = SQLiteExecutionEventStore(database)
    restarted_lifecycle = ExecutionLifecycle(recorder=ExecutionRecorder(restarted_store))
    restored = SQLiteExecutionContextSnapshotStore(database).load_context(
        context.execution_run.execution_run_id,
        restarted_lifecycle,
    )

    assert restored.opportunity == context.opportunity
    assert restored.evidence_packet == context.evidence_packet
    assert restored.mission_candidate == context.mission_candidate
    assert restored.execution_plan == context.execution_plan
    assert restored.execution_run == context.execution_run
    assert restored.events == context.events


def test_snapshot_remains_immutable_while_ledger_advances(tmp_path) -> None:
    database = tmp_path / "execution.sqlite3"
    lifecycle, context = build_context(database)
    snapshots = SQLiteExecutionContextSnapshotStore(database)
    original = snapshots.save(context)
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    advanced = orchestrator.start_run(context, actor="engine", occurred_at=NOW)

    restored = snapshots.load_context(
        context.execution_run.execution_run_id,
        lifecycle,
    )

    assert snapshots.get(context.execution_run.execution_run_id) == original
    assert restored.execution_run == advanced.execution_run
    assert restored.events == advanced.events


def test_snapshot_rejects_duplicate_for_same_run(tmp_path) -> None:
    database = tmp_path / "execution.sqlite3"
    _, context = build_context(database)
    snapshots = SQLiteExecutionContextSnapshotStore(database)
    snapshots.save(context)

    with pytest.raises(ValueError, match="already exists"):
        snapshots.save(context)


def test_snapshot_detects_payload_tampering(tmp_path) -> None:
    database = tmp_path / "execution.sqlite3"
    _, context = build_context(database)
    snapshots = SQLiteExecutionContextSnapshotStore(database)
    snapshots.save(context)

    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            UPDATE execution_context_snapshots
            SET payload_json = ?
            WHERE execution_run_id = ?
            """,
            ('{"tampered":true}', context.execution_run.execution_run_id),
        )

    with pytest.raises(ValueError, match="checksum mismatch"):
        snapshots.get(context.execution_run.execution_run_id)
