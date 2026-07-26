from __future__ import annotations

from datetime import datetime, timezone

from agent.opportunities import (
    SAMGovSource,
    UniversalDailyIntakeBridge,
    UniversalIntakeAdapter,
    collect_normalized,
    normalize_sam_record,
)


def _sam_record() -> dict[str, object]:
    return {
        "noticeId": "abc123",
        "title": "Autonomous Data Analysis Support",
        "solicitationNumber": "TEST-001",
        "fullParentPathName": "DEPARTMENT OF TESTING.TEST OFFICE",
        "office": "TEST OFFICE",
        "postedDate": "2026-07-20",
        "responseDeadLine": "2026-08-20T17:00:00-04:00",
        "type": "Solicitation",
        "naicsCode": "541512",
        "classificationCode": "DA10",
        "typeOfSetAsideDescription": "Small Business Set-Aside",
        "description": "Provide an automated analysis capability.",
        "uiLink": "https://sam.gov/opp/abc123/view",
        "resourceLinks": ["https://example.gov/attachment.pdf"],
        "pointOfContact": [
            {
                "fullname": "Alex Example",
                "email": "alex@example.gov",
                "phone": "555-0100",
                "type": "primary",
            }
        ],
        "placeOfPerformance": {
            "city": {"name": "Washington"},
            "state": {"code": "DC"},
            "country": {"code": "USA"},
            "zip": "20001",
        },
        "active": True,
    }


class StubSAMClient:
    def search(self, **kwargs):
        self.kwargs = kwargs
        return (_sam_record(),)


def test_normalize_sam_record_preserves_source_specific_metadata() -> None:
    record = normalize_sam_record(_sam_record())

    assert record["external_id"] == "abc123"
    assert record["source"] == "SAM.gov"
    assert record["deadline"] == "2026-08-20"
    assert record["attachments"] == ("https://example.gov/attachment.pdf",)
    assert record["naics"] == ("541512",)
    assert record["psc"] == "DA10"
    assert record["set_aside"] == "Small Business Set-Aside"
    assert record["contact"]["email"] == "alex@example.gov"
    assert record["location"]["state"] == "DC"


def test_sam_source_implements_fetch_normalize_validate_contract() -> None:
    client = StubSAMClient()
    source = SAMGovSource(
        client=client,
        posted_from="07/01/2026",
        posted_to="07/26/2026",
        limit=25,
    )

    records = collect_normalized(source)

    assert len(records) == 1
    assert records[0]["solicitation_number"] == "TEST-001"
    assert client.kwargs["limit"] == 25
    assert source.metadata().adapter_version == "1.0.0"


def test_sam_record_flows_through_canonical_daily_bridge_without_report_change() -> None:
    normalized = normalize_sam_record(_sam_record())
    bridge = UniversalDailyIntakeBridge(
        adapter=UniversalIntakeAdapter(
            source_name="SAM.gov",
            source_url="https://sam.gov/",
        )
    )

    result = bridge.run(
        [normalized],
        render_report=lambda records: "CURRENT SAM DAILY REPORT\n",
        generated_at=datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc),
    )

    bundle = result.artifacts[0]
    assert result.report == "CURRENT SAM DAILY REPORT\n"
    assert bundle.opportunity.external_id == "abc123"
    assert bundle.opportunity.deadline.isoformat() == "2026-08-20"
    assert bundle.opportunity.attachments == ("https://example.gov/attachment.pdf",)
    assert bundle.opportunity.metadata["naics"] == ("541512",)


def test_sam_normalizer_rejects_records_without_stable_identity() -> None:
    try:
        normalize_sam_record({"title": "Missing notice ID"})
    except ValueError as exc:
        assert "noticeId and title" in str(exc)
    else:
        raise AssertionError("expected ValueError")
