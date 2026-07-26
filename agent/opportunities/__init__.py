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
from .integration import (
    ArtifactSink,
    DailyIntakeResult,
    IntakeArtifactBundle,
    JsonDirectoryArtifactSink,
    UniversalDailyIntakeBridge,
)
from .pipeline import (
    QualificationPolicy,
    UniversalIntakeAdapter,
    build_mission_candidate,
)

__all__ = [
    "ArtifactSink",
    "DailyIntakeResult",
    "EvidenceAssessment",
    "EvidencePacket",
    "IntakeArtifactBundle",
    "JsonDirectoryArtifactSink",
    "MissionCandidate",
    "Opportunity",
    "ProvenanceRecord",
    "QualificationDecision",
    "QualificationPolicy",
    "QualificationStatus",
    "UniversalDailyIntakeBridge",
    "UniversalIntakeAdapter",
    "build_mission_candidate",
    "to_primitive",
]
