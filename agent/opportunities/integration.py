from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence
import json

from .domain import EvidencePacket, MissionCandidate, Opportunity, QualificationStatus, to_primitive
from .graph import MissionGraph, build_mission_graph
from .lifecycle import ExecutionContext, ExecutionLifecycle
from .pipeline import QualificationPolicy, UniversalIntakeAdapter, build_mission_candidate


RUN_MANIFEST_SCHEMA_VERSION = "universal-opportunity-run-manifest-v1"
ENGINE_VERSION = "universal-opportunity-engine-v1"

Record = Mapping[str, Any]
ReportRenderer = Callable[[Sequence[Record]], str]


@dataclass(frozen=True)
class IntakeArtifactBundle:
    """Structured artifacts emitted for one normalized intake record."""

    opportunity: Opportunity
    evidence_packet: EvidencePacket
    mission_candidate: MissionCandidate
    mission_graph: MissionGraph
    execution_context: ExecutionContext | None = None

    def to_primitive(self) -> dict[str, Any]:
        payload = {
            "opportunity": to_primitive(self.opportunity),
            "evidence_packet": to_primitive(self.evidence_packet),
            "mission_candidate": to_primitive(self.mission_candidate),
            "mission_graph": self.mission_graph.to_primitive(),
        }
        if self.execution_context is not None:
            payload["execution_context"] = to_primitive(self.execution_context)
        return payload


@dataclass(frozen=True)
class DailyIntakeResult:
    """Result of one daily run while preserving the existing report payload."""

    report: str
    artifacts: tuple[IntakeArtifactBundle, ...]
    generated_at: datetime

    @property
    def execution_contexts(self) -> tuple[ExecutionContext, ...]:
        return tuple(
            bundle.execution_context
            for bundle in self.artifacts
            if bundle.execution_context is not None
        )


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
    """Persist immutable, independently addressable artifacts and a run manifest."""

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

        directories = {
            "opportunity": run_dir / "opportunities",
            "evidence_packet": run_dir / "evidence",
            "mission_candidate": run_dir / "missions",
            "mission_graph": run_dir / "graphs",
            "bundle": run_dir / "bundles",
        }
        for directory in directories.values():
            directory.mkdir()

        manifest_entries: list[dict[str, Any]] = []
        for bundle in artifacts:
            opportunity_file = f"{bundle.opportunity.opportunity_id}.json"
            evidence_file = f"{bundle.evidence_packet.evidence_packet_id}.json"
            candidate_file = f"{bundle.mission_candidate.mission_candidate_id}.json"
            graph_file = f"{bundle.mission_graph.graph_id}.json"
            bundle_file = f"{bundle.opportunity.opportunity_id}.json"

            payloads = {
                directories["opportunity"] / opportunity_file: to_primitive(bundle.opportunity),
                directories["evidence_packet"] / evidence_file: to_primitive(bundle.evidence_packet),
                directories["mission_candidate"] / candidate_file: to_primitive(bundle.mission_candidate),
                directories["mission_graph"] / graph_file: bundle.mission_graph.to_primitive(),
                directories["bundle"] / bundle_file: bundle.to_primitive(),
            }
            hashes: dict[str, str] = {}
            for path, payload in payloads.items():
                encoded = json.dumps(payload, indent=2, sort_keys=True)
                path.write_text(encoded, encoding="utf-8")
                hashes[str(path.relative_to(run_dir))] = sha256(encoded.encode("utf-8")).hexdigest()

            manifest_entry: dict[str, Any] = {
                "opportunity_id": bundle.opportunity.opportunity_id,
                "opportunity_version": bundle.opportunity.version,
                "evidence_packet_id": bundle.evidence_packet.evidence_packet_id,
                "evidence_packet_version": bundle.evidence_packet.version,
                "mission_candidate_id": bundle.mission_candidate.mission_candidate_id,
                "mission_graph_id": bundle.mission_graph.graph_id,
                "file": f"bundles/{bundle_file}",
                "files": {
                    "opportunity": f"opportunities/{opportunity_file}",
                    "evidence_packet": f"evidence/{evidence_file}",
                    "mission_candidate": f"missions/{candidate_file}",
                    "mission_graph": f"graphs/{graph_file}",
                    "bundle": f"bundles/{bundle_file}",
                },
                "sha256": hashes,
            }
            if bundle.execution_context is not None:
                manifest_entry.update(
                    {
                        "execution_plan_id": bundle.execution_context.execution_plan.execution_plan_id,
                        "execution_run_id": bundle.execution_context.execution_run.execution_run_id,
                    }
                )
            manifest_entries.append(manifest_entry)

        manifest = {
            "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "generated_at": generated_at.isoformat(),
            "artifact_count": len(artifacts),
            "execution_count": sum(
                bundle.execution_context is not None for bundle in artifacts
            ),
            "artifacts": manifest_entries,
        }
        manifest_text = json.dumps(manifest, indent=2, sort_keys=True)
        (run_dir / "manifest.json").write_text(manifest_text, encoding="utf-8")
        (run_dir / "run.json").write_text(manifest_text, encoding="utf-8")


@dataclass(frozen=True)
class UniversalDailyIntakeBridge:
    """Build canonical intake artifacts and initialize qualified execution lifecycles."""

    adapter: UniversalIntakeAdapter
    policy: QualificationPolicy = QualificationPolicy()
    sink: ArtifactSink | None = None
    lifecycle: ExecutionLifecycle = field(default_factory=ExecutionLifecycle.in_memory)

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
        mission_graph = build_mission_graph(
            opportunity,
            evidence_packet,
            mission_candidate,
        )
        execution_context = None
        if mission_candidate.decision.status != QualificationStatus.REJECTED:
            execution_context = self.lifecycle.initialize(
                opportunity,
                evidence_packet,
                mission_candidate,
                occurred_at=generated_at,
            )
        return IntakeArtifactBundle(
            opportunity=opportunity,
            evidence_packet=evidence_packet,
            mission_candidate=mission_candidate,
            mission_graph=mission_graph,
            execution_context=execution_context,
        )
