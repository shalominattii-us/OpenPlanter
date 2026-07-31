from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .context_snapshot import SQLiteExecutionContextSnapshotStore
from .execution_record import ExecutionRecorder
from .lifecycle import ExecutionLifecycle
from .orchestrator import DeterministicExecutionOrchestrator
from .pipeline import UniversalIntakeAdapter, build_mission_candidate
from .runtime import (
    DeterministicExecutionService,
    DeterministicRunLoop,
    EligibilityExecutorPlugin,
    PluginRegistry,
    PluginRuntime,
    ResearchExecutorPlugin,
)
from .sqlite_store import SQLiteExecutionEventStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openplanter-execute",
        description="Create, inspect, and advance durable opportunity executions.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a durable execution from a normalized record")
    _database_argument(init)
    init.add_argument("--input", type=Path, required=True, help="Normalized opportunity JSON object")
    init.add_argument("--source-name", default="operator-input")
    init.add_argument("--source-url", default="operator://input")
    init.add_argument("--actor", default="openplanter-execution-cli")

    status = subparsers.add_parser("status", help="Inspect a durable execution")
    _database_argument(status)
    status.add_argument("--run-id", required=True)

    advance = subparsers.add_parser("advance", help="Advance execution until a bounded checkpoint")
    _database_argument(advance)
    advance.add_argument("--run-id", required=True)
    advance.add_argument("--max-steps", type=int, default=1)
    advance.add_argument("--actor", default="openplanter-execution-cli")
    advance.add_argument("--trace-id", default="")
    advance.add_argument(
        "--artifact-root",
        type=Path,
        help="Durable artifact directory; defaults beside the execution database",
    )

    approve = subparsers.add_parser("approve", help="Approve an explicitly gated running step")
    _database_argument(approve)
    approve.add_argument("--run-id", required=True)
    approve.add_argument("--step-id", required=True)
    approve.add_argument("--actor", required=True)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            payload = _initialize(args)
        elif args.command == "status":
            payload = _status(args.database, args.run_id)
        elif args.command == "advance":
            payload = _advance(args)
        elif args.command == "approve":
            payload = _approve(args)
        else:  # pragma: no cover - argparse enforces commands
            raise ValueError(f"unsupported command: {args.command}")
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        return 1

    print(json.dumps({"ok": True, **payload}, indent=2, sort_keys=True, default=str))
    return 0


def _initialize(args: argparse.Namespace) -> Mapping[str, Any]:
    record = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError("input must contain one JSON object")

    now = datetime.now(timezone.utc)
    adapter = UniversalIntakeAdapter(
        source_name=args.source_name,
        source_url=args.source_url,
    )
    opportunity = adapter.opportunity_from_record(record, retrieved_at=now)
    packet = adapter.evidence_from_record(opportunity, record, created_at=now)
    candidate = build_mission_candidate(opportunity, packet, created_at=now)
    lifecycle = _lifecycle(args.database, actor=args.actor)
    context = lifecycle.initialize(opportunity, packet, candidate, occurred_at=now)
    SQLiteExecutionContextSnapshotStore(args.database).save(context)
    return _context_summary(context, DeterministicExecutionOrchestrator(lifecycle))


def _status(database: Path, run_id: str) -> Mapping[str, Any]:
    lifecycle = _lifecycle(database)
    context = SQLiteExecutionContextSnapshotStore(database).load_context(run_id, lifecycle)
    return _context_summary(context, DeterministicExecutionOrchestrator(lifecycle))


def _advance(args: argparse.Namespace) -> Mapping[str, Any]:
    if args.max_steps < 1:
        raise ValueError("max-steps must be at least 1")
    lifecycle = _lifecycle(args.database, actor=args.actor)
    context = SQLiteExecutionContextSnapshotStore(args.database).load_context(
        args.run_id,
        lifecycle,
    )
    registry = PluginRegistry()
    registry.register(ResearchExecutorPlugin())
    registry.register(EligibilityExecutorPlugin())
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    artifact_root = args.artifact_root or (args.database.parent / "artifacts")
    service = DeterministicExecutionService.create(
        orchestrator,
        PluginRuntime(registry),
        artifact_root=artifact_root,
    )
    report = DeterministicRunLoop(service).execute_until_checkpoint(
        context,
        actor=args.actor,
        max_steps=args.max_steps,
        trace_id=args.trace_id,
    )
    return {
        **_context_summary(report.context, orchestrator),
        "checkpoint": report.checkpoint.value,
        "steps_attempted": report.steps_attempted,
        "events_recorded": report.events_recorded,
        "artifact_root": str(artifact_root.resolve()),
    }


def _approve(args: argparse.Namespace) -> Mapping[str, Any]:
    lifecycle = _lifecycle(args.database, actor=args.actor)
    context = SQLiteExecutionContextSnapshotStore(args.database).load_context(
        args.run_id,
        lifecycle,
    )
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    approved = orchestrator.approve_step(
        context,
        args.step_id,
        actor=args.actor,
    )
    return _context_summary(approved, orchestrator)


def _context_summary(context, orchestrator: DeterministicExecutionOrchestrator) -> Mapping[str, Any]:
    state = orchestrator.state(context)
    return {
        "execution_run_id": context.execution_run.execution_run_id,
        "execution_plan_id": context.execution_plan.execution_plan_id,
        "opportunity_id": context.opportunity.opportunity_id,
        "title": context.opportunity.title,
        "run_status": context.execution_run.status.value,
        "next_step_id": state.next_step_id,
        "event_count": len(context.events),
        "artifact_count": len(context.artifacts),
        "artifacts": [
            {
                "artifact_id": artifact.artifact_id,
                "name": artifact.name,
                "uri": artifact.uri,
                "media_type": artifact.media_type,
                "checksum_sha256": artifact.checksum_sha256,
                "step_id": artifact.step_id,
            }
            for artifact in context.artifacts
        ],
        "steps": [
            {
                "step_id": step.step_id,
                "sequence": step.sequence,
                "kind": step.kind.value,
                "approval": step.approval.value,
                "status": state.step(step.step_id).status.value,
            }
            for step in context.execution_plan.steps
        ],
    }


def _lifecycle(database: Path, *, actor: str = "openplanter-execution-cli") -> ExecutionLifecycle:
    store = SQLiteExecutionEventStore(database)
    return ExecutionLifecycle(recorder=ExecutionRecorder(store), actor=actor)


def _database_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("var/opportunities/execution.sqlite3"),
    )


if __name__ == "__main__":
    raise SystemExit(main())
