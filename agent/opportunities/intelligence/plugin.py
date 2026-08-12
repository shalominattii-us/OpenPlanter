from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from types import MappingProxyType
from typing import Any, Protocol, TypeVar, runtime_checkable

from ..domain import EvidencePacket, MissionCandidate, Opportunity
from .contracts import IntelligenceStage

StageResult = TypeVar("StageResult")


@dataclass(frozen=True)
class OpportunityIntelligenceContext:
    """Immutable information passed between pure intelligence plugins."""

    opportunity: Opportunity
    evidence_packet: EvidencePacket
    mission_candidate: MissionCandidate
    evaluated_at: datetime
    stage_outputs: Mapping[IntelligenceStage, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at must be timezone-aware")
        if self.evidence_packet.opportunity_id != self.opportunity.opportunity_id:
            raise ValueError("evidence packet does not belong to opportunity")
        if self.mission_candidate.opportunity_id != self.opportunity.opportunity_id:
            raise ValueError("mission candidate does not belong to opportunity")
        object.__setattr__(
            self,
            "stage_outputs",
            MappingProxyType(dict(self.stage_outputs)),
        )

    def output(self, stage: IntelligenceStage) -> Any:
        try:
            return self.stage_outputs[stage]
        except KeyError as exc:
            raise RuntimeError(f"intelligence stage has not completed: {stage.value}") from exc

    def with_output(self, stage: IntelligenceStage, result: StageResult) -> OpportunityIntelligenceContext:
        if stage in self.stage_outputs:
            raise RuntimeError(f"intelligence stage already completed: {stage.value}")
        updated = dict(self.stage_outputs)
        updated[stage] = result
        return replace(self, stage_outputs=updated)


@runtime_checkable
class OpportunityIntelligencePlugin(Protocol):
    """Pure stage plugin for the pre-execution opportunity intelligence chain."""

    plugin_id: str
    version: str
    stage: IntelligenceStage
    order: int

    def execute(self, context: OpportunityIntelligenceContext) -> Any:
        ...
