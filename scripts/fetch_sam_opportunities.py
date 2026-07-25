#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from gov_ops.sam_gov import SAMGovOpportunitiesClient, normalize_search_response


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch active SAM.gov opportunities and emit canonical Opportunity objects."
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
    opportunities = [item.to_dict() for item in normalize_search_response(payload)]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(opportunities, indent=2), encoding="utf-8")
    print(f"Wrote {len(opportunities)} normalized opportunities to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
