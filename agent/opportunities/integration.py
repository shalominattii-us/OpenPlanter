from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence
import json

from .domain import EvidencePacket, MissionCandidate, Opportunity, to_primitive
from .pipeline import QualificationPolicy, UniversalIntakeAdapter, build_mission_candidate


Record = Mapping[str, Any]
ReportRenderer = Callable[[Sequence[Record]], str]


@dataclass(frozen=True)
class IntakeArtifactBundle:
    """Structured artifacts emitted for one normalized intake record."""

    opportunity: Opportunity
    evidence_packet: EvidencePacket
    mission_candidate: MissionCandidate

    def to_primitive(self) -> dict[str, Any]:
        return {
            "opportunity": to_primitive(self.opportunity),
            "evidence_packet": to_primitive(self.evidence_packet),
            "mission_candidate": to_primitive(self.mission_candidate),
        }


@dataclass(frozen=True)
class DailyIntakeResult:
    """Result of one daily run while preserving the existing report payload."""

    report: str
    artifacts: tuple[IntakeArtifactBundle, ...]
    generated_at: datetime


class ArtifactSink(Protocol):
    """Persistence boundary for structured daily-intake artifacts."""

    def write_run(
        self,
        *,
        generated_at: datetime,
        artifacts: Sequence[IntakeArtifactBundle],
    ) -> None:
        ...


@dataclass(frozen=True)
class JsonDirectoryArtifactSink:
    """Persist one immutable JSON document per artifact bundle.

    Existing report generation does not depend on this sink. A persistence error
    is therefore visible to the caller instead of silently changing the report.
    """

    root: Path

    def write_run(
        self,
        *,
        generated_at: datetime,
        artifacts: Sequence[IntakeArtifactBundle],
    ) -> None:
        run_id = generated_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        run_dir = self.root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)

        manifest: list[dict[str, Any]] = []
        for bundle in artifacts:
            file_name = f"{bundle.opportunity.opportunity_id}.json"
            payload = bundle.to_primitive()
            (run_dir / file_name).write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            manifest.append(
                {
                    "opportunity_id": bundle.opportunity.opportunity_id,
                    "opportunity_version": bundle.opportunity.version,
                    "evidence_packet_id": bundle.evidence_packet.evidence_packet_id,
                    "mission_candidate_id": bundle.mission_candidate.mission_candidate_id,
                    "file": file_name,
                }
            )

        (run_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "generated_at": generated_at.isoformat(),
                    "artifact_count": len(artifacts),
                    "artifacts": manifest,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )


@dataclass(frozen=True)
class UniversalDailyIntakeBridge:
    """Add canonical artifacts without changing the current report renderer.

    The bridge passes the original normalized records to ``render_report`` in the
    original order. It constructs and optionally persists structured artifacts in
    parallel, allowing the daily report to remain byte-for-byte compatible while
    the new domain layer is introduced.
    """

    adapter: UniversalIntakeAdapter
    policy: QualificationPolicy = QualificationPolicy()
    sink: ArtifactSink | None = None

    def run(
        self,
        records: Iterable[Record],
        *,
        render_report: ReportRenderer,
        generated_at: datetime | None = None,
    ) -> DailyIntakeResult:
        run_time = generated_at or datetime.now(timezone.utc)
        if run_time.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")

        # Materialize exactly once so generators remain safe and the renderer sees
        # the same record objects and ordering supplied by the existing pipeline.
        normalized_records = tuple(records)
        artifacts = tuple(
            self._build_bundle(record, generated_at=run_time)
            for record in normalized_records
        )

        if self.sink is not None:
            self.sink.write_run(generated_at=run_time, artifacts=artifacts)

        report = render_report(normalized_records)
        return DailyIntakeResult(
            report=report,
            artifacts=artifacts,
            generated_at=run_time,
        )

    def _build_bundle(
        self,
        record: Record,
        *,
        generated_at: datetime,
    ) -> IntakeArtifactBundle:
        opportunity = self.adapter.opportunity_from_record(
            record,
            retrieved_at=generated_at,
        )
        evidence_packet = self.adapter.evidence_from_record(
            opportunity,
            record,
            created_at=generated_at,
        )
        mission_candidate = build_mission_candidate(
            opportunity,
            evidence_packet,
            policy=self.policy,
            created_at=generated_at,
        )
        return IntakeArtifactBundle(
            opportunity=opportunity,
            evidence_packet=evidence_packet,
            mission_candidate=mission_candidate,
        )
