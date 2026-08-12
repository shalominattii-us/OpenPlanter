from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .adapters.sam_gov import SAMGovClient, SAMGovSource
from .integration import (
    DailyIntakeResult,
    JsonDirectoryArtifactSink,
    UniversalDailyIntakeBridge,
)
from .intelligence import OpportunityIntelligencePipeline
from .pipeline import UniversalIntakeAdapter
from .sources import OpportunitySource, collect_normalized

Record = Mapping[str, object]
ReportRenderer = Callable[[Sequence[Record]], str]
LOGGER = logging.getLogger("openplanter.opportunities")


@dataclass(frozen=True)
class IntakeRunConfig:
    output_root: Path
    report_path: Path
    posted_from: str
    posted_to: str
    limit: int = 100
    offset: int = 0
    title: str | None = None
    notice_type: str | None = None
    naics: str | None = None
    organization: str | None = None

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("limit must be at least 1")
        if self.offset < 0:
            raise ValueError("offset cannot be negative")


def render_json_report(records: Sequence[Record]) -> str:
    """Deterministic fallback report for standalone operation.

    Existing deployments can inject their current renderer into ``run_source`` or
    ``run_sam_daily`` so report bytes remain under the legacy renderer's control.
    """

    return json.dumps(list(records), indent=2, sort_keys=True, default=str) + "\n"


def run_source(
    source: OpportunitySource,
    *,
    output_root: Path,
    report_path: Path,
    render_report: ReportRenderer,
    generated_at: datetime | None = None,
) -> DailyIntakeResult:
    metadata = source.metadata()
    records = collect_normalized(source)
    LOGGER.info("collected %d records from %s", len(records), metadata.source_name)

    bridge = UniversalDailyIntakeBridge(
        adapter=UniversalIntakeAdapter(
            source_name=metadata.source_name,
            source_url=metadata.source_url,
        ),
        sink=JsonDirectoryArtifactSink(output_root),
        intelligence_pipeline=OpportunityIntelligencePipeline.default(),
    )
    result = bridge.run(
        records,
        render_report=render_report,
        generated_at=generated_at,
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(result.report, encoding="utf-8")
    LOGGER.info(
        "wrote report to %s and %d artifact bundles to %s",
        report_path,
        len(result.artifacts),
        output_root,
    )
    return result


def run_sam_daily(
    *,
    api_key: str,
    config: IntakeRunConfig,
    render_report: ReportRenderer = render_json_report,
    generated_at: datetime | None = None,
) -> DailyIntakeResult:
    source = SAMGovSource(
        client=SAMGovClient(api_key=api_key),
        posted_from=config.posted_from,
        posted_to=config.posted_to,
        limit=config.limit,
        offset=config.offset,
        title=config.title,
        notice_type=config.notice_type,
        naics=config.naics,
        organization=config.organization,
    )
    return run_source(
        source,
        output_root=config.output_root,
        report_path=config.report_path,
        render_report=render_report,
        generated_at=generated_at,
    )


def build_parser() -> argparse.ArgumentParser:
    today = date.today()
    yesterday = today - timedelta(days=1)
    parser = argparse.ArgumentParser(
        prog="openplanter-opportunities",
        description="Fetch SAM.gov opportunities, render a report, and persist canonical artifacts.",
    )
    parser.add_argument("--posted-from", default=yesterday.strftime("%m/%d/%Y"))
    parser.add_argument("--posted-to", default=today.strftime("%m/%d/%Y"))
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--title")
    parser.add_argument("--notice-type")
    parser.add_argument("--naics")
    parser.add_argument("--organization")
    parser.add_argument("--output-root", type=Path, default=Path("var/opportunities/runs"))
    parser.add_argument("--report-path", type=Path, default=Path("var/opportunities/latest-report.json"))
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "INFO"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    api_key = os.getenv("SAM_GOV_API_KEY", "").strip()
    if not api_key:
        LOGGER.error("SAM_GOV_API_KEY is required")
        return 2

    try:
        config = IntakeRunConfig(
            output_root=args.output_root,
            report_path=args.report_path,
            posted_from=args.posted_from,
            posted_to=args.posted_to,
            limit=args.limit,
            offset=args.offset,
            title=args.title,
            notice_type=args.notice_type,
            naics=args.naics,
            organization=args.organization,
        )
        result = run_sam_daily(api_key=api_key, config=config)
    except (OSError, RuntimeError, ValueError) as exc:
        LOGGER.exception("opportunity intake failed: %s", exc)
        return 1

    LOGGER.info(
        "opportunity intake completed at %s with %d artifacts",
        result.generated_at.astimezone(timezone.utc).isoformat(),
        len(result.artifacts),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
