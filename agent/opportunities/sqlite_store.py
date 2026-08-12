from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any, Mapping

from .execution_record import (
    ExecutionArtifact,
    ExecutionEvent,
    ExecutionEventType,
    ExecutionOutcome,
    ExecutionOutcomeStatus,
    ExecutionRun,
    ExecutionRunStatus,
)


class SQLiteExecutionEventStore:
    """Durable SQLite implementation of the execution event-store contract.

    The store persists runs, append-only events, artifacts, and outcomes. It uses
    only Python's standard library and can be reopened by a later process to
    resume an execution from the same authoritative history.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS execution_runs (
                    execution_run_id TEXT PRIMARY KEY,
                    execution_plan_id TEXT NOT NULL,
                    mission_candidate_id TEXT NOT NULL,
                    opportunity_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    schema_version TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS execution_events (
                    event_id TEXT PRIMARY KEY,
                    execution_run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    step_id TEXT,
                    details_json TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    UNIQUE (execution_run_id, sequence),
                    FOREIGN KEY (execution_run_id)
                        REFERENCES execution_runs(execution_run_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS execution_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    execution_run_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    uri TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    checksum_sha256 TEXT,
                    step_id TEXT,
                    metadata_json TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    FOREIGN KEY (execution_run_id)
                        REFERENCES execution_runs(execution_run_id)
                        ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS execution_outcomes (
                    outcome_id TEXT PRIMARY KEY,
                    execution_run_id TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    value REAL,
                    currency TEXT,
                    metrics_json TEXT NOT NULL,
                    lessons_json TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    FOREIGN KEY (execution_run_id)
                        REFERENCES execution_runs(execution_run_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_execution_events_run
                    ON execution_events(execution_run_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_execution_artifacts_run
                    ON execution_artifacts(execution_run_id, created_at);
                """
            )

    def create_run(self, run: ExecutionRun) -> None:
        try:
            with self._lock, self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO execution_runs (
                        execution_run_id, execution_plan_id,
                        mission_candidate_id, opportunity_id, status,
                        created_at, started_at, completed_at, schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run.execution_run_id,
                        run.execution_plan_id,
                        run.mission_candidate_id,
                        run.opportunity_id,
                        run.status.value,
                        run.created_at.isoformat(),
                        _iso(run.started_at),
                        _iso(run.completed_at),
                        run.schema_version,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"execution run already exists: {run.execution_run_id}") from exc

    def get_run(self, execution_run_id: str) -> ExecutionRun:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM execution_runs WHERE execution_run_id = ?",
                (execution_run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown execution run: {execution_run_id}")
        return _run_from_row(row)

    def update_run(self, run: ExecutionRun) -> None:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE execution_runs
                SET execution_plan_id = ?, mission_candidate_id = ?,
                    opportunity_id = ?, status = ?, created_at = ?,
                    started_at = ?, completed_at = ?, schema_version = ?
                WHERE execution_run_id = ?
                """,
                (
                    run.execution_plan_id,
                    run.mission_candidate_id,
                    run.opportunity_id,
                    run.status.value,
                    run.created_at.isoformat(),
                    _iso(run.started_at),
                    _iso(run.completed_at),
                    run.schema_version,
                    run.execution_run_id,
                ),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"unknown execution run: {run.execution_run_id}")

    def append_event(self, event: ExecutionEvent) -> None:
        try:
            with self._lock, self._connect() as connection:
                run_exists = connection.execute(
                    "SELECT 1 FROM execution_runs WHERE execution_run_id = ?",
                    (event.execution_run_id,),
                ).fetchone()
                if run_exists is None:
                    raise KeyError(f"unknown execution run: {event.execution_run_id}")
                expected = connection.execute(
                    "SELECT COUNT(*) + 1 FROM execution_events WHERE execution_run_id = ?",
                    (event.execution_run_id,),
                ).fetchone()[0]
                if event.sequence != expected:
                    raise ValueError(
                        f"event sequence must be {expected} for run {event.execution_run_id}"
                    )
                connection.execute(
                    """
                    INSERT INTO execution_events (
                        event_id, execution_run_id, sequence, event_type,
                        occurred_at, actor, step_id, details_json, schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.execution_run_id,
                        event.sequence,
                        event.event_type.value,
                        event.occurred_at.isoformat(),
                        event.actor,
                        event.step_id,
                        _json(event.details),
                        event.schema_version,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"event already exists or sequence conflicts: {event.event_id}") from exc

    def events_for_run(self, execution_run_id: str) -> tuple[ExecutionEvent, ...]:
        self.get_run(execution_run_id)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM execution_events
                WHERE execution_run_id = ? ORDER BY sequence
                """,
                (execution_run_id,),
            ).fetchall()
        return tuple(_event_from_row(row) for row in rows)

    def record_artifact(self, artifact: ExecutionArtifact) -> None:
        try:
            with self._lock, self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO execution_artifacts (
                        artifact_id, execution_run_id, name, uri, media_type,
                        created_at, checksum_sha256, step_id, metadata_json,
                        schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact.artifact_id,
                        artifact.execution_run_id,
                        artifact.name,
                        artifact.uri,
                        artifact.media_type,
                        artifact.created_at.isoformat(),
                        artifact.checksum_sha256,
                        artifact.step_id,
                        _json(artifact.metadata),
                        artifact.schema_version,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if not self._run_exists(artifact.execution_run_id):
                raise KeyError(f"unknown execution run: {artifact.execution_run_id}") from exc
            raise ValueError(f"artifact already exists: {artifact.artifact_id}") from exc

    def artifacts_for_run(self, execution_run_id: str) -> tuple[ExecutionArtifact, ...]:
        self.get_run(execution_run_id)
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM execution_artifacts
                WHERE execution_run_id = ? ORDER BY created_at, artifact_id
                """,
                (execution_run_id,),
            ).fetchall()
        return tuple(_artifact_from_row(row) for row in rows)

    def record_outcome(self, outcome: ExecutionOutcome) -> None:
        try:
            with self._lock, self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO execution_outcomes (
                        outcome_id, execution_run_id, status, recorded_at,
                        summary, value, currency, metrics_json, lessons_json,
                        schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        outcome.outcome_id,
                        outcome.execution_run_id,
                        outcome.status.value,
                        outcome.recorded_at.isoformat(),
                        outcome.summary,
                        outcome.value,
                        outcome.currency,
                        _json(outcome.metrics),
                        _json(outcome.lessons),
                        outcome.schema_version,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if not self._run_exists(outcome.execution_run_id):
                raise KeyError(f"unknown execution run: {outcome.execution_run_id}") from exc
            raise ValueError("an execution outcome has already been recorded") from exc

    def outcome_for_run(self, execution_run_id: str) -> ExecutionOutcome | None:
        self.get_run(execution_run_id)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM execution_outcomes WHERE execution_run_id = ?",
                (execution_run_id,),
            ).fetchone()
        return None if row is None else _outcome_from_row(row)

    def _run_exists(self, execution_run_id: str) -> bool:
        with self._lock, self._connect() as connection:
            return connection.execute(
                "SELECT 1 FROM execution_runs WHERE execution_run_id = ?",
                (execution_run_id,),
            ).fetchone() is not None


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def _mapping(value: str) -> Mapping[str, Any]:
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise ValueError("stored JSON value is not an object")
    return decoded


def _iso(value: Any) -> str | None:
    return None if value is None else value.isoformat()


def _run_from_row(row: sqlite3.Row) -> ExecutionRun:
    return ExecutionRun(
        execution_run_id=row["execution_run_id"],
        execution_plan_id=row["execution_plan_id"],
        mission_candidate_id=row["mission_candidate_id"],
        opportunity_id=row["opportunity_id"],
        status=ExecutionRunStatus(row["status"]),
        created_at=_datetime(row["created_at"]),
        started_at=_optional_datetime(row["started_at"]),
        completed_at=_optional_datetime(row["completed_at"]),
        schema_version=row["schema_version"],
    )


def _event_from_row(row: sqlite3.Row) -> ExecutionEvent:
    return ExecutionEvent(
        event_id=row["event_id"],
        execution_run_id=row["execution_run_id"],
        sequence=row["sequence"],
        event_type=ExecutionEventType(row["event_type"]),
        occurred_at=_datetime(row["occurred_at"]),
        actor=row["actor"],
        step_id=row["step_id"],
        details=_mapping(row["details_json"]),
        schema_version=row["schema_version"],
    )


def _artifact_from_row(row: sqlite3.Row) -> ExecutionArtifact:
    return ExecutionArtifact(
        artifact_id=row["artifact_id"],
        execution_run_id=row["execution_run_id"],
        name=row["name"],
        uri=row["uri"],
        media_type=row["media_type"],
        created_at=_datetime(row["created_at"]),
        checksum_sha256=row["checksum_sha256"],
        step_id=row["step_id"],
        metadata=_mapping(row["metadata_json"]),
        schema_version=row["schema_version"],
    )


def _outcome_from_row(row: sqlite3.Row) -> ExecutionOutcome:
    lessons = json.loads(row["lessons_json"])
    return ExecutionOutcome(
        outcome_id=row["outcome_id"],
        execution_run_id=row["execution_run_id"],
        status=ExecutionOutcomeStatus(row["status"]),
        recorded_at=_datetime(row["recorded_at"]),
        summary=row["summary"],
        value=row["value"],
        currency=row["currency"],
        metrics={key: float(value) for key, value in _mapping(row["metrics_json"]).items()},
        lessons=tuple(str(item) for item in lessons),
        schema_version=row["schema_version"],
    )


def _datetime(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value)


def _optional_datetime(value: str | None):
    return None if value is None else _datetime(value)
