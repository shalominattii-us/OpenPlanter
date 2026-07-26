from __future__ import annotations

from datetime import datetime, timezone
import json

from agent.opportunities import (
    JsonDirectoryArtifactSink,
    QualificationStatus,
    UniversalDailyIntakeBridge,
    UniversalIntakeAdapter,
)


def _record() -> dict[str, object]:
    return {
        "external_id": "363209",
        "title": "Transnational repression research and mitigation",
        "source": "Grants.gov",
        "source_url": "https://www.grants.gov/example/363209",
        "issuer": "U.S. Department of State",
        "jurisdiction": "United States",
        "type": "Notice of Funding Opportunity",
        "status": "open",
        "deadline": "2026-08-10",
        "amount_max": 986679,
        "strategic_fit": "high",
        "urgency": "high",
        "complexity": "high",
        "eligibility_fit": "high",
        "eligibility": ["companies", "nonprofits", "universities"],
        "recommendations": ["Review ethical and privacy controls"],
    }


def test_bridge_preserves_original_report_input_and_output() -> None:
    first = _record()
    second = {**_record(), "external_id": "361915", "title": "NSF infrastructure"}
    supplied = [first, second]
    observed: list[object] = []

    def renderer(records):
        observed.extend(records)
        return "EXISTING DAILY REPORT\n"

    bridge = UniversalDailyIntakeBridge(
        adapter=UniversalIntakeAdapter(
            source_name="Universal Opportunity Intake",
            source_url="https://example.invalid/intake",
        )
    )
    result = bridge.run(
        supplied,
        render_report=renderer,
        generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
    )

    assert result.report == "EXISTING DAILY REPORT\n"
    assert observed[0] is first
    assert observed[1] is second
    assert len(result.artifacts) == 2
    assert result.artifacts[0].opportunity.external_id == "363209"
    assert result.artifacts[0].mission_candidate.decision.status in {
        QualificationStatus.QUALIFIED,
        QualificationStatus.REVIEW,
    }


def test_bridge_accepts_generator_without_consuming_it_twice() -> None:
    bridge = UniversalDailyIntakeBridge(
        adapter=UniversalIntakeAdapter("test", "https://example.invalid")
    )
    rendered_counts: list[int] = []

    def renderer(records):
        rendered_counts.append(len(records))
        return "ok"

    result = bridge.run(
        (_record() for _ in range(3)),
        render_report=renderer,
        generated_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
    )

    assert rendered_counts == [3]
    assert len(result.artifacts) == 3


def test_json_sink_writes_manifest_and_linked_artifacts(tmp_path) -> None:
    run_time = datetime(2026, 7, 26, 1, 2, 3, tzinfo=timezone.utc)
    bridge = UniversalDailyIntakeBridge(
        adapter=UniversalIntakeAdapter("test", "https://example.invalid"),
        sink=JsonDirectoryArtifactSink(tmp_path),
    )

    result = bridge.run([_record()], render_report=lambda records: "report", generated_at=run_time)

    run_dirs = list(tmp_path.iterdir())
    assert len(run_dirs) == 1
    manifest = json.loads((run_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifact_count"] == 1
    artifact_file = run_dirs[0] / manifest["artifacts"][0]["file"]
    payload = json.loads(artifact_file.read_text(encoding="utf-8"))
    bundle = result.artifacts[0]
    assert payload["opportunity"]["opportunity_id"] == bundle.opportunity.opportunity_id
    assert payload["evidence_packet"]["opportunity_id"] == bundle.opportunity.opportunity_id
    assert payload["mission_candidate"]["evidence_packet_id"] == bundle.evidence_packet.evidence_packet_id


def test_naive_generated_at_is_rejected() -> None:
    bridge = UniversalDailyIntakeBridge(
        adapter=UniversalIntakeAdapter("test", "https://example.invalid")
    )

    try:
        bridge.run([_record()], render_report=lambda records: "report", generated_at=datetime(2026, 7, 26))
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("expected ValueError")
