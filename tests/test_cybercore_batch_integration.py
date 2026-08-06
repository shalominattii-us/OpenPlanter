from __future__ import annotations

import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

from agent.opportunities.intelligence.cli import main
from agent.opportunities.intelligence.policy import sha256_json

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "cybercore" / "2026-08-06"
BATCH = FIXTURE / "AEGENTIX-CYBERCORE-OPP-INTAKE-2026-08-06.json"
EVIDENCE = FIXTURE / "source-verification-2026-08-06.json"
MANIFEST = ROOT / "manifests" / "cybercore-opportunity-intelligence.json"
EVALUATED_AT = "2026-08-06T17:32:17Z"
RUN_ID = "20260806T173217000000Z"


def test_real_cybercore_batch_runs_end_to_end_with_zero_actions(tmp_path, capsys) -> None:
    output_root = tmp_path / "runs"

    code = main(
        [
            "--batch",
            str(BATCH),
            "--evidence",
            str(EVIDENCE),
            "--output-root",
            str(output_root),
            "--evaluated-at",
            EVALUATED_AT,
        ]
    )

    assert code == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["ok"] is True
    assert summary["record_count"] == 22
    assert summary["intelligence_output_count"] == 22
    assert summary["execution_context_count"] == 5
    assert summary["verification"] == {
        "NEEDS_SOURCE_VERIFICATION": 9,
        "VERIFIED": 13,
    }
    assert summary["maturity"] == {
        "CLOSED": 7,
        "FORECAST_MONITOR": 1,
        "HUMAN_REVIEW": 5,
        "PROGRAM_DISCOVERY": 6,
        "SOURCE_DISCOVERY": 3,
    }
    assert summary["commercialization"] == {
        "CLOSED_NO_ACTION": 7,
        "MONITOR_FORECAST": 1,
        "PROGRAM_DISCOVERY_ONLY": 6,
        "READY_FOR_HUMAN_REVIEW": 5,
        "SOURCE_VERIFICATION_REQUIRED": 3,
    }
    assert summary["safety"] == {
        "authorization_policy": "human_required",
        "automatic_dispatches": 0,
        "external_actions_executed": 0,
        "treasury_labs_handoffs_executed": 0,
    }

    run_dir = output_root / RUN_ID
    run_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["schema_version"] == "universal-opportunity-run-manifest-v2"
    assert run_manifest["engine_version"] == "universal-opportunity-engine-v2"
    assert run_manifest["artifact_count"] == 22
    assert run_manifest["intelligence_count"] == 22
    assert run_manifest["execution_count"] == 5
    assert run_manifest["human_review_count"] == 5
    assert run_manifest["automatic_dispatches"] == 0
    assert run_manifest["external_actions_executed"] == 0
    assert run_manifest["treasury_labs_handoffs_executed"] == 0

    maturity = Counter()
    verification = Counter()
    scored = 0
    execution_entries = 0
    for entry in run_manifest["artifacts"]:
        for relative_path, expected_hash in entry["sha256"].items():
            path = run_dir / relative_path
            assert path.exists()
            assert sha256(path.read_bytes()).hexdigest() == expected_hash

        output_path = run_dir / entry["files"]["intelligence_output"]
        output = json.loads(output_path.read_text(encoding="utf-8"))
        maturity[output["maturity"]["stage"]] += 1
        verification[output["source_verification"]["status"]] += 1
        scored += output["strategic_intelligence"] is not None
        assert [trace["stage"] for trace in output["plugin_trace"]] == [
            "source_verification",
            "strategic_intelligence",
            "commercialization_routing",
            "maturity_output",
        ]
        artifact_hash = output["artifact_hash"]
        output["artifact_hash"] = None
        assert sha256_json(output) == artifact_hash
        assert output["safety"]["automatic_dispatches"] == 0
        assert output["safety"]["external_actions_executed"] == 0
        assert output["safety"]["treasury_labs_handoffs_executed"] == 0

        has_execution = "execution_run_id" in entry
        execution_entries += has_execution
        assert has_execution is (entry["intelligence"]["maturity_stage"] == "HUMAN_REVIEW")

    assert verification == Counter({"VERIFIED": 13, "NEEDS_SOURCE_VERIFICATION": 9})
    assert scored == 13
    assert execution_entries == 5
    assert maturity == Counter(
        {
            "CLOSED": 7,
            "PROGRAM_DISCOVERY": 6,
            "HUMAN_REVIEW": 5,
            "SOURCE_DISCOVERY": 3,
            "FORECAST_MONITOR": 1,
        }
    )


def test_manifest_pins_policy_and_fixture_bytes() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    paths = (
        manifest["policies"]["strategic_intelligence"],
        manifest["policies"]["commercialization"],
        manifest["interoperability_fixture"]["batch"],
        manifest["interoperability_fixture"]["evidence"],
    )

    for item in paths:
        path = ROOT / item["path"]
        assert path.exists()
        assert sha256(path.read_bytes()).hexdigest() == item["sha256"]

    assert manifest["safety"] == {
        "human_authorization_required": True,
        "automatic_dispatches": 0,
        "external_actions_executed": 0,
        "treasury_labs_handoffs_executed": 0,
        "replay_side_effects": False,
    }
