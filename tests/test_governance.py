from __future__ import annotations

import pytest

from gov_ops.governance import (
    CoreMutationProposal,
    EagleCratAdvisory,
    GovernanceEvent,
    GovernanceRequest,
    SovereignAuthorization,
    SovereignGovernanceGate,
)
from gov_ops.opportunity import Opportunity
from gov_ops.qualification import QualificationEngine


PRINCIPLES = ["constitutional-core:v1", "mutation-law:v1"]


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


def _advisory(request: GovernanceRequest) -> EagleCratAdvisory:
    return EagleCratAdvisory(
        advisory_id="eaglecrat-advisory-1",
        request_id=request.request_id,
        disposition="federal_compliant",
        rationale="No regulatory conflict identified for sovereign review.",
        policy_refs=["eaglecrat:mission-review:v1"],
    )


def test_eaglecrat_or_application_cannot_create_mission_without_sovereign_authorization() -> None:
    candidate = _candidate()
    request = GovernanceRequest.from_candidate(candidate)
    advisory = _advisory(request)
    authorization = SovereignAuthorization(
        authorization_id="auth-deferred",
        request_id=request.request_id,
        advisory_id=advisory.advisory_id,
        decision="deferred",
        authority="Sovereign OS",
        decided_at="2026-07-25T21:00:00Z",
        rationale="Awaiting sovereign determination.",
    )

    with pytest.raises(PermissionError, match="sovereign authorization"):
        SovereignGovernanceGate().create_mission(
            candidate, request, authorization, advisory
        )


def test_authorized_mission_requires_ledger_commit() -> None:
    candidate = _candidate()
    request = GovernanceRequest.from_candidate(candidate)
    advisory = _advisory(request)
    authorization = SovereignAuthorization(
        authorization_id="auth-missing-ledger",
        request_id=request.request_id,
        advisory_id=advisory.advisory_id,
        decision="authorized",
        authority="Sovereign OS",
        decided_at="2026-07-25T21:00:00Z",
        rationale="Authorized in principle.",
        principle_refs=PRINCIPLES,
    )

    with pytest.raises(ValueError, match="Ledger commit"):
        SovereignGovernanceGate().create_mission(
            candidate, request, authorization, advisory
        )


def test_sovereign_authorization_creates_mission() -> None:
    candidate = _candidate()
    request = GovernanceRequest.from_candidate(candidate)
    advisory = _advisory(request)
    authorization = SovereignAuthorization(
        authorization_id="auth-approved",
        request_id=request.request_id,
        advisory_id=advisory.advisory_id,
        decision="authorized",
        authority="Sovereign OS",
        decided_at="2026-07-25T21:00:00Z",
        rationale="Mission is authorized under sovereign doctrine.",
        conditions=["Preserve full decision provenance"],
        principle_refs=PRINCIPLES,
        ledger_commit_ref="sov-ledger:mission:0001",
    )

    mission = SovereignGovernanceGate().create_mission(
        candidate, request, authorization, advisory
    )

    assert mission.state == "accepted"
    assert mission.authorization_id == authorization.authorization_id
    assert mission.ledger_commit_ref == "sov-ledger:mission:0001"


def test_authorization_cannot_silently_reference_an_unprovided_advisory() -> None:
    candidate = _candidate()
    request = GovernanceRequest.from_candidate(candidate)
    authorization = SovereignAuthorization(
        authorization_id="auth-approved",
        request_id=request.request_id,
        advisory_id="missing-advisory",
        decision="authorized",
        authority="Sovereign OS",
        decided_at="2026-07-25T21:00:00Z",
        rationale="Authorization references external review.",
        principle_refs=PRINCIPLES,
        ledger_commit_ref="sov-ledger:mission:0002",
    )

    with pytest.raises(ValueError, match="advisory that was not supplied"):
        SovereignGovernanceGate().create_mission(candidate, request, authorization)


def test_core_mutation_request_requires_principles_and_provenance() -> None:
    candidate = _candidate()
    base_request = GovernanceRequest.from_candidate(candidate)
    request = GovernanceRequest(
        **{
            **base_request.to_dict(),
            "requested_action": "mutate_cybernetic_core",
            "affects_cybernetic_core": True,
        }
    )

    with pytest.raises(ValueError, match="principle references"):
        request.validate()


def test_core_mutation_is_blocked_without_sovereign_authorization() -> None:
    candidate = _candidate()
    request = GovernanceRequest.from_candidate(
        candidate,
        principle_refs=PRINCIPLES,
        provenance_refs=["decision:qualification-1", "evidence:package-1"],
    )
    request = GovernanceRequest(
        **{
            **request.to_dict(),
            "requested_action": "mutate_cybernetic_core",
            "affects_cybernetic_core": True,
        }
    )
    proposal = CoreMutationProposal(
        proposal_id="mutation-1",
        request_id=request.request_id,
        component="mission-kernel",
        current_version="0.1",
        proposed_version="0.2",
        change_summary="Introduce a governed mission transition.",
        evidence_refs=["validation:mission-kernel-0.1"],
        principle_refs=PRINCIPLES,
        rollback_plan="Restore mission-kernel 0.1 from the signed release.",
        validation_plan="Replay governance fixtures before activation.",
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
        SovereignGovernanceGate().authorize_core_mutation(
            request, proposal, authorization
        )


def test_authorized_core_mutation_returns_replayable_governance_event() -> None:
    candidate = _candidate()
    request = GovernanceRequest.from_candidate(
        candidate,
        principle_refs=PRINCIPLES,
        provenance_refs=["decision:qualification-1", "evidence:package-1"],
    )
    request = GovernanceRequest(
        **{
            **request.to_dict(),
            "requested_action": "mutate_cybernetic_core",
            "affects_cybernetic_core": True,
        }
    )
    proposal = CoreMutationProposal(
        proposal_id="mutation-1",
        request_id=request.request_id,
        component="mission-kernel",
        current_version="0.1",
        proposed_version="0.2",
        change_summary="Introduce a governed mission transition.",
        evidence_refs=["validation:mission-kernel-0.1"],
        principle_refs=PRINCIPLES,
        rollback_plan="Restore mission-kernel 0.1 from the signed release.",
        validation_plan="Replay governance fixtures before activation.",
    )
    authorization = SovereignAuthorization(
        authorization_id="auth-core-approved",
        request_id=request.request_id,
        advisory_id=None,
        decision="authorized",
        authority="Sovereign OS",
        decided_at="2026-07-25T21:00:00Z",
        rationale="Mutation is authorized under the constitutional change path.",
        principle_refs=PRINCIPLES,
        ledger_commit_ref="sov-ledger:mutation:0001",
    )

    event = SovereignGovernanceGate().authorize_core_mutation(
        request, proposal, authorization
    )

    assert isinstance(event, GovernanceEvent)
    assert event.event_type == "core_mutation_authorized"
    assert event.ledger_commit_ref == "sov-ledger:mutation:0001"
    assert event.principle_refs == PRINCIPLES


def test_governance_event_identity_is_stable() -> None:
    first = GovernanceEvent.build(
        event_type="request_created",
        occurred_at="2026-07-25T21:00:00Z",
        actor="OpenPlanter",
        request_id="request-1",
        subject_id="candidate-1",
    )
    second = GovernanceEvent.build(
        event_type="request_created",
        occurred_at="2026-07-25T22:00:00Z",
        actor="OpenPlanter",
        request_id="request-1",
        subject_id="candidate-1",
    )

    assert first.event_id == second.event_id
