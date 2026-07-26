from __future__ import annotations

import json
from datetime import datetime, timezone

from agent.opportunities.runner import main, run_source
from agent.opportunities.sources import SourceMetadata


class FakeSource:
    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            source_name="Test Source",
            source_url="https://example.test/",
            adapter_version="1.0.0",
        )

    def fetch(self):
        return (
            {
                "id": "alpha",
                "title": "Alpha opportunity",
            },
        )

    def normalize(self, record):
        return {
            "external_id": record["id"],
            "title": record["title"],
            "source": "Test Source",
            "source_url": "https://example.test/alpha",
            "jurisdiction": "United States",
            "type": "Solicitation",
            "status": "open",
        }

    def validate(self, record):
        assert record["external_id"]


def test_run_source_writes_report_and_canonical_artifacts(tmp_path):
    seen = []

    def renderer(records):
        seen.extend(records)
        return "legacy-report\n"

    generated_at = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
    result = run_source(
        FakeSource(),
        output_root=tmp_path / "runs",
        report_path=tmp_path / "reports" / "daily.txt",
        render_report=renderer,
        generated_at=generated_at,
    )

    assert result.report == "legacy-report\n"
    assert [record["external_id"] for record in seen] == ["alpha"]
    assert (tmp_path / "reports" / "daily.txt").read_text() == "legacy-report\n"

    run_dirs = list((tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    manifest = json.loads((run_dirs[0] / "run.json").read_text())
    assert manifest["artifact_count"] == 1
    assert manifest["artifacts"][0]["opportunity_id"]
    assert (run_dirs[0] / manifest["artifacts"][0]["files"]["bundle"]).exists()


def test_main_requires_sam_api_key(monkeypatch):
    monkeypatch.delenv("SAM_GOV_API_KEY", raising=False)
    assert main([]) == 2
