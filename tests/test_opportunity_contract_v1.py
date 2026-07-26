from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json

from agent.opportunities import (
    ENGINE_VERSION,
    MISSION_GRAPH_SCHEMA_VERSION,
    RUN_MANIFEST_SCHEMA_VERSION,
    JsonDirectoryArtifactSink,
    SourceMetadata,
    UniversalDailyIntakeBridge,
    UniversalIntakeAdapter,
    collect_normalized,
)


class ExampleSource:
    def metadata(self) -> SourceMetadata:
        return SourceMetadata("Example", "https://example.invalid", "1.0.0")

    def fetch(self):
        return ({"id": "one", "name": "First"}, {"id": "two", "name": "Second"})

    def normalize(self, record):
        return {
            "external_id": record["id"],
            "title": record["name"],
            "source": "Example",
            "jurisdiction": "Global",
            "type": "Program",
            "status": "open",
            "strategic_fit": "high",
            "urgency": "medium",
            "complexity": "low",
            "eligibility_fit": "high",
        }

    def validate(self, record):
        if not record.get("external_id") or not record.get("title"):
            raise ValueError("invalid normalized record")


def test_source_contract_collects_validated_normalized_records() -> None:
    records = collect_normalized(ExampleSource())

    assert [record["external_id"] for record in records] == ["one", "two"]
    assert ExampleSource().metadata().adapter_version == "1.0.0"


def test_bridge_builds_stable_replayable_graph() -> None:
    record = collect_normalized(ExampleSource())[0]
    generated_at = datetime(2026, 7, 26, 5, 30, tzinfo=timezone.utc)
    bridge = UniversalDailyIntakeBridge(
        UniversalIntakeAdapter("Example", "https://example.invalid")
    )

    first = bridge.run([record], render_report=lambda records: "same", generated_at=generated_at)
    second = bridge.run([record], render_report=lambda records: "same", generated_at=generated_at)

    first_graph = first.artifacts[0].mission_graph
    second_graph = second.artifacts[0].mission_graph
    assert first.report == second.report == "same"
    assert first_graph.graph_id == second_graph.graph_id
    assert first_graph.schema_version == MISSION_GRAPH_SCHEMA_VERSION
    assert first_graph.to_primitive() == second_graph.to_primitive()
    assert {node.kind for node in first_graph.nodes} == {
        "opportunity",
        "evidence_packet",
        "mission_candidate",
    }


def test_run_manifest_has_versions_hashes_and_no_orphans(tmp_path) -> None:
    records = collect_normalized(ExampleSource())
    generated_at = datetime(2026, 7, 26, 5, 31, tzinfo=timezone.utc)
    bridge = UniversalDailyIntakeBridge(
        UniversalIntakeAdapter("Example", "https://example.invalid"),
        sink=JsonDirectoryArtifactSink(tmp_path),
    )

    result = bridge.run(records, render_report=lambda records: "unchanged", generated_at=generated_at)
    run_dir = next(tmp_path.iterdir())
    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert result.report == "unchanged"
    assert manifest["schema_version"] == RUN_MANIFEST_SCHEMA_VERSION
    assert manifest["engine_version"] == ENGINE_VERSION
    assert manifest["artifact_count"] == len(records)

    for entry in manifest["artifacts"]:
        for relative_path in entry["files"].values():
            artifact_path = run_dir / relative_path
            assert artifact_path.exists()
            text = artifact_path.read_text(encoding="utf-8")
            assert entry["sha256"][relative_path] == sha256(text.encode("utf-8")).hexdigest()

        graph = json.loads((run_dir / entry["files"]["mission_graph"]).read_text(encoding="utf-8"))
        known_nodes = {node["node_id"] for node in graph["nodes"]}
        assert graph["root_opportunity_id"] in known_nodes
        assert all(
            edge["source_id"] in known_nodes and edge["target_id"] in known_nodes
            for edge in graph["edges"]
        )
