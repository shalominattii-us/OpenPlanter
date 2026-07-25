from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from gov_ops.qualification import MissionCandidate


GovernanceDisposition = Literal[
    "federal_compliant",
    "sovereign_override_eligible",
    "defer",
    "deny",
]
SovereignDecision = Literal["authorized", "denied", "deferred"]
GovernanceEventType = Literal[
    "request_created",
    "eaglecrat_advisory_issued",
    "sovereign_authorization_issued",
    "ledger_commit_recorded",
    "mission_created",
    "core_mutation_authorized",
]


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


@dataclass(frozen=True)
class GovernanceRequest:
    """A request for governed authorization, not an authorization itself.

    Applications may formulate intent and context, but they may not create a
    mission or mutate the cybernetic core. Those actions require a sovereign
    authorization record.
    """

    request_id: str
    candidate_id: str
    opportunity_id: str
    decision_id: str
    intent: str
    context: dict[str, Any] = field(default_factory=dict)
    jurisdiction: str = "unspecified"
    risk_profile: dict[str, Any] = field(default_factory=dict)
    requested_action: str = "accept_mission"
    affects_cybernetic_core: bool = False
    principle_refs: list[str] = field(default_factory=list)
    provenance_refs: list[str] = field(default_factory=list)

    @classmethod
    def from_candidate(
        cls,
        candidate: MissionCandidate,
        *,
        jurisdiction: str = "unspecified",
        risk_profile: dict[str, Any] | None = None,
        principle_refs: list[str] | None = None,
        provenance_refs: list[str] | None = None,
    ) -> "GovernanceRequest":
        return cls(
            request_id=_stable_id("agx-governance-request", candidate.candidate_id),
            candidate_id=candidate.candidate_id,
            opportunity_id=candidate.opportunity_id,
            decision_id=candidate.decision_id,
            intent=candidate.objective,
            context={
                "title": candidate.title,
                "required_capabilities": list(candidate.required_capabilities),
                "constraints": dict(candidate.constraints),
            },
            jurisdiction=jurisdiction,
            risk_profile=dict(risk_profile or {}),
            principle_refs=list(principle_refs or []),
            provenance_refs=list(provenance_refs or []),
        )

    def validate(self) -> None:
        if not self.request_id.strip():
            raise ValueError("Governance request identity is required")
        if not self.intent.strip():
            raise ValueError("Governance request intent is required")
        if self.affects_cybernetic_core and not self.principle_refs:
            raise ValueError("Core mutation requests require constitutional principle references")
        if self.affects_cybernetic_core and not self.provenance_refs:
            raise ValueError("Core mutation requests require provenance references")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class CoreMutationProposal:
    """A bounded proposal for changing the constitutional or cybernetic core."""

    proposal_id: str
    request_id: str
    component: str
    current_version: str
    proposed_version: str
    change_summary: str
    evidence_refs: list[str]
    principle_refs: list[str]
    rollback_plan: str
    validation_plan: str

    def validate(self) -> None:
        if not self.component.strip():
            raise ValueError("Core mutation component is required")
        if self.current_version == self.proposed_version:
            raise ValueError("Core mutation must propose a distinct version")
        if not self.evidence_refs:
            raise ValueError("Core mutation requires evidence references")
        if not self.principle_refs:
            raise ValueError("Core mutation requires constitutional principle references")
        if not self.rollback_plan.strip():
            raise ValueError("Core mutation requires a rollback plan")
        if not self.validation_plan.strip():
            raise ValueError("Core mutation requires a validation plan")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class EagleCratAdvisory:
    """Regulatory and policy evaluation supplied to sovereign authority.

    EagleCrat can identify a compliant route or an override-eligible route, but
    this advisory is not itself sovereign authorization.
    """

    advisory_id: str
    request_id: str
    disposition: GovernanceDisposition
    rationale: str
    compliance_flags: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    policy_refs: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if self.disposition not in {
            "federal_compliant",
            "sovereign_override_eligible",
            "defer",
            "deny",
        }:
            raise ValueError(f"Unsupported EagleCrat disposition: {self.disposition}")
        if not self.rationale.strip():
            raise ValueError("EagleCrat advisory rationale is required")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class SovereignAuthorization:
    """Final authorization issued by the Sovereign OS authority boundary."""

    authorization_id: str
    request_id: str
    advisory_id: str | None
    decision: SovereignDecision
    authority: str
    decided_at: str
    rationale: str
    conditions: list[str] = field(default_factory=list)
    principle_refs: list[str] = field(default_factory=list)
    ledger_commit_ref: str | None = None

    def validate(self) -> None:
        if self.decision not in {"authorized", "denied", "deferred"}:
            raise ValueError(f"Unsupported sovereign decision: {self.decision}")
        if self.decision == "authorized" and not self.ledger_commit_ref:
            raise ValueError("Authorized actions require a Sovereign Ledger commit reference")
        if self.decision == "authorized" and not self.principle_refs:
            raise ValueError("Authorized actions require governing principle references")
        if not self.authority.strip():
            raise ValueError("Sovereign authority identity is required")
        if not self.rationale.strip():
            raise ValueError("Sovereign authorization rationale is required")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class GovernanceEvent:
    """Immutable event preserving the causal governance chain."""

    event_id: str
    event_type: GovernanceEventType
    occurred_at: str
    actor: str
    request_id: str
    subject_id: str
    parent_event_id: str | None = None
    advisory_id: str | None = None
    authorization_id: str | None = None
    ledger_commit_ref: str | None = None
    principle_refs: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        *,
        event_type: GovernanceEventType,
        occurred_at: str,
        actor: str,
        request_id: str,
        subject_id: str,
        parent_event_id: str | None = None,
        advisory_id: str | None = None,
        authorization_id: str | None = None,
        ledger_commit_ref: str | None = None,
        principle_refs: list[str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> "GovernanceEvent":
        identity_material = "|".join(
            [event_type, request_id, subject_id, parent_event_id or "root"]
        )
        return cls(
            event_id=_stable_id("agx-governance-event", identity_material),
            event_type=event_type,
            occurred_at=occurred_at,
            actor=actor,
            request_id=request_id,
            subject_id=subject_id,
            parent_event_id=parent_event_id,
            advisory_id=advisory_id,
            authorization_id=authorization_id,
            ledger_commit_ref=ledger_commit_ref,
            principle_refs=list(principle_refs or []),
            payload=dict(payload or {}),
        )

    def validate(self) -> None:
        if not self.actor.strip():
            raise ValueError("Governance event actor is required")
        if self.event_type in {
            "sovereign_authorization_issued",
            "ledger_commit_recorded",
            "mission_created",
            "core_mutation_authorized",
        } and not self.principle_refs:
            raise ValueError("Consequential governance events require principle references")
        if self.event_type in {
            "ledger_commit_recorded",
            "mission_created",
            "core_mutation_authorized",
        } and not self.ledger_commit_ref:
            raise ValueError("Committed governance events require a ledger reference")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class Mission:
    """A mission created only after sovereign authorization."""

    mission_id: str
    candidate_id: str
    governance_request_id: str
    authorization_id: str
    ledger_commit_ref: str
    title: str
    objective: str
    state: str = "accepted"
    constraints: dict[str, Any] = field(default_factory=dict)
    required_capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SovereignGovernanceGate:
    """Enforce the authority hierarchy at mission and core-mutation boundaries."""

    @staticmethod
    def _validate_lineage(
        request: GovernanceRequest,
        advisory: EagleCratAdvisory | None,
        authorization: SovereignAuthorization,
    ) -> None:
        request.validate()
        authorization.validate()
        if authorization.request_id != request.request_id:
            raise ValueError("Sovereign authorization does not reference this governance request")
        if advisory is not None:
            advisory.validate()
            if advisory.request_id != request.request_id:
                raise ValueError("EagleCrat advisory does not reference this governance request")
            if authorization.advisory_id != advisory.advisory_id:
                raise ValueError("Sovereign authorization does not reference the supplied advisory")
        elif authorization.advisory_id is not None:
            raise ValueError("Authorization references an advisory that was not supplied")

    def create_mission(
        self,
        candidate: MissionCandidate,
        request: GovernanceRequest,
        authorization: SovereignAuthorization,
        advisory: EagleCratAdvisory | None = None,
    ) -> Mission:
        self._validate_lineage(request, advisory, authorization)
        if request.candidate_id != candidate.candidate_id:
            raise ValueError("Governance request does not reference this mission candidate")
        if authorization.decision != "authorized":
            raise PermissionError("Mission creation requires sovereign authorization")
        if request.affects_cybernetic_core:
            raise PermissionError("Core mutation requests require the dedicated core-mutation path")

        return Mission(
            mission_id=_stable_id("agx-msn", candidate.candidate_id),
            candidate_id=candidate.candidate_id,
            governance_request_id=request.request_id,
            authorization_id=authorization.authorization_id,
            ledger_commit_ref=authorization.ledger_commit_ref or "",
            title=candidate.title,
            objective=candidate.objective,
            constraints=dict(candidate.constraints),
            required_capabilities=list(candidate.required_capabilities),
        )

    def authorize_core_mutation(
        self,
        request: GovernanceRequest,
        proposal: CoreMutationProposal,
        authorization: SovereignAuthorization,
        advisory: EagleCratAdvisory | None = None,
    ) -> GovernanceEvent:
        self._validate_lineage(request, advisory, authorization)
        proposal.validate()
        if not request.affects_cybernetic_core:
            raise ValueError("Request is not marked as a cybernetic core mutation")
        if proposal.request_id != request.request_id:
            raise ValueError("Core mutation proposal does not reference this governance request")
        if authorization.decision != "authorized":
            raise PermissionError("Cybernetic core mutation requires sovereign authorization")

        return GovernanceEvent.build(
            event_type="core_mutation_authorized",
            occurred_at=authorization.decided_at,
            actor=authorization.authority,
            request_id=request.request_id,
            subject_id=proposal.proposal_id,
            advisory_id=authorization.advisory_id,
            authorization_id=authorization.authorization_id,
            ledger_commit_ref=authorization.ledger_commit_ref,
            principle_refs=authorization.principle_refs,
            payload={
                "component": proposal.component,
                "current_version": proposal.current_version,
                "proposed_version": proposal.proposed_version,
                "validation_plan": proposal.validation_plan,
                "rollback_plan": proposal.rollback_plan,
            },
        )
