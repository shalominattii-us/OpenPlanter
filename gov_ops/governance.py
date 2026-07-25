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

    @classmethod
    def from_candidate(
        cls,
        candidate: MissionCandidate,
        *,
        jurisdiction: str = "unspecified",
        risk_profile: dict[str, Any] | None = None,
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
        )

    def to_dict(self) -> dict[str, Any]:
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
    ledger_commit_ref: str | None = None

    def validate(self) -> None:
        if self.decision not in {"authorized", "denied", "deferred"}:
            raise ValueError(f"Unsupported sovereign decision: {self.decision}")
        if self.decision == "authorized" and not self.ledger_commit_ref:
            raise ValueError("Authorized actions require a Sovereign Ledger commit reference")
        if not self.authority.strip():
            raise ValueError("Sovereign authority identity is required")

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

    def create_mission(
        self,
        candidate: MissionCandidate,
        request: GovernanceRequest,
        authorization: SovereignAuthorization,
    ) -> Mission:
        authorization.validate()
        if request.candidate_id != candidate.candidate_id:
            raise ValueError("Governance request does not reference this mission candidate")
        if authorization.request_id != request.request_id:
            raise ValueError("Sovereign authorization does not reference this governance request")
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
        authorization: SovereignAuthorization,
    ) -> None:
        authorization.validate()
        if not request.affects_cybernetic_core:
            raise ValueError("Request is not marked as a cybernetic core mutation")
        if authorization.request_id != request.request_id:
            raise ValueError("Authorization does not reference the mutation request")
        if authorization.decision != "authorized":
            raise PermissionError("Cybernetic core mutation requires sovereign authorization")
