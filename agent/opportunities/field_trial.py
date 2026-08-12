from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Mapping, Sequence

from .execution_cli import main as execution_main


_SAMPLE_RECORD: Mapping[str, Any] = {
    "external_id": "field-trial-1",
    "title": "Validate the Universal Opportunity Execution Engine",
    "source": "field-trial",
    "jurisdiction": "US",
    "type": "partnership",
    "status": "open",
    "issuer": "Field Trial Recipient",
    "deadline": "2026-09-15",
    "eligibility": ["US small business"],
    "submission_path": "local://field-trial-receipt",
    "strategic_fit": "very high",
    "urgency": "high",
    "complexity": "low",
    "eligibility_fit": "very high",
    "amount_max": 500000,
}

_EXPECTED_ARTIFACTS = frozenset(
    {
        "validated-opportunity-brief.json",
        "eligibility-matrix.json",
        "offer-design.json",
        "value-model.json",
        "proposal-draft.md",
        "implementation-plan.json",
        "budget-assumptions.json",
        "outreach-draft.md",
        "submission-checklist.md",
        "contact-brief.json",
        "submission-receipt.json",
        "outcome-record.json",
    }
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openplanter-field-trial",
        description="Run the complete durable execution lifecycle through the public CLI.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("var/opportunities/field-trial"),
        help="Directory for the database, source record, and durable artifacts",
    )
    parser.add_argument("--actor", default="field-trial-operator")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_field_trial(args.workspace, actor=args.actor)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, **result}, indent=2, sort_keys=True))
    return 0


def run_field_trial(workspace: Path, *, actor: str) -> Mapping[str, Any]:
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    database = workspace / "execution.sqlite3"
    source = workspace / "opportunity.json"
    artifacts = workspace / "artifacts"
    if database.exists():
        raise ValueError(f"field-trial database already exists: {database}")
    source.write_text(json.dumps(_SAMPLE_RECORD, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    initialized = _invoke(
        "init",
        "--database",
        str(database),
        "--input",
        str(source),
        "--source-name",
        "field-trial",
        "--source-url",
        "local://field-trial",
        "--actor",
        actor,
    )
    run_id = str(initialized["execution_run_id"])

    preapproval = _invoke(
        "advance",
        "--database",
        str(database),
        "--run-id",
        run_id,
        "--max-steps",
        "7",
        "--artifact-root",
        str(artifacts),
        "--actor",
        actor,
        "--trace-id",
        "field-trial-preapproval",
    )
    if preapproval["checkpoint"] != "awaiting_approval":
        raise RuntimeError(f"expected approval checkpoint, got {preapproval['checkpoint']}")
    submit_step = next(
        item for item in preapproval["steps"] if item["kind"] == "submit_response"
    )

    _invoke(
        "approve",
        "--database",
        str(database),
        "--run-id",
        run_id,
        "--step-id",
        str(submit_step["step_id"]),
        "--actor",
        actor,
    )
    completed = _invoke(
        "advance",
        "--database",
        str(database),
        "--run-id",
        run_id,
        "--max-steps",
        "2",
        "--artifact-root",
        str(artifacts),
        "--actor",
        actor,
        "--trace-id",
        "field-trial-postapproval",
    )
    final_status = _invoke(
        "status",
        "--database",
        str(database),
        "--run-id",
        run_id,
    )

    names = frozenset(item["name"] for item in final_status["artifacts"])
    missing = tuple(sorted(_EXPECTED_ARTIFACTS - names))
    if missing:
        raise RuntimeError(f"field trial is missing artifacts: {missing}")
    if completed["checkpoint"] != "completed" or final_status["run_status"] != "completed":
        raise RuntimeError("field trial did not complete")
    for artifact in final_status["artifacts"]:
        uri = str(artifact["uri"])
        checksum = artifact.get("checksum_sha256")
        if not uri.startswith("file://") or not checksum:
            raise RuntimeError(f"artifact is not durably materialized: {artifact['name']}")
        if not Path(uri.removeprefix("file://")).is_file():
            raise RuntimeError(f"artifact file is missing: {artifact['name']}")

    return {
        "execution_run_id": run_id,
        "run_status": final_status["run_status"],
        "checkpoint": completed["checkpoint"],
        "database": str(database),
        "artifact_root": str(artifacts),
        "artifact_count": final_status["artifact_count"],
        "event_count": final_status["event_count"],
        "approval_step_id": submit_step["step_id"],
        "artifacts": sorted(names),
    }


def _invoke(*argv: str) -> Mapping[str, Any]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = execution_main(list(argv))
    if code != 0:
        detail = stderr.getvalue().strip() or stdout.getvalue().strip()
        raise RuntimeError(f"openplanter-execute {' '.join(argv)} failed: {detail}")
    payload = json.loads(stdout.getvalue())
    if not payload.get("ok"):
        raise RuntimeError(f"openplanter-execute returned unsuccessful payload: {payload}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
