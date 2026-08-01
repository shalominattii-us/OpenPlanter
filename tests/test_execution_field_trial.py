import json
from pathlib import Path

from agent.opportunities.field_trial import main, run_field_trial


def test_field_trial_completes_full_durable_lifecycle(tmp_path) -> None:
    result = run_field_trial(tmp_path / "trial", actor="test-operator")

    assert result["run_status"] == "completed"
    assert result["checkpoint"] == "completed"
    assert result["artifact_count"] == 12
    assert "submission-receipt.json" in result["artifacts"]
    assert "outcome-record.json" in result["artifacts"]
    assert Path(result["database"]).is_file()
    assert Path(result["artifact_root"]).is_dir()


def test_field_trial_artifacts_are_inspectable_and_checksummed(tmp_path) -> None:
    result = run_field_trial(tmp_path / "trial", actor="test-operator")
    root = Path(result["artifact_root"])

    paths = tuple(root.rglob("*"))
    files = tuple(path for path in paths if path.is_file())
    assert len(files) == 12
    outcome = next(path for path in files if path.name == "outcome-record.json")
    receipt = next(path for path in files if path.name == "submission-receipt.json")
    outcome_payload = json.loads(outcome.read_text(encoding="utf-8"))
    receipt_payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert outcome_payload["submission_status"] == "simulated_not_sent"
    assert outcome_payload["financial_outcome"]["revenue_recognized"] == 0
    assert receipt_payload["approval_boundary"] == "satisfied_by_orchestrator_before_dispatch"


def test_field_trial_command_returns_machine_readable_summary(tmp_path, capsys) -> None:
    code = main(["--workspace", str(tmp_path / "trial"), "--actor", "test-operator"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["run_status"] == "completed"
    assert payload["artifact_count"] == 12


def test_field_trial_refuses_to_overwrite_existing_ledger(tmp_path, capsys) -> None:
    workspace = tmp_path / "trial"
    assert main(["--workspace", str(workspace)]) == 0
    capsys.readouterr()

    code = main(["--workspace", str(workspace)])

    assert code == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["ok"] is False
    assert "database already exists" in payload["error"]
