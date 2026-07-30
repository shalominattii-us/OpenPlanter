"""Canonical domain layer for universal opportunity intake and execution."""

from .adapters import SAMGovClient, SAMGovSource, normalize_sam_record
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
from .execution import (
    EXECUTION_PLAN_SCHEMA_VERSION,
    ApprovalRequirement,
    ExecutionPlan,
    ExecutionPlanStatus,
    ExecutionPolicy,
    ExecutionStep,
    ExecutionStepKind,
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
    "ApprovalRequirement",
    "ArtifactSink",
    "DailyIntakeResult",
    "ENGINE_VERSION",
    "EXECUTION_PLAN_SCHEMA_VERSION",
    "EvidenceAssessment",
    "EvidencePacket",
    "ExecutionPlan",
    "ExecutionPlanStatus",
    "ExecutionPolicy",
    "ExecutionStep",
    "ExecutionStepKind",
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
    "SAMGovClient",
    "SAMGovSource",
    "SourceMetadata",
    "UniversalDailyIntakeBridge",
    "UniversalIntakeAdapter",
    "build_mission_candidate",
    "build_mission_graph",
    "collect_normalized",
    "normalize_sam_record",
    "to_primitive",
]
