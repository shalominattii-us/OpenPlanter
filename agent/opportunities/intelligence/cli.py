from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..integration import JsonDirectoryArtifactSink, UniversalDailyIntakeBridge
from ..pipeline import UniversalIntakeAdapter
from .cybercore import load_cybercore_batch
from .pipeline import OpportunityIntelligencePipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="foundry-cybercore",
        description=(
            "Run a Cybercore opportunity batch through Foundry source verification, "
            "strategic intelligence, commercialization routing, and maturity output."
        ),
    )
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("var/opportunities/cybercore-runs"),
    )
    parser.add_argument(
        "--evaluated-at",
        help="Timezone-aware ISO-8601 timestamp; defaults to the current UTC time",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        evaluated_at = _timestamp(args.evaluated_at)
        batch = load_cybercore_batch(args.batch, evidence_path=args.evidence)
        bridge = UniversalDailyIntakeBridge(
            adapter=UniversalIntakeAdapter(
                source_name="AEGENTIX Cybercore",
                source_url="https://github.com/shalominattii-us/sovereign-os",
            ),
            sink=JsonDirectoryArtifactSink(args.output_root),
            intelligence_pipeline=OpportunityIntelligencePipeline.default(),
        )
        result = bridge.run(
            batch.records,
            render_report=_render_report,
            generated_at=evaluated_at,
        )
        run_id = evaluated_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        payload = _summary(batch.batch_id, result.artifacts, args.output_root / run_id)
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps(
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps({"ok": True, **payload}, indent=2, sort_keys=True))
    return 0


def _render_report(records: Sequence[dict[str, Any]]) -> str:
    return json.dumps(list(records), indent=2, sort_keys=True, default=str) + "\n"


def _summary(batch_id: str, artifacts, run_dir: Path) -> dict[str, Any]:
    outputs = tuple(
        bundle.intelligence_output
        for bundle in artifacts
        if bundle.intelligence_output is not None
    )
    maturity = Counter(output.maturity.stage.value for output in outputs)
    verification = Counter(
        output.source_verification.status.value for output in outputs
    )
    routing = Counter(output.commercialization.status.value for output in outputs)
    return {
        "batch_id": batch_id,
        "record_count": len(artifacts),
        "intelligence_output_count": len(outputs),
        "execution_context_count": sum(
            bundle.execution_context is not None for bundle in artifacts
        ),
        "verification": dict(sorted(verification.items())),
        "maturity": dict(sorted(maturity.items())),
        "commercialization": dict(sorted(routing.items())),
        "safety": {
            "authorization_policy": "human_required",
            "automatic_dispatches": 0,
            "external_actions_executed": 0,
            "treasury_labs_handoffs_executed": 0,
        },
        "run_directory": str(run_dir.resolve()),
        "manifest": str((run_dir / "manifest.json").resolve()),
    }


def _timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("evaluated-at must be timezone-aware")
    return parsed.astimezone(timezone.utc)


if __name__ == "__main__":
    raise SystemExit(main())
