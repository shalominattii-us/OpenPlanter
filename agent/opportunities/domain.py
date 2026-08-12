from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Mapping, Sequence


class QualificationStatus(str, Enum):
    QUALIFIED = "qualified"
    REVIEW = "review"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ProvenanceRecord:
    source_name: str
    source_url: str
    retrieved_at: datetime
    source_record_id: str | None = None
    content_hash: str | None = None

    def __post_init__(self) -> None:
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        if not self.source_name.strip():
            raise ValueError("source_name is required")
        if not self.source_url.strip():
            raise ValueError("source_url is required")


@dataclass(frozen=True)
class Opportunity:
    opportunity_id: str
    title: str
    source: str
    jurisdiction: str
    opportunity_type: str
    status: str
    version: int
    provenance: ProvenanceRecord
    issuer: str | None = None
    external_id: str | None = None
    published_date: date | None = None
    deadline: date | None = None
    eligibility: tuple[str, ...] = ()
    sectors: tuple[str, ...] = ()
    amount_min: float | None = None
    amount_max: float | None = None
    currency: str = "USD"
    submission_path: str | None = None
    attachments: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.opportunity_id.strip():
            raise ValueError("opportunity_id is required")
        if not self.title.strip():
            raise ValueError("title is required")
        if self.version < 1:
            raise ValueError("version must be >= 1")
        if self.amount_min is not None and self.amount_min < 0:
            raise ValueError("amount_min must be non-negative")
        if self.amount_max is not None and self.amount_max < 0:
            raise ValueError("amount_max must be non-negative")
        if self.amount_min is not None and self.amount_max is not None:
            if self.amount_min > self.amount_max:
                raise ValueError("amount_min cannot exceed amount_max")

    @classmethod
    def create(
        cls,
        *,
        title: str,
        source: str,
        jurisdiction: str,
        opportunity_type: str,
        status: str,
        provenance: ProvenanceRecord,
        external_id: str | None = None,
        version: int = 1,
        **kwargs: Any,
    ) -> "Opportunity":
        stable_key = "|".join(
            [source.strip().lower(), (external_id or title).strip().lower()]
        )
        opportunity_id = f"opp_{sha256(stable_key.encode('utf-8')).hexdigest()[:20]}"
        return cls(
            opportunity_id=opportunity_id,
            title=title,
            source=source,
            jurisdiction=jurisdiction,
            opportunity_type=opportunity_type,
            status=status,
            version=version,
            provenance=provenance,
            external_id=external_id,
            **kwargs,
        )


@dataclass(frozen=True)
class EvidenceAssessment:
    dimension: str
    score: float
    confidence: float
    rationale: tuple[str, ...] = ()
    facts: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("score must be between 0 and 1")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not self.dimension.strip():
            raise ValueError("dimension is required")


@dataclass(frozen=True)
class EvidencePacket:
    evidence_packet_id: str
    opportunity_id: str
    opportunity_version: int
    version: int
    created_at: datetime
    assessments: tuple[EvidenceAssessment, ...]
    provenance: tuple[ProvenanceRecord, ...]
    recommendations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if self.version < 1:
            raise ValueError("version must be >= 1")
        dimensions = [item.dimension for item in self.assessments]
        if len(dimensions) != len(set(dimensions)):
            raise ValueError("assessment dimensions must be unique")

    @classmethod
    def create(
        cls,
        *,
        opportunity: Opportunity,
        assessments: Sequence[EvidenceAssessment],
        provenance: Sequence[ProvenanceRecord] | None = None,
        recommendations: Sequence[str] = (),
        version: int = 1,
        created_at: datetime | None = None,
    ) -> "EvidencePacket":
        created = created_at or datetime.now(timezone.utc)
        digest_input = f"{opportunity.opportunity_id}|{opportunity.version}|{version}"
        packet_id = f"evp_{sha256(digest_input.encode('utf-8')).hexdigest()[:20]}"
        return cls(
            evidence_packet_id=packet_id,
            opportunity_id=opportunity.opportunity_id,
            opportunity_version=opportunity.version,
            version=version,
            created_at=created,
            assessments=tuple(assessments),
            provenance=tuple(provenance or (opportunity.provenance,)),
            recommendations=tuple(recommendations),
        )

    def score_for(self, dimension: str) -> float | None:
        for assessment in self.assessments:
            if assessment.dimension == dimension:
                return assessment.score
        return None

    @property
    def confidence(self) -> float:
        if not self.assessments:
            return 0.0
        return sum(item.confidence for item in self.assessments) / len(self.assessments)


@dataclass(frozen=True)
class QualificationDecision:
    status: QualificationStatus
    score: float
    reasons: tuple[str, ...]
    rule_version: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("score must be between 0 and 1")


@dataclass(frozen=True)
class MissionCandidate:
    mission_candidate_id: str
    opportunity_id: str
    opportunity_version: int
    evidence_packet_id: str
    evidence_packet_version: int
    created_at: datetime
    decision: QualificationDecision

    @classmethod
    def create(
        cls,
        *,
        opportunity: Opportunity,
        evidence_packet: EvidencePacket,
        decision: QualificationDecision,
        created_at: datetime | None = None,
    ) -> "MissionCandidate":
        if evidence_packet.opportunity_id != opportunity.opportunity_id:
            raise ValueError("evidence packet does not belong to opportunity")
        if evidence_packet.opportunity_version != opportunity.version:
            raise ValueError("evidence packet references another opportunity version")
        digest_input = (
            f"{opportunity.opportunity_id}|{evidence_packet.evidence_packet_id}|"
            f"{decision.rule_version}"
        )
        candidate_id = f"mic_{sha256(digest_input.encode('utf-8')).hexdigest()[:20]}"
        return cls(
            mission_candidate_id=candidate_id,
            opportunity_id=opportunity.opportunity_id,
            opportunity_version=opportunity.version,
            evidence_packet_id=evidence_packet.evidence_packet_id,
            evidence_packet_version=evidence_packet.version,
            created_at=created_at or datetime.now(timezone.utc),
            decision=decision,
        )


def to_primitive(value: Any) -> Any:
    """Convert immutable domain objects into JSON-compatible primitives."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_primitive(item) for item in value]
    return value
