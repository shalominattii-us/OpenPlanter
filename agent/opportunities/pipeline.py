from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence

from .domain import (
    EvidenceAssessment,
    EvidencePacket,
    MissionCandidate,
    Opportunity,
    ProvenanceRecord,
    QualificationDecision,
    QualificationStatus,
)


_LABEL_SCORES = {
    "very low": 0.10,
    "low": 0.25,
    "low-medium": 0.35,
    "medium-low": 0.40,
    "moderate": 0.50,
    "medium": 0.50,
    "medium-high": 0.70,
    "moderate-high": 0.70,
    "high": 0.85,
    "very high": 0.95,
    "critical": 1.00,
}


def _label_score(value: Any, *, default: float = 0.5) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    if value is None:
        return default
    return _LABEL_SCORES.get(str(value).strip().lower(), default)


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


@dataclass(frozen=True)
class UniversalIntakeAdapter:
    """Translate existing daily-intake records into canonical domain objects.

    The adapter intentionally accepts a loose mapping so the current daily report
    generator can keep its existing source-specific normalization while emitting
    structured artifacts in parallel.
    """

    source_name: str
    source_url: str

    def opportunity_from_record(
        self,
        record: Mapping[str, Any],
        *,
        retrieved_at: datetime | None = None,
    ) -> Opportunity:
        retrieved = retrieved_at or datetime.now(timezone.utc)
        provenance = ProvenanceRecord(
            source_name=self.source_name,
            source_url=str(record.get("source_url") or self.source_url),
            source_record_id=_first(record, "external_id", "identifier", "record_id"),
            retrieved_at=retrieved,
            content_hash=record.get("content_hash"),
        )
        return Opportunity.create(
            title=str(record.get("title") or "Untitled opportunity"),
            source=str(record.get("source") or self.source_name),
            jurisdiction=str(record.get("jurisdiction") or "Unknown"),
            opportunity_type=str(record.get("type") or record.get("opportunity_type") or "Unknown"),
            status=str(record.get("status") or "unknown"),
            provenance=provenance,
            external_id=provenance.source_record_id,
            version=int(record.get("version") or 1),
            issuer=record.get("issuer") or record.get("agency"),
            published_date=_as_date(record.get("published_date") or record.get("posted")),
            deadline=_as_date(record.get("deadline")),
            eligibility=_as_tuple(record.get("eligibility")),
            sectors=_as_tuple(record.get("sectors") or record.get("sector")),
            amount_min=_as_number(record.get("amount_min") or record.get("award_floor")),
            amount_max=_as_number(
                record.get("amount_max")
                or record.get("award_ceiling")
                or record.get("maximum_award")
                or record.get("total_funding")
            ),
            currency=str(record.get("currency") or "USD"),
            submission_path=record.get("submission_path"),
            attachments=_as_tuple(record.get("attachments")),
            metadata=dict(record),
        )

    def evidence_from_record(
        self,
        opportunity: Opportunity,
        record: Mapping[str, Any],
        *,
        created_at: datetime | None = None,
    ) -> EvidencePacket:
        assessments = (
            EvidenceAssessment(
                dimension="strategic_fit",
                score=_label_score(record.get("strategic_fit")),
                confidence=_label_score(record.get("strategic_fit_confidence"), default=0.75),
                rationale=_as_tuple(record.get("strategic_fit_rationale")),
                facts={"label": record.get("strategic_fit")},
            ),
            EvidenceAssessment(
                dimension="urgency",
                score=_label_score(record.get("urgency"), default=_deadline_urgency(opportunity.deadline)),
                confidence=0.90 if opportunity.deadline else 0.55,
                rationale=_as_tuple(record.get("urgency_rationale")),
                facts={"deadline": opportunity.deadline.isoformat() if opportunity.deadline else None},
            ),
            EvidenceAssessment(
                dimension="complexity",
                score=_label_score(record.get("complexity")),
                confidence=_label_score(record.get("complexity_confidence"), default=0.70),
                rationale=_as_tuple(record.get("complexity_rationale")),
                facts={"label": record.get("complexity")},
            ),
            EvidenceAssessment(
                dimension="financial_value",
                score=_financial_score(opportunity.amount_max),
                confidence=0.90 if opportunity.amount_max is not None else 0.45,
                rationale=_as_tuple(record.get("financial_rationale")),
                facts={
                    "amount_min": opportunity.amount_min,
                    "amount_max": opportunity.amount_max,
                    "currency": opportunity.currency,
                    "revenue_path": record.get("revenue_path") or record.get("commercial_path"),
                },
            ),
            EvidenceAssessment(
                dimension="eligibility",
                score=_label_score(record.get("eligibility_fit"), default=0.50),
                confidence=_label_score(record.get("eligibility_confidence"), default=0.65),
                rationale=_as_tuple(record.get("eligibility_rationale")),
                facts={"eligibility": list(opportunity.eligibility)},
            ),
        )
        recommendations = _as_tuple(
            record.get("recommendations")
            or record.get("recommended_classification")
            or record.get("flag")
        )
        return EvidencePacket.create(
            opportunity=opportunity,
            assessments=assessments,
            recommendations=recommendations,
            created_at=created_at,
        )


@dataclass(frozen=True)
class QualificationPolicy:
    rule_version: str = "universal-intake-v1"
    qualify_threshold: float = 0.70
    review_threshold: float = 0.45
    minimum_confidence: float = 0.55

    def decide(self, packet: EvidencePacket) -> QualificationDecision:
        fit = packet.score_for("strategic_fit") or 0.0
        urgency = packet.score_for("urgency") or 0.0
        value = packet.score_for("financial_value") or 0.0
        eligibility = packet.score_for("eligibility") or 0.0
        complexity = packet.score_for("complexity") or 0.0

        score = (
            fit * 0.35
            + urgency * 0.20
            + value * 0.20
            + eligibility * 0.20
            + (1.0 - complexity) * 0.05
        )
        reasons = (
            f"strategic_fit={fit:.2f}",
            f"urgency={urgency:.2f}",
            f"financial_value={value:.2f}",
            f"eligibility={eligibility:.2f}",
            f"complexity={complexity:.2f}",
            f"confidence={packet.confidence:.2f}",
        )

        if packet.confidence < self.minimum_confidence:
            status = QualificationStatus.REVIEW
        elif score >= self.qualify_threshold:
            status = QualificationStatus.QUALIFIED
        elif score >= self.review_threshold:
            status = QualificationStatus.REVIEW
        else:
            status = QualificationStatus.REJECTED

        return QualificationDecision(
            status=status,
            score=round(score, 6),
            reasons=reasons,
            rule_version=self.rule_version,
        )


def build_mission_candidate(
    opportunity: Opportunity,
    packet: EvidencePacket,
    *,
    policy: QualificationPolicy | None = None,
    created_at: datetime | None = None,
) -> MissionCandidate:
    decision = (policy or QualificationPolicy()).decide(packet)
    return MissionCandidate.create(
        opportunity=opportunity,
        evidence_packet=packet,
        decision=decision,
        created_at=created_at,
    )


def _first(record: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _as_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _deadline_urgency(deadline: date | None) -> float:
    if deadline is None:
        return 0.40
    days = (deadline - datetime.now(timezone.utc).date()).days
    if days < 0:
        return 0.0
    if days <= 7:
        return 1.0
    if days <= 30:
        return 0.80
    if days <= 90:
        return 0.60
    return 0.35


def _financial_score(amount_max: float | None) -> float:
    if amount_max is None:
        return 0.50
    if amount_max >= 10_000_000:
        return 1.0
    if amount_max >= 1_000_000:
        return 0.85
    if amount_max >= 250_000:
        return 0.70
    if amount_max >= 50_000:
        return 0.55
    return 0.35
