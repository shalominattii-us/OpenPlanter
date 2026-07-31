from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any, Mapping

from .domain import (
    EvidenceAssessment,
    EvidencePacket,
    MissionCandidate,
    Opportunity,
    ProvenanceRecord,
    QualificationDecision,
    QualificationStatus,
    to_primitive,
)
from .execution import (
    ApprovalRequirement,
    ExecutionPlan,
    ExecutionPlanStatus,
    ExecutionStep,
    ExecutionStepKind,
)
from .lifecycle import ExecutionContext, ExecutionLifecycle


EXECUTION_CONTEXT_SNAPSHOT_SCHEMA_VERSION = "universal-execution-context-snapshot-v1"


@dataclass(frozen=True)
class ExecutionContextSnapshot:
    execution_run_id: str
    payload: Mapping[str, Any]
    checksum_sha256: str
    schema_version: str = EXECUTION_CONTEXT_SNAPSHOT_SCHEMA_VERSION


class SQLiteExecutionContextSnapshotStore:
    """Persist immutable planning snapshots used to rehydrate execution contexts."""

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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_context_snapshots (
                    execution_run_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    checksum_sha256 TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    FOREIGN KEY (execution_run_id)
                        REFERENCES execution_runs(execution_run_id)
                        ON DELETE CASCADE
                )
                """
            )

    def save(self, context: ExecutionContext) -> ExecutionContextSnapshot:
        payload = {
            "opportunity": to_primitive(context.opportunity),
            "evidence_packet": to_primitive(context.evidence_packet),
            "mission_candidate": to_primitive(context.mission_candidate),
            "execution_plan": to_primitive(context.execution_plan),
        }
        encoded = _canonical_json(payload)
        checksum = sha256(encoded.encode("utf-8")).hexdigest()
        snapshot = ExecutionContextSnapshot(
            execution_run_id=context.execution_run.execution_run_id,
            payload=payload,
            checksum_sha256=checksum,
        )
        try:
            with self._lock, self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO execution_context_snapshots (
                        execution_run_id, payload_json, checksum_sha256, schema_version
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        snapshot.execution_run_id,
                        encoded,
                        snapshot.checksum_sha256,
                        snapshot.schema_version,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"execution context snapshot already exists or run is unknown: "
                f"{snapshot.execution_run_id}"
            ) from exc
        return snapshot

    def get(self, execution_run_id: str) -> ExecutionContextSnapshot:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM execution_context_snapshots WHERE execution_run_id = ?",
                (execution_run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"unknown execution context snapshot: {execution_run_id}")
        payload = json.loads(row["payload_json"])
        if not isinstance(payload, dict):
            raise ValueError("stored execution context snapshot is not an object")
        checksum = sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
        if checksum != row["checksum_sha256"]:
            raise ValueError("execution context snapshot checksum mismatch")
        return ExecutionContextSnapshot(
            execution_run_id=execution_run_id,
            payload=payload,
            checksum_sha256=checksum,
            schema_version=row["schema_version"],
        )

    def load_context(
        self,
        execution_run_id: str,
        lifecycle: ExecutionLifecycle,
    ) -> ExecutionContext:
        snapshot = self.get(execution_run_id)
        payload = snapshot.payload
        context = ExecutionContext(
            opportunity=_opportunity(payload["opportunity"]),
            evidence_packet=_evidence_packet(payload["evidence_packet"]),
            mission_candidate=_mission_candidate(payload["mission_candidate"]),
            execution_plan=_execution_plan(payload["execution_plan"]),
            execution_run=lifecycle.store.get_run(execution_run_id),
            events=lifecycle.recorder.timeline(execution_run_id),
            artifacts=lifecycle.store.artifacts_for_run(execution_run_id),
        )
        return lifecycle.refresh(context)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _provenance(value: Mapping[str, Any]) -> ProvenanceRecord:
    return ProvenanceRecord(
        source_name=str(value["source_name"]),
        source_url=str(value["source_url"]),
        retrieved_at=datetime.fromisoformat(str(value["retrieved_at"])),
        source_record_id=value.get("source_record_id"),
        content_hash=value.get("content_hash"),
    )


def _opportunity(value: Mapping[str, Any]) -> Opportunity:
    return Opportunity(
        opportunity_id=str(value["opportunity_id"]),
        title=str(value["title"]),
        source=str(value["source"]),
        jurisdiction=str(value["jurisdiction"]),
        opportunity_type=str(value["opportunity_type"]),
        status=str(value["status"]),
        version=int(value["version"]),
        provenance=_provenance(value["provenance"]),
        issuer=value.get("issuer"),
        external_id=value.get("external_id"),
        published_date=_optional_date(value.get("published_date")),
        deadline=_optional_date(value.get("deadline")),
        eligibility=tuple(value.get("eligibility", ())),
        sectors=tuple(value.get("sectors", ())),
        amount_min=value.get("amount_min"),
        amount_max=value.get("amount_max"),
        currency=str(value.get("currency", "USD")),
        submission_path=value.get("submission_path"),
        attachments=tuple(value.get("attachments", ())),
        metadata=dict(value.get("metadata", {})),
    )


def _evidence_packet(value: Mapping[str, Any]) -> EvidencePacket:
    assessments = tuple(
        EvidenceAssessment(
            dimension=str(item["dimension"]),
            score=float(item["score"]),
            confidence=float(item["confidence"]),
            rationale=tuple(item.get("rationale", ())),
            facts=dict(item.get("facts", {})),
        )
        for item in value.get("assessments", ())
    )
    return EvidencePacket(
        evidence_packet_id=str(value["evidence_packet_id"]),
        opportunity_id=str(value["opportunity_id"]),
        opportunity_version=int(value["opportunity_version"]),
        version=int(value["version"]),
        created_at=datetime.fromisoformat(str(value["created_at"])),
        assessments=assessments,
        provenance=tuple(_provenance(item) for item in value.get("provenance", ())),
        recommendations=tuple(value.get("recommendations", ())),
    )


def _mission_candidate(value: Mapping[str, Any]) -> MissionCandidate:
    decision_value = value["decision"]
    return MissionCandidate(
        mission_candidate_id=str(value["mission_candidate_id"]),
        opportunity_id=str(value["opportunity_id"]),
        opportunity_version=int(value["opportunity_version"]),
        evidence_packet_id=str(value["evidence_packet_id"]),
        evidence_packet_version=int(value["evidence_packet_version"]),
        created_at=datetime.fromisoformat(str(value["created_at"])),
        decision=QualificationDecision(
            status=QualificationStatus(str(decision_value["status"])),
            score=float(decision_value["score"]),
            reasons=tuple(decision_value.get("reasons", ())),
            rule_version=str(decision_value["rule_version"]),
        ),
    )


def _execution_plan(value: Mapping[str, Any]) -> ExecutionPlan:
    steps = tuple(
        ExecutionStep(
            step_id=str(item["step_id"]),
            sequence=int(item["sequence"]),
            kind=ExecutionStepKind(str(item["kind"])),
            title=str(item["title"]),
            objective=str(item["objective"]),
            approval=ApprovalRequirement(str(item["approval"])),
            depends_on=tuple(item.get("depends_on", ())),
            inputs=dict(item.get("inputs", {})),
            outputs=tuple(item.get("outputs", ())),
        )
        for item in value.get("steps", ())
    )
    return ExecutionPlan(
        execution_plan_id=str(value["execution_plan_id"]),
        mission_candidate_id=str(value["mission_candidate_id"]),
        opportunity_id=str(value["opportunity_id"]),
        opportunity_version=int(value["opportunity_version"]),
        status=ExecutionPlanStatus(str(value["status"])),
        created_at=datetime.fromisoformat(str(value["created_at"])),
        steps=steps,
        blockers=tuple(value.get("blockers", ())),
        assumptions=tuple(value.get("assumptions", ())),
        schema_version=str(value.get("schema_version", "universal-opportunity-execution-plan-v1")),
    )


def _optional_date(value: Any) -> date | None:
    return None if value in (None, "") else date.fromisoformat(str(value))
