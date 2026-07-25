from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Iterable

from gov_ops.opportunity import Opportunity


_REQUIRED_EVIDENCE_FIELDS = (
    "agency",
    "due_date",
    "description",
    "urls",
)


@dataclass(frozen=True)
class EvidencePackage:
    """Structured, additive evidence derived from an immutable opportunity."""

    evidence_id: str
    opportunity_id: str
    observed_at: str
    missing_fields: list[str] = field(default_factory=list)
    completeness: float = 0.0
    days_until_due: int | None = None
    deadline_state: str = "unknown"
    source_confidence: float = 1.0
    facts: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionRecord:
    """Persistable outcome of a consequential qualification decision."""

    decision_id: str
    opportunity_id: str
    evidence_id: str
    decided_at: str
    outcome: str
    score: float
    confidence: float
    rationale: str
    alternatives_considered: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    policy_version: str = "gov-ops-qualification-v0.1"

    def validate(self) -> None:
        if self.outcome not in {"mission_candidate", "operator_review", "rejected"}:
            raise ValueError(f"Unsupported decision outcome: {self.outcome}")
        for name, value in (("score", self.score), ("confidence", self.confidence)):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True)
class MissionCandidate:
    """A qualified proposal for work, distinct from an accepted mission."""

    candidate_id: str
    opportunity_id: str
    evidence_id: str
    decision_id: str
    title: str
    objective: str
    state: str = "candidate"
    required_capabilities: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QualificationResult:
    evidence: EvidencePackage
    decision: DecisionRecord
    mission_candidate: MissionCandidate | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence": self.evidence.to_dict(),
            "decision": self.decision.to_dict(),
            "mission_candidate": (
                self.mission_candidate.to_dict() if self.mission_candidate else None
            ),
        }


def _stable_id(prefix: str, opportunity_id: str) -> str:
    digest = hashlib.sha256(opportunity_id.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


class EvidenceBuilder:
    """Build deterministic evidence without mutating the source opportunity."""

    def build(
        self,
        opportunity: Opportunity,
        *,
        observed_at: datetime | None = None,
    ) -> EvidencePackage:
        opportunity.validate()
        timestamp = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        missing_fields = [
            name for name in _REQUIRED_EVIDENCE_FIELDS if not getattr(opportunity, name)
        ]
        completeness = round(
            (_REQUIRED_EVIDENCE_FIELDS.__len__() - len(missing_fields))
            / _REQUIRED_EVIDENCE_FIELDS.__len__(),
            3,
        )

        due = _parse_date(opportunity.due_date)
        days_until_due = (due - timestamp.date()).days if due else None
        if days_until_due is None:
            deadline_state = "unknown"
        elif days_until_due < 0:
            deadline_state = "expired"
        elif days_until_due <= 7:
            deadline_state = "critical"
        elif days_until_due <= 30:
            deadline_state = "near"
        else:
            deadline_state = "open"

        facts = {
            "agency": opportunity.agency,
            "office": opportunity.office,
            "solicitation_number": opportunity.solicitation_number,
            "notice_type": opportunity.notice_type,
            "posted_date": opportunity.posted_date,
            "due_date": opportunity.due_date,
            "naics": list(opportunity.naics),
            "psc": opportunity.psc,
            "set_aside": opportunity.set_aside,
            "attachment_count": len(opportunity.attachments),
            "has_contact": bool(opportunity.contact),
            "source": opportunity.source,
            "source_record_id": opportunity.source_record_id,
        }

        return EvidencePackage(
            evidence_id=_stable_id("agx-evidence", opportunity.opportunity_id),
            opportunity_id=opportunity.opportunity_id,
            observed_at=timestamp.isoformat().replace("+00:00", "Z"),
            missing_fields=missing_fields,
            completeness=completeness,
            days_until_due=days_until_due,
            deadline_state=deadline_state,
            facts=facts,
        )


class QualificationEngine:
    """Apply transparent v0.1 policy to evidence and produce a durable decision."""

    def __init__(
        self,
        *,
        candidate_threshold: float = 0.65,
        review_threshold: float = 0.4,
    ) -> None:
        if not 0.0 <= review_threshold <= candidate_threshold <= 1.0:
            raise ValueError("Thresholds must satisfy 0 <= review <= candidate <= 1")
        self.candidate_threshold = candidate_threshold
        self.review_threshold = review_threshold

    def qualify(
        self,
        opportunity: Opportunity,
        *,
        observed_at: datetime | None = None,
    ) -> QualificationResult:
        evidence = EvidenceBuilder().build(opportunity, observed_at=observed_at)
        reasons: list[str] = []

        score = evidence.completeness * 0.65
        if opportunity.agency:
            score += 0.1
        if opportunity.naics or opportunity.psc:
            score += 0.1
        if opportunity.attachments:
            score += 0.05
        if evidence.deadline_state == "open":
            score += 0.1
        elif evidence.deadline_state == "near":
            score += 0.05
        elif evidence.deadline_state == "critical":
            reasons.append("Deadline is within seven days")
        elif evidence.deadline_state == "expired":
            reasons.append("Opportunity deadline has passed")
            score = 0.0
        elif evidence.deadline_state == "unknown":
            reasons.append("Due date is missing or invalid")

        score = round(max(0.0, min(score, 1.0)), 3)
        confidence = round(0.5 + (evidence.completeness * 0.5), 3)

        if evidence.deadline_state == "expired":
            outcome = "rejected"
        elif score >= self.candidate_threshold:
            outcome = "mission_candidate"
        elif score >= self.review_threshold:
            outcome = "operator_review"
        else:
            outcome = "rejected"

        if evidence.missing_fields:
            reasons.append(f"Missing evidence: {', '.join(evidence.missing_fields)}")

        rationale = {
            "mission_candidate": "Evidence clears the deterministic mission-candidate threshold.",
            "operator_review": "Evidence is promising but requires operator judgment before mission creation.",
            "rejected": "Evidence does not justify mission creation under the current policy.",
        }[outcome]

        decided_at = evidence.observed_at
        decision = DecisionRecord(
            decision_id=_stable_id("agx-decision", opportunity.opportunity_id),
            opportunity_id=opportunity.opportunity_id,
            evidence_id=evidence.evidence_id,
            decided_at=decided_at,
            outcome=outcome,
            score=score,
            confidence=confidence,
            rationale=rationale,
            alternatives_considered=[
                value
                for value in ("mission_candidate", "operator_review", "rejected")
                if value != outcome
            ],
            reasons=reasons,
        )

        mission_candidate = None
        if outcome == "mission_candidate":
            mission_candidate = MissionCandidate(
                candidate_id=_stable_id("agx-msn-candidate", opportunity.opportunity_id),
                opportunity_id=opportunity.opportunity_id,
                evidence_id=evidence.evidence_id,
                decision_id=decision.decision_id,
                title=opportunity.title,
                objective=f"Evaluate and realize opportunity: {opportunity.title}",
                required_capabilities=[
                    "opportunity-analysis",
                    "requirements-extraction",
                    "delivery-planning",
                ],
                constraints={
                    "due_date": opportunity.due_date,
                    "agency": opportunity.agency,
                    "set_aside": opportunity.set_aside,
                },
            )

        return QualificationResult(
            evidence=evidence,
            decision=decision,
            mission_candidate=mission_candidate,
        )

    def qualify_many(
        self,
        opportunities: Iterable[Opportunity],
        *,
        observed_at: datetime | None = None,
    ) -> list[QualificationResult]:
        return [self.qualify(item, observed_at=observed_at) for item in opportunities]
