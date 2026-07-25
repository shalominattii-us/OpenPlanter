#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from gov_ops.infinite_brain import InfiniteBrainPublisher
from gov_ops.mission_graph import MissionGraphBuilder
from gov_ops.qualification import QualificationEngine
from gov_ops.sam_gov import SAMGovOpportunitiesClient, normalize_search_response


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch active SAM.gov opportunities, emit canonical Opportunity objects, "
            "and optionally produce deterministic qualification and mission-lineage records."
        )
    )
    parser.add_argument("--api-key", default=os.getenv("SAM_GOV_API_KEY"))
    parser.add_argument("--posted-from", required=True, help="MM/DD/YYYY")
    parser.add_argument("--posted-to", required=True, help="MM/DD/YYYY")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--title")
    parser.add_argument("--notice-type")
    parser.add_argument("--naics")
    parser.add_argument("--organization")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--qualification-output",
        type=Path,
        help=(
            "Optional JSON output for evidence packages, decision records, and mission "
            "candidates produced by the deterministic qualification policy."
        ),
    )
    parser.add_argument(
        "--mission-graph-output",
        type=Path,
        help=(
            "Optional JSON output for replayable Opportunity -> Evidence -> Decision -> "
            "MissionCandidate lineage graphs. This does not create accepted missions."
        ),
    )
    parser.add_argument(
        "--infinite-brain-root",
        type=Path,
        help=(
            "Optional path to an Infinite Brain OS checkout. When provided, each "
            "opportunity is also written as a durable intake record."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.api_key:
        print("SAM.gov API key is required via --api-key or SAM_GOV_API_KEY", file=sys.stderr)
        return 2

    client = SAMGovOpportunitiesClient(args.api_key)
    payload = client.search(
        posted_from=args.posted_from,
        posted_to=args.posted_to,
        limit=args.limit,
        offset=args.offset,
        title=args.title,
        notice_type=args.notice_type,
        naics=args.naics,
        organization=args.organization,
    )
    normalized = normalize_search_response(payload)
    opportunities = [item.to_dict() for item in normalized]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(opportunities, indent=2), encoding="utf-8")
    print(f"Wrote {len(opportunities)} normalized opportunities to {args.output}")

    qualification_results = None
    if args.qualification_output or args.mission_graph_output:
        qualification_results = QualificationEngine().qualify_many(normalized)

    if args.qualification_output and qualification_results is not None:
        args.qualification_output.parent.mkdir(parents=True, exist_ok=True)
        args.qualification_output.write_text(
            json.dumps([item.to_dict() for item in qualification_results], indent=2),
            encoding="utf-8",
        )
        candidate_count = sum(
            item.mission_candidate is not None for item in qualification_results
        )
        print(
            f"Wrote {len(qualification_results)} qualification decisions with "
            f"{candidate_count} mission candidates to {args.qualification_output}"
        )

    if args.mission_graph_output and qualification_results is not None:
        builder = MissionGraphBuilder()
        graphs = [
            builder.build(opportunity, result)
            for opportunity, result in zip(normalized, qualification_results, strict=True)
        ]
        args.mission_graph_output.parent.mkdir(parents=True, exist_ok=True)
        args.mission_graph_output.write_text(
            json.dumps([graph.to_dict() for graph in graphs], indent=2),
            encoding="utf-8",
        )
        print(
            f"Wrote {len(graphs)} mission lineage graphs to "
            f"{args.mission_graph_output}"
        )

    if args.infinite_brain_root:
        publisher = InfiniteBrainPublisher(args.infinite_brain_root)
        published = publisher.publish_many(normalized)
        print(
            f"Published {len(published)} opportunities to "
            f"{publisher.destination}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
