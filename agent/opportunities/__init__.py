"""Canonical domain layer for the Universal Opportunity Intake pipeline."""

from .domain import (
    EvidenceAssessment,
    EvidencePacket,
    MissionCandidate,
    Opportunity,
    ProvenanceRecord,
    QualificationDecision,
    QualificationStatus,
    to_primitive,
)
from .pipeline import (
    QualificationPolicy,
    UniversalIntakeAdapter,
    build_mission_candidate,
)

__all__ = [
    "EvidenceAssessment",
    "EvidencePacket",
    "MissionCandidate",
    "Opportunity",
    "ProvenanceRecord",
    "QualificationDecision",
    "QualificationPolicy",
    "QualificationStatus",
    "UniversalIntakeAdapter",
    "build_mission_candidate",
    "to_primitive",
]
