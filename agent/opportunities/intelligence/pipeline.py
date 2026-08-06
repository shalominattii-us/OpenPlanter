from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..domain import EvidencePacket, MissionCandidate, Opportunity, to_primitive
from .contracts import (
    CommercializationDecision,
    IntelligencePluginTrace,
    IntelligenceStage,
    MaturityDecision,
    OpportunityIntelligenceOutput,
    SourceVerificationResult,
    StrategicIntelligenceScore,
)
from .plugin import OpportunityIntelligenceContext
from .plugins import (
    CommercializationRoutingPlugin,
    MaturityOutputPlugin,
    SourceVerificationPlugin,
    StrategicIntelligencePlugin,
)
from .policy import sha256_json
from .registry import OpportunityIntelligencePluginRegistry


@dataclass(frozen=True)
class OpportunityIntelligencePipeline:
    registry: OpportunityIntelligencePluginRegistry

    @classmethod
    def default(cls) -> OpportunityIntelligencePipeline:
        registry = OpportunityIntelligencePluginRegistry()
        registry.register(SourceVerificationPlugin())
        registry.register(StrategicIntelligencePlugin())
        registry.register(CommercializationRoutingPlugin())
        registry.register(MaturityOutputPlugin())
        return cls(registry=registry)

    def run(
        self,
        opportunity: Opportunity,
        evidence_packet: EvidencePacket,
        mission_candidate: MissionCandidate,
        *,
        evaluated_at: datetime | None = None,
    ) -> OpportunityIntelligenceOutput:
        evaluated = evaluated_at or datetime.now(timezone.utc)
        context = OpportunityIntelligenceContext(
            opportunity=opportunity,
            evidence_packet=evidence_packet,
            mission_candidate=mission_candidate,
            evaluated_at=evaluated,
        )
        traces: list[IntelligencePluginTrace] = []
        for plugin in self.registry.validated_chain():
            result = plugin.execute(context)
            _validate_stage_output(plugin.stage, result)
            output_hash = sha256_json(to_primitive(result))
            traces.append(
                IntelligencePluginTrace(
                    plugin_id=plugin.plugin_id,
                    plugin_version=plugin.version,
                    stage=plugin.stage,
                    output_hash=output_hash,
                )
            )
            context = context.with_output(plugin.stage, result)

        verification: SourceVerificationResult = context.output(
            IntelligenceStage.SOURCE_VERIFICATION
        )
        strategic: StrategicIntelligenceScore | None = context.output(
            IntelligenceStage.STRATEGIC_INTELLIGENCE
        )
        commercialization: CommercializationDecision = context.output(
            IntelligenceStage.COMMERCIALIZATION_ROUTING
        )
        maturity: MaturityDecision = context.output(IntelligenceStage.MATURITY_OUTPUT)
        safety = {
            "authorization_policy": "human_required",
            "automatic_dispatches": 0,
            "external_actions_executed": 0,
            "treasury_labs_handoffs_executed": 0,
            "output_is_decision_support_only": True,
            "replay_side_effects": False,
        }
        unsigned = {
            "schema_version": "cybercore-opportunity-intelligence-output-v1",
            "opportunity_id": opportunity.opportunity_id,
            "opportunity_version": opportunity.version,
            "evaluated_at": evaluated.isoformat(),
            "evaluation_date": evaluated.date().isoformat(),
            "source_verification": to_primitive(verification),
            "strategic_intelligence": to_primitive(strategic),
            "commercialization": to_primitive(commercialization),
            "maturity": to_primitive(maturity),
            "plugin_trace": [to_primitive(trace) for trace in traces],
            "safety": safety,
            "artifact_hash": None,
        }
        artifact_hash = sha256_json(unsigned)
        return OpportunityIntelligenceOutput(
            opportunity_id=opportunity.opportunity_id,
            opportunity_version=opportunity.version,
            evaluated_at=evaluated,
            evaluation_date=evaluated.date(),
            source_verification=verification,
            strategic_intelligence=strategic,
            commercialization=commercialization,
            maturity=maturity,
            plugin_trace=tuple(traces),
            safety=safety,
            artifact_hash=artifact_hash,
        )


def _validate_stage_output(stage: IntelligenceStage, value: object) -> None:
    expected = {
        IntelligenceStage.SOURCE_VERIFICATION: SourceVerificationResult,
        IntelligenceStage.STRATEGIC_INTELLIGENCE: (StrategicIntelligenceScore, type(None)),
        IntelligenceStage.COMMERCIALIZATION_ROUTING: CommercializationDecision,
        IntelligenceStage.MATURITY_OUTPUT: MaturityDecision,
    }[stage]
    if not isinstance(value, expected):
        name = getattr(expected, "__name__", str(expected))
        raise TypeError(f"intelligence stage {stage.value} returned invalid output; expected {name}")
