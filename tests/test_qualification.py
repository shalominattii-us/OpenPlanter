from __future__ import annotations

from datetime import datetime, timezone

from gov_ops.opportunity import Opportunity
from gov_ops.qualification import QualificationEngine


OBSERVED_AT = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


def test_complete_open_opportunity_becomes_mission_candidate() -> None:
    opportunity = Opportunity(
        opportunity_id="sam-qualified",
        source="sam.gov",
        source_record_id="qualified",
        title="Advanced Energy Demonstration",
        agency="Department of Example",
        due_date="2026-09-30",
        naics=["541715"],
        description="Develop and demonstrate an advanced energy system.",
        urls=["https://sam.gov/opp/qualified/view"],
    )

    result = QualificationEngine().qualify(opportunity, observed_at=OBSERVED_AT)

    assert result.evidence.completeness == 1.0
    assert result.evidence.deadline_state == "open"
    assert result.decision.outcome == "mission_candidate"
    assert result.decision.score >= 0.65
    assert result.mission_candidate is not None
    assert result.mission_candidate.opportunity_id == opportunity.opportunity_id
    assert result.mission_candidate.decision_id == result.decision.decision_id


def test_promising_opportunity_with_unknown_deadline_requires_operator_review() -> None:
    opportunity = Opportunity(
        opportunity_id="sam-review",
        source="sam.gov",
        source_record_id="review",
        title="Sparse Research Notice",
        agency="Department of Example",
        description="Research support with a deadline that has not yet been published.",
        urls=["https://sam.gov/opp/review/view"],
    )

    result = QualificationEngine().qualify(opportunity, observed_at=OBSERVED_AT)

    assert result.decision.outcome == "operator_review"
    assert "due_date" in result.evidence.missing_fields
    assert result.mission_candidate is None


def test_expired_opportunity_is_rejected_even_when_complete() -> None:
    opportunity = Opportunity(
        opportunity_id="sam-expired",
        source="sam.gov",
        source_record_id="expired",
        title="Expired Systems Work",
        agency="Department of Example",
        due_date="2026-07-01",
        naics=["541715"],
        description="An otherwise complete but expired opportunity.",
        urls=["https://sam.gov/opp/expired/view"],
    )

    result = QualificationEngine().qualify(opportunity, observed_at=OBSERVED_AT)

    assert result.evidence.deadline_state == "expired"
    assert result.decision.outcome == "rejected"
    assert result.decision.score == 0.0
    assert result.mission_candidate is None


def test_identifiers_are_stable_across_requalification() -> None:
    opportunity = Opportunity(
        opportunity_id="sam-stable",
        source="sam.gov",
        source_record_id="stable",
        title="Stable Identity Opportunity",
        agency="Department of Example",
        due_date="2026-10-01",
        description="Stable identifiers preserve graph lineage.",
        urls=["https://sam.gov/opp/stable/view"],
    )
    engine = QualificationEngine()

    first = engine.qualify(opportunity, observed_at=OBSERVED_AT)
    second = engine.qualify(opportunity, observed_at=OBSERVED_AT)

    assert first.evidence.evidence_id == second.evidence.evidence_id
    assert first.decision.decision_id == second.decision.decision_id
    assert first.mission_candidate is not None
    assert second.mission_candidate is not None
    assert first.mission_candidate.candidate_id == second.mission_candidate.candidate_id
