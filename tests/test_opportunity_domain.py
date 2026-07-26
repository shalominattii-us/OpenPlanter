import json
import unittest
from datetime import datetime, timezone

from agent.opportunities import (
    QualificationStatus,
    UniversalIntakeAdapter,
    build_mission_candidate,
    to_primitive,
)


class TestUniversalOpportunityDomain(unittest.TestCase):
    def setUp(self):
        self.adapter = UniversalIntakeAdapter(
            source_name="Grants.gov",
            source_url="https://www.grants.gov/",
        )
        self.record = {
            "title": "Federal earthquake-risk mitigation",
            "source": "Grants.gov",
            "source_url": "https://www.grants.gov/search-results-detail/363128",
            "record_id": "363128",
            "issuer": "Federal Emergency Management Agency",
            "jurisdiction": "United States",
            "type": "Grant",
            "status": "open",
            "published_date": "2026-07-13",
            "deadline": "2026-08-14",
            "amount_max": 1_000_000,
            "eligibility": [
                "Nonprofits",
                "Public or private institutions of higher education",
            ],
            "sector": ["disaster resilience", "risk analytics"],
            "strategic_fit": "medium-high",
            "urgency": "high",
            "complexity": "medium",
            "eligibility_fit": "high",
            "strategic_fit_rationale": [
                "Relevant to simulation, geospatial systems and emergency planning"
            ],
            "revenue_path": "Direct grant or eligible partner",
        }
        self.now = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)

    def test_adapter_builds_stable_opportunity(self):
        first = self.adapter.opportunity_from_record(self.record, retrieved_at=self.now)
        second = self.adapter.opportunity_from_record(self.record, retrieved_at=self.now)

        self.assertEqual(first.opportunity_id, second.opportunity_id)
        self.assertEqual(first.external_id, "363128")
        self.assertEqual(first.version, 1)
        self.assertEqual(first.amount_max, 1_000_000)
        self.assertEqual(first.provenance.source_record_id, "363128")

    def test_evidence_packet_references_exact_opportunity_version(self):
        opportunity = self.adapter.opportunity_from_record(
            self.record, retrieved_at=self.now
        )
        packet = self.adapter.evidence_from_record(
            opportunity, self.record, created_at=self.now
        )

        self.assertEqual(packet.opportunity_id, opportunity.opportunity_id)
        self.assertEqual(packet.opportunity_version, opportunity.version)
        self.assertEqual(packet.score_for("strategic_fit"), 0.70)
        self.assertEqual(packet.score_for("urgency"), 0.85)
        self.assertGreater(packet.confidence, 0.0)

    def test_qualification_is_deterministic(self):
        opportunity = self.adapter.opportunity_from_record(
            self.record, retrieved_at=self.now
        )
        packet = self.adapter.evidence_from_record(
            opportunity, self.record, created_at=self.now
        )

        first = build_mission_candidate(
            opportunity, packet, created_at=self.now
        )
        second = build_mission_candidate(
            opportunity, packet, created_at=self.now
        )

        self.assertEqual(first.mission_candidate_id, second.mission_candidate_id)
        self.assertEqual(first.decision.score, second.decision.score)
        self.assertIn(
            first.decision.status,
            {
                QualificationStatus.QUALIFIED,
                QualificationStatus.REVIEW,
                QualificationStatus.REJECTED,
            },
        )
        self.assertEqual(first.evidence_packet_id, packet.evidence_packet_id)

    def test_domain_objects_serialize_to_json(self):
        opportunity = self.adapter.opportunity_from_record(
            self.record, retrieved_at=self.now
        )
        packet = self.adapter.evidence_from_record(
            opportunity, self.record, created_at=self.now
        )
        candidate = build_mission_candidate(
            opportunity, packet, created_at=self.now
        )

        payload = {
            "opportunity": to_primitive(opportunity),
            "evidence_packet": to_primitive(packet),
            "mission_candidate": to_primitive(candidate),
        }
        encoded = json.dumps(payload)

        self.assertIn(opportunity.opportunity_id, encoded)
        self.assertIn(packet.evidence_packet_id, encoded)
        self.assertIn(candidate.mission_candidate_id, encoded)


if __name__ == "__main__":
    unittest.main()
