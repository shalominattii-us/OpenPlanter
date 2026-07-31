import json

from agent.opportunities.execution_cli import main


def record():
    return {
        "external_id": "cli-1",
        "title": "Validate operational execution CLI",
        "source": "operator-input",
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


def initialize(tmp_path, capsys):
    database = tmp_path / "execution.sqlite3"
    source = tmp_path / "opportunity.json"
    source.write_text(json.dumps(record()), encoding="utf-8")
    code = main(
        [
            "init",
            "--database",
            str(database),
            "--input",
            str(source),
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    return database, payload


def test_cli_initializes_durable_execution(tmp_path, capsys) -> None:
    database, payload = initialize(tmp_path, capsys)

    assert database.exists()
    assert payload["ok"] is True
    assert payload["run_status"] == "created"
    assert payload["event_count"] == 1
    assert len(payload["steps"]) == 7


def test_cli_status_rehydrates_execution_after_restart(tmp_path, capsys) -> None:
    database, initialized = initialize(tmp_path, capsys)

    code = main(
        [
            "status",
            "--database",
            str(database),
            "--run-id",
            initialized["execution_run_id"],
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["execution_run_id"] == initialized["execution_run_id"]
    assert payload["title"] == record()["title"]
    assert payload["run_status"] == "created"


def test_cli_advances_real_plugins_with_bounded_run(tmp_path, capsys) -> None:
    database, initialized = initialize(tmp_path, capsys)

    code = main(
        [
            "advance",
            "--database",
            str(database),
            "--run-id",
            initialized["execution_run_id"],
            "--max-steps",
            "2",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["checkpoint"] == "step_limit_reached"
    assert payload["steps_attempted"] == 2
    assert payload["run_status"] == "running"
    assert payload["artifact_count"] == 2
    assert [item["status"] for item in payload["steps"][:2]] == [
        "completed",
        "completed",
    ]


def test_cli_reports_invalid_input_without_traceback(tmp_path, capsys) -> None:
    database = tmp_path / "execution.sqlite3"
    source = tmp_path / "invalid.json"
    source.write_text("[]", encoding="utf-8")

    code = main(
        [
            "init",
            "--database",
            str(database),
            "--input",
            str(source),
        ]
    )

    assert code == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["ok"] is False
    assert "input must contain one JSON object" in payload["error"]
