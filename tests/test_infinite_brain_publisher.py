from __future__ import annotations

from datetime import datetime, timezone

from gov_ops.infinite_brain import InfiniteBrainPublisher
from gov_ops.opportunity import Opportunity


def test_publish_writes_schema_compatible_intake_record(tmp_path) -> None:
    opportunity = Opportunity(
        opportunity_id="sam-abc123",
        source="sam.gov",
        source_record_id="abc123",
        title="Advanced Power Systems Research",
        agency="Department of Example",
        office="Research Office",
        solicitation_number="EX-2026-01",
        notice_type="Solicitation",
        posted_date="2026-07-20",
        due_date="2026-08-31",
        naics=["541715"],
        psc="AJ12",
        description="Research and development support for advanced power systems.",
        urls=["https://sam.gov/opp/abc123/view"],
    )
    publisher = InfiniteBrainPublisher(
        tmp_path,
        received_at=datetime(2026, 7, 24, 12, 30, tzinfo=timezone.utc),
    )

    result = publisher.publish(opportunity)

    assert result.opportunity_id == opportunity.opportunity_id
    assert result.path.exists()
    assert result.path.parent == tmp_path / "intake" / "sources" / "web"

    content = result.path.read_text(encoding="utf-8")
    assert 'type: "intake-record"' in content
    assert 'source: "web"' in content
    assert 'received_at: "2026-07-24T12:30:00Z"' in content
    assert "sam-abc123" in content
    assert "EX-2026-01" in content
    assert "Advanced Power Systems Research" in content


def test_publish_many_preserves_every_opportunity_id(tmp_path) -> None:
    opportunities = [
        Opportunity(
            opportunity_id=f"sam-{index}",
            source="sam.gov",
            source_record_id=str(index),
            title=f"Opportunity {index}",
        )
        for index in range(2)
    ]
    publisher = InfiniteBrainPublisher(
        tmp_path,
        received_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
    )

    published = publisher.publish_many(opportunities)

    assert [item.opportunity_id for item in published] == ["sam-0", "sam-1"]
    assert all(item.path.exists() for item in published)
