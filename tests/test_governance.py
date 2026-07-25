from __future__ import annotations

import pytest

from gov_ops.governance import (
    GovernanceRequest,
    SovereignAuthorization,
    SovereignGovernanceGate,
)
from gov_ops.opportunity import Opportunity
from gov_ops.qualification import QualificationEngine


def _candidate():
    opportunity = Opportunity(
        opportunity_id="sam-governed",
        source="sam.gov",
        source_record_id="governed",
        title="Governed Demonstration",
        agency="Department of Example",
        due_date="2027-01-15",
        naics=["541715"],
        description="A complete opportunity requiring governed acceptance.",
        urls=["https://sam.gov/opp/governed/view"],
    )
    result = QualificationEngine().qualify(opportunity)
    assert result.mission_candidate is not None
    return result.mission_candidate


def test_eaglecrat_or_application_cannot_create_mission_without_sovereign_authorization() -> None:
    candidate = _candidate()
    request = GovernanceRequest.from_candidate(candidate)
    authorization = SovereignAuthorization(
        authorization_id="auth-deferred",
        request_id=request.request_id,
        advisory_id="eaglecrat-advisory-1",
        decision="deferred",
        authority="Sovereign OS",
        decided_at="2026-07-25T21:00:00Z",
        rationale="Awaiting sovereign determination.",
    )

    with pytest.raises(PermissionError, match="sovereign authorization"):
        SovereignGovernanceGate().create_mission(candidate, request, authorization)


def test_authorized_mission_requires_ledger_commit() -> None:
    candidate = _candidate()
    request = GovernanceRequest.from_candidate(candidate)
    authorization = SovereignAuthorization(
        authorization_id="auth-missing-ledger",
        request_id=request.request_id,
        advisory_id="eaglecrat-advisory-1",
        decision="authorized",
        authority="Sovereign OS",
        decided_at="2026-07-25T21:00:00Z",
        rationale="Authorized in principle.",
    )

    with pytest.raises(ValueError, match="Ledger commit"):
        SovereignGovernanceGate().create_mission(candidate, request, authorization)


def test_sovereign_authorization_creates_mission() -> None:
    candidate = _candidate()
    request = GovernanceRequest.from_candidate(candidate)
    authorization = SovereignAuthorization(
        authorization_id="auth-approved",
        request_id=request.request_id,
        advisory_id="eaglecrat-advisory-1",
        decision="authorized",
        authority="Sovereign OS",
        decided_at="2026-07-25T21:00:00Z",
        rationale="Mission is authorized under sovereign doctrine.",
        conditions=["Preserve full decision provenance"],
        ledger_commit_ref="sov-ledger:mission:0001",
    )

    mission = SovereignGovernanceGate().create_mission(candidate, request, authorization)

    assert mission.state == "accepted"
    assert mission.authorization_id == authorization.authorization_id
    assert mission.ledger_commit_ref == "sov-ledger:mission:0001"


def test_core_mutation_is_blocked_without_sovereign_authorization() -> None:
    candidate = _candidate()
    base_request = GovernanceRequest.from_candidate(candidate)
    request = GovernanceRequest(
        **{
            **base_request.to_dict(),
            "requested_action": "mutate_cybernetic_core",
            "affects_cybernetic_core": True,
        }
    )
    authorization = SovereignAuthorization(
        authorization_id="auth-denied",
        request_id=request.request_id,
        advisory_id=None,
        decision="denied",
        authority="Sovereign OS",
        decided_at="2026-07-25T21:00:00Z",
        rationale="Unauthorized core mutation.",
    )

    with pytest.raises(PermissionError, match="core mutation"):
        SovereignGovernanceGate().authorize_core_mutation(request, authorization)
