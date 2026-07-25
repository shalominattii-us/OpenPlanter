from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from gov_ops.opportunity import Opportunity


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str, *, max_length: int = 40) -> str:
    slug = _SLUG_RE.sub("-", value.lower()).strip("-")
    return slug[:max_length].rstrip("-") or "opportunity"


def _yaml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
    return f'"{escaped}"'


@dataclass(frozen=True)
class PublishedIntakeRecord:
    opportunity_id: str
    path: Path
    intake_id: str


class InfiniteBrainPublisher:
    """Publish canonical opportunities into Infinite Brain's durable intake fabric.

    This adapter writes one schema-compatible Markdown intake record per opportunity.
    It intentionally does not manage live queue state, routing decisions, or canon
    promotion. Those responsibilities remain inside the Infinite Brain runtime.
    """

    source_family = "web"

    def __init__(self, brain_root: Path, *, received_at: datetime | None = None) -> None:
        self.brain_root = Path(brain_root)
        self.received_at = received_at

    @property
    def destination(self) -> Path:
        return self.brain_root / "intake" / "sources" / self.source_family

    def publish(self, opportunity: Opportunity) -> PublishedIntakeRecord:
        opportunity.validate()
        captured_at = self.received_at or datetime.now(timezone.utc)
        captured_at = captured_at.astimezone(timezone.utc)
        capture_date = captured_at.date().isoformat()
        intake_id = f"intake-web-{capture_date}-{_slugify(opportunity.title)}"
        path = self.destination / f"{intake_id}.md"

        self.destination.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self.render(opportunity, intake_id=intake_id, captured_at=captured_at),
            encoding="utf-8",
        )
        return PublishedIntakeRecord(
            opportunity_id=opportunity.opportunity_id,
            path=path,
            intake_id=intake_id,
        )

    def publish_many(self, opportunities: Iterable[Opportunity]) -> list[PublishedIntakeRecord]:
        return [self.publish(opportunity) for opportunity in opportunities]

    def render(self, opportunity: Opportunity, *, intake_id: str, captured_at: datetime) -> str:
        original_ref = opportunity.urls[0] if opportunity.urls else f"sam.gov:{opportunity.source_record_id}"
        creator = opportunity.agency or "unknown"
        summary = opportunity.description or opportunity.title
        summary = " ".join(summary.split())[:500]
        why_it_matters = (
            "Government opportunity captured for qualification, routing, and possible mission creation."
        )
        raw_capture = f"external:{opportunity.source}:{opportunity.source_record_id}"
        received_at = captured_at.isoformat().replace("+00:00", "Z")
        created = captured_at.date().isoformat()

        lines = [
            "---",
            f"id: {_yaml_string(intake_id)}",
            f"aliases: [{_yaml_string(intake_id)}]",
            'type: "intake-record"',
            'namespace: "personal-operator"',
            f"source: {_yaml_string(self.source_family)}",
            f"creator: {_yaml_string(creator)}",
            f"original_ref: {_yaml_string(original_ref)}",
            f"received_at: {_yaml_string(received_at)}",
            f"raw_capture: {_yaml_string(raw_capture)}",
            f"summary: {_yaml_string(summary)}",
            f"why_it_matters: {_yaml_string(why_it_matters)}",
            'lifecycle_state: "scratch"',
            "confidence: 1.0",
            'retrieval_class: "ephemeral"',
            'export_class: "internal"',
            f"created: {_yaml_string(created)}",
            "---",
            "",
            "## Source",
            "",
            f"- Platform: {opportunity.source}",
            f"- Creator: {creator}",
            f"- Original: {original_ref}",
            f"- Captured: {received_at}",
            f"- Raw capture: {raw_capture}",
            f"- Opportunity ID: {opportunity.opportunity_id}",
            f"- Source record ID: {opportunity.source_record_id}",
            "",
            "## Captured content",
            "",
            opportunity.description or opportunity.title,
            "",
            "## Extracted summary",
            "",
            summary,
            "",
            "## Why it matters",
            "",
            why_it_matters,
            "",
            "## Opportunity metadata",
            "",
            f"- Agency: {opportunity.agency or 'unknown'}",
            f"- Office: {opportunity.office or 'unknown'}",
            f"- Solicitation number: {opportunity.solicitation_number or 'unknown'}",
            f"- Notice type: {opportunity.notice_type or 'unknown'}",
            f"- Posted date: {opportunity.posted_date or 'unknown'}",
            f"- Due date: {opportunity.due_date or 'unknown'}",
            f"- NAICS: {', '.join(opportunity.naics) if opportunity.naics else 'unknown'}",
            f"- PSC: {opportunity.psc or 'unknown'}",
            f"- Set aside: {opportunity.set_aside or 'unknown'}",
            "",
        ]
        return "\n".join(lines)
