from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any

INTELLIGENCE_OUTPUT_SCHEMA_VERSION = "cybercore-opportunity-intelligence-output-v1"


class IntelligenceStage(str, Enum):
    SOURCE_VERIFICATION = "source_verification"
    STRATEGIC_INTELLIGENCE = "strategic_intelligence"
    COMMERCIALIZATION_ROUTING = "commercialization_routing"
    MATURITY_OUTPUT = "maturity_output"


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    NEEDS_SOURCE_VERIFICATION = "NEEDS_SOURCE_VERIFICATION"


class TemporalStatus(str, Enum):
    OPEN = "OPEN"
    DEADLINE_TODAY = "DEADLINE_TODAY"
    CLOSED = "CLOSED"
    FORECAST = "FORECAST"
    PROGRAM_ONLY = "PROGRAM_ONLY"
    UNKNOWN = "UNKNOWN"


class CommercializationStatus(str, Enum):
    READY_FOR_HUMAN_REVIEW = "READY_FOR_HUMAN_REVIEW"
    MONITOR_FORECAST = "MONITOR_FORECAST"
    CLOSED_NO_ACTION = "CLOSED_NO_ACTION"
    PROGRAM_DISCOVERY_ONLY = "PROGRAM_DISCOVERY_ONLY"
    SOURCE_VERIFICATION_REQUIRED = "SOURCE_VERIFICATION_REQUIRED"
    NO_ROUTE_IDENTIFIED = "NO_ROUTE_IDENTIFIED"


class MaturityStage(str, Enum):
    SOURCE_DISCOVERY = "SOURCE_DISCOVERY"
    STRATEGIC_INTELLIGENCE = "STRATEGIC_INTELLIGENCE"
    FORECAST_MONITOR = "FORECAST_MONITOR"
    PROGRAM_DISCOVERY = "PROGRAM_DISCOVERY"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class SourceVerificationResult:
    status: VerificationStatus
    temporal_status: TemporalStatus
    source_authority: str
    source_urls: tuple[str, ...]
    verified_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    evidence_hash: str
    rationale: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.source_authority.strip():
            raise ValueError("source_authority is required")
        if not self.source_urls:
            raise ValueError("at least one source URL is required")
        if len(self.evidence_hash) != 64:
            raise ValueError("evidence_hash must be a SHA-256 hex digest")


@dataclass(frozen=True)
class StrategicIntelligenceScore:
    status: str
    policy_version: str
    methodology: str
    dimensions: Mapping[str, float]
    weights: Mapping[str, float]
    score: float
    recommended_priority: str
    explanation: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status != "SCORED":
            raise ValueError("strategic intelligence status must be SCORED")
        if not 0 <= self.score <= 100:
            raise ValueError("strategic intelligence score must be between 0 and 100")
        if abs(sum(self.weights.values()) - 1.0) > 0.000001:
            raise ValueError("strategic intelligence weights must sum to 1")
        if any(not 0 <= value <= 100 for value in self.dimensions.values()):
            raise ValueError("strategic intelligence dimensions must be between 0 and 100")


@dataclass(frozen=True)
class CommercializationDecision:
    status: CommercializationStatus
    policy_version: str
    candidate_paths: tuple[str, ...]
    primary_path: str | None
    rationale: tuple[str, ...]
    treasury_labs_status: str
    automatic_dispatch: bool = False
    handoff_executed: bool = False

    def __post_init__(self) -> None:
        if self.automatic_dispatch:
            raise ValueError("automatic Treasury Labs dispatch is prohibited")
        if self.handoff_executed:
            raise ValueError("Foundry intelligence cannot execute a Treasury Labs handoff")
        if self.primary_path is not None and self.primary_path not in self.candidate_paths:
            raise ValueError("primary_path must be one of candidate_paths")


@dataclass(frozen=True)
class MaturityDecision:
    stage: MaturityStage
    order: int
    disposition: str
    human_decision_required: bool
    actionable: bool
    reason: str

    def __post_init__(self) -> None:
        if self.order < 1:
            raise ValueError("maturity order must be positive")
        if not self.disposition.strip() or not self.reason.strip():
            raise ValueError("maturity disposition and reason are required")


@dataclass(frozen=True)
class IntelligencePluginTrace:
    plugin_id: str
    plugin_version: str
    stage: IntelligenceStage
    output_hash: str

    def __post_init__(self) -> None:
        if not self.plugin_id.strip() or not self.plugin_version.strip():
            raise ValueError("plugin identity and version are required")
        if len(self.output_hash) != 64:
            raise ValueError("plugin output_hash must be a SHA-256 hex digest")


@dataclass(frozen=True)
class OpportunityIntelligenceOutput:
    opportunity_id: str
    opportunity_version: int
    evaluated_at: datetime
    evaluation_date: date
    source_verification: SourceVerificationResult
    strategic_intelligence: StrategicIntelligenceScore | None
    commercialization: CommercializationDecision
    maturity: MaturityDecision
    plugin_trace: tuple[IntelligencePluginTrace, ...]
    safety: Mapping[str, Any]
    artifact_hash: str
    schema_version: str = field(default=INTELLIGENCE_OUTPUT_SCHEMA_VERSION)

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware")
        if self.opportunity_version < 1:
            raise ValueError("opportunity_version must be at least 1")
        if len(self.plugin_trace) != 4:
            raise ValueError("the Cybercore intelligence chain requires exactly four plugins")
        if len(self.artifact_hash) != 64:
            raise ValueError("artifact_hash must be a SHA-256 hex digest")
        if self.safety.get("automatic_dispatches") != 0:
            raise ValueError("automatic dispatches must remain zero")
        if self.safety.get("external_actions_executed") != 0:
            raise ValueError("external actions must remain zero")
        if self.safety.get("treasury_labs_handoffs_executed") != 0:
            raise ValueError("Treasury Labs handoffs must remain zero")

    def to_primitive(self) -> dict[str, Any]:
        return _primitive(asdict(self))


def _primitive(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_primitive(item) for item in value]
    return value
