from gov_ops.sam_gov import normalize_sam_opportunity, normalize_search_response


def sample_record():
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
    }


def test_normalize_sam_opportunity_emits_canonical_contract():
    opportunity = normalize_sam_opportunity(sample_record())

    assert opportunity.opportunity_id.startswith("opp_")
    assert opportunity.source == "sam.gov"
    assert opportunity.source_record_id == "abc123"
    assert opportunity.title == "Autonomous Data Analysis Support"
    assert opportunity.naics == ["541512"]
    assert opportunity.contact["email"] == "alex@example.gov"
    assert opportunity.attachments == [{"url": "https://example.gov/attachment.pdf"}]
    assert opportunity.status == "ingested"


def test_normalize_search_response():
    normalized = normalize_search_response({"opportunitiesData": [sample_record()]})
    assert len(normalized) == 1
    assert normalized[0].solicitation_number == "TEST-001"


def test_stable_opportunity_id():
    first = normalize_sam_opportunity(sample_record())
    second = normalize_sam_opportunity(sample_record())
    assert first.opportunity_id == second.opportunity_id
