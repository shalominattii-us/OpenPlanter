from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Opportunity:
    """Canonical opportunity object emitted by every intake source."""

    opportunity_id: str
    source: str
    source_record_id: str
    title: str
    agency: str | None = None
    office: str | None = None
    solicitation_number: str | None = None
    notice_type: str | None = None
    posted_date: str | None = None
    due_date: str | None = None
    naics: list[str] = field(default_factory=list)
    psc: str | None = None
    set_aside: str | None = None
    location: dict[str, Any] = field(default_factory=dict)
    description: str | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)
    contact: dict[str, Any] = field(default_factory=dict)
    urls: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "ingested"

    def validate(self) -> None:
        missing = [
            name
            for name, value in (
                ("opportunity_id", self.opportunity_id),
                ("source", self.source),
                ("source_record_id", self.source_record_id),
                ("title", self.title),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Missing required opportunity fields: {', '.join(missing)}")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)
