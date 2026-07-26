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
from .graph import (
    MISSION_GRAPH_SCHEMA_VERSION,
    MissionGraph,
    MissionGraphEdge,
    MissionGraphNode,
    build_mission_graph,
)
from .integration import (
    ENGINE_VERSION,
    RUN_MANIFEST_SCHEMA_VERSION,
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
from .sources import OpportunitySource, SourceMetadata, collect_normalized

__all__ = [
    "ArtifactSink",
    "DailyIntakeResult",
    "ENGINE_VERSION",
    "EvidenceAssessment",
    "EvidencePacket",
    "IntakeArtifactBundle",
    "JsonDirectoryArtifactSink",
    "MISSION_GRAPH_SCHEMA_VERSION",
    "MissionCandidate",
    "MissionGraph",
    "MissionGraphEdge",
    "MissionGraphNode",
    "Opportunity",
    "OpportunitySource",
    "ProvenanceRecord",
    "QualificationDecision",
    "QualificationPolicy",
    "QualificationStatus",
    "RUN_MANIFEST_SCHEMA_VERSION",
    "SourceMetadata",
    "UniversalDailyIntakeBridge",
    "UniversalIntakeAdapter",
    "build_mission_candidate",
    "build_mission_graph",
    "collect_normalized",
    "to_primitive",
]
