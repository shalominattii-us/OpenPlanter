import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from agent.opportunities import (
    DeterministicExecutionOrchestrator,
    ExecutionLifecycle,
    UniversalIntakeAdapter,
    build_mission_candidate,
)
from agent.opportunities.runtime import (
    ArtifactMaterializer,
    DeterministicExecutionService,
    EligibilityExecutorPlugin,
    ExecutionArtifactResult,
    PluginRegistry,
    PluginRuntime,
    ResearchExecutorPlugin,
)


NOW = datetime(2026, 7, 31, 21, 0, tzinfo=timezone.utc)


def build_context():
    adapter = UniversalIntakeAdapter(
        source_name="test-source",
        source_url="https://example.test/opportunities",
    )
    record = {
        "external_id": "materialization-1",
        "title": "Materialize executor output",
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
    lifecycle = ExecutionLifecycle.in_memory()
    return lifecycle, lifecycle.initialize(opportunity, packet, candidate, occurred_at=NOW)


def build_service(lifecycle, artifact_root):
    registry = PluginRegistry()
    registry.register(ResearchExecutorPlugin())
    registry.register(EligibilityExecutorPlugin())
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    return DeterministicExecutionService.create(
        orchestrator,
        PluginRuntime(registry),
        artifact_root=artifact_root,
    )


def test_materializer_writes_exact_bytes_and_checksum(tmp_path) -> None:
    artifact = ExecutionArtifactResult(
        name="result.json",
        uri="execution://logical/result.json",
        media_type="application/json",
        content='{"ok":true}\n',
    )

    materialized = ArtifactMaterializer(tmp_path).materialize("run-1", "step-1", artifact)
    path = Path(materialized.uri.removeprefix("file://"))

    assert path.read_bytes() == artifact.content_bytes
    assert materialized.checksum_sha256 == sha256(artifact.content_bytes).hexdigest()
    assert materialized.size_bytes == len(artifact.content_bytes)


def test_materializer_rejects_path_traversal(tmp_path) -> None:
    artifact = ExecutionArtifactResult(
        name="../escape.json",
        uri="execution://logical/escape.json",
        content="{}",
    )

    with pytest.raises(ValueError, match="safe file name"):
        ArtifactMaterializer(tmp_path).materialize("run-1", "step-1", artifact)


def test_execution_service_records_real_research_file(tmp_path) -> None:
    lifecycle, context = build_context()
    service = build_service(lifecycle, tmp_path / "artifacts")

    advanced = service.execute_next_step(context, actor="engine", occurred_at=NOW)

    assert len(advanced.artifacts) == 1
    recorded = advanced.artifacts[0]
    path = Path(recorded.uri.removeprefix("file://"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "validated-opportunity-brief-v1"
    assert recorded.checksum_sha256 == sha256(path.read_bytes()).hexdigest()
    assert recorded.metadata["materialized"] is True
    assert recorded.metadata["logical_uri"].startswith("execution://")


def test_research_and_eligibility_files_are_distinct_and_durable(tmp_path) -> None:
    lifecycle, context = build_context()
    service = build_service(lifecycle, tmp_path / "artifacts")

    after_research = service.execute_next_step(context, actor="engine", occurred_at=NOW)
    after_eligibility = service.execute_next_step(
        after_research,
        actor="engine",
        occurred_at=NOW,
    )

    assert len(after_eligibility.artifacts) == 2
    paths = [Path(item.uri.removeprefix("file://")) for item in after_eligibility.artifacts]
    assert all(path.exists() for path in paths)
    assert {path.name for path in paths} == {
        "validated-opportunity-brief.json",
        "eligibility-matrix.json",
    }
    eligibility = json.loads(
        next(path for path in paths if path.name == "eligibility-matrix.json").read_text()
    )
    assert eligibility["requires_operator_review"] is True
