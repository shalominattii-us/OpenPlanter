from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent.opportunities import (
    CommercializationStatus,
    IntelligencePluginRegistrationError,
    MaturityStage,
    OpportunityIntelligencePipeline,
    OpportunityIntelligencePluginRegistry,
    SourceVerificationPlugin,
    TemporalStatus,
    UniversalDailyIntakeBridge,
    UniversalIntakeAdapter,
    VerificationStatus,
    build_mission_candidate,
)
from agent.opportunities.intelligence.policy import sha256_json

NOW = datetime(2026, 8, 6, 17, 32, 17, tzinfo=timezone.utc)


def _record(**overrides):
    record = {
        "external_id": "70RDA126R00000099",
        "title": "Maritime Domain Awareness Commercial Solutions Opening",
        "source": "SAM.gov",
        "source_url": "https://sam.gov/opp/example/view",
        "issuer": "U.S. Department of Homeland Security",
        "jurisdiction": "United States",
        "type": "procurement",
        "opportunity_type": "procurement",
        "program_type": "commercial solutions opening",
        "procurement_type": "CSO",
        "market_entry": "technology_partner",
        "status": "open",
        "published_date": "2026-07-20",
        "deadline": "2026-09-30",
        "eligibility": ["SAM.gov registered technology companies"],
        "submission_path": "https://sam.gov/opp/example/view",
        "sectors": ["maritime domain awareness"],
        "sector": "maritime domain awareness",
        "strategic_fit": "Tier 1",
        "strategic_tier": "Tier 1",
        "priority": "P0",
        "revenue_path": "maritime awareness technology prototype",
    }
    record.update(overrides)
    return record


def _domain(record):
    adapter = UniversalIntakeAdapter("SAM.gov", "https://sam.gov/")
    opportunity = adapter.opportunity_from_record(record, retrieved_at=NOW)
    packet = adapter.evidence_from_record(opportunity, record, created_at=NOW)
    candidate = build_mission_candidate(opportunity, packet, created_at=NOW)
    return opportunity, packet, candidate


def test_default_pipeline_registers_exactly_four_ordered_plugins() -> None:
    plugins = OpportunityIntelligencePipeline.default().registry.validated_chain()

    assert [plugin.order for plugin in plugins] == [1, 2, 3, 4]
    assert [plugin.stage.value for plugin in plugins] == [
        "source_verification",
        "strategic_intelligence",
        "commercialization_routing",
        "maturity_output",
    ]


def test_registry_rejects_duplicate_stage_and_incomplete_chain() -> None:
    registry = OpportunityIntelligencePluginRegistry()
    registry.register(SourceVerificationPlugin())

    with pytest.raises(IntelligencePluginRegistrationError, match="already registered"):
        registry.register(SourceVerificationPlugin(plugin_id="another-source-plugin"))
    with pytest.raises(IntelligencePluginRegistrationError, match="must register"):
        registry.validated_chain()


def test_verified_open_record_gets_exact_score_route_and_maturity() -> None:
    opportunity, packet, candidate = _domain(_record())

    output = OpportunityIntelligencePipeline.default().run(
        opportunity,
        packet,
        candidate,
        evaluated_at=NOW,
    )

    assert output.source_verification.status is VerificationStatus.VERIFIED
    assert output.source_verification.temporal_status is TemporalStatus.OPEN
    assert output.strategic_intelligence is not None
    assert output.strategic_intelligence.dimensions == {
        "sector_fit": 95.0,
        "revenue_probability": 90.0,
        "funding_probability": 72.0,
        "implementation_complexity": 62.0,
        "strategic_alignment": 95.0,
    }
    assert output.strategic_intelligence.score == 80.9
    assert output.strategic_intelligence.recommended_priority == "P0"
    assert output.commercialization.status is CommercializationStatus.READY_FOR_HUMAN_REVIEW
    assert output.commercialization.primary_path == "prototype_demonstration"
    assert output.commercialization.automatic_dispatch is False
    assert output.commercialization.handoff_executed is False
    assert output.maturity.stage is MaturityStage.HUMAN_REVIEW
    assert output.maturity.human_decision_required is True
    assert output.maturity.actionable is True
    assert len(output.plugin_trace) == 4

    primitive = output.to_primitive()
    artifact_hash = primitive["artifact_hash"]
    primitive["artifact_hash"] = None
    assert sha256_json(primitive) == artifact_hash


def test_missing_identifier_blocks_scoring_routing_and_execution_context() -> None:
    record = _record(external_id=None, record_id=None)
    bridge = UniversalDailyIntakeBridge(
        adapter=UniversalIntakeAdapter("SAM.gov", "https://sam.gov/"),
        intelligence_pipeline=OpportunityIntelligencePipeline.default(),
    )

    result = bridge.run([record], render_report=lambda records: "ok", generated_at=NOW)
    bundle = result.artifacts[0]
    output = bundle.intelligence_output

    assert output is not None
    assert output.source_verification.status is VerificationStatus.NEEDS_SOURCE_VERIFICATION
    assert output.strategic_intelligence is None
    assert output.commercialization.status is CommercializationStatus.SOURCE_VERIFICATION_REQUIRED
    assert output.maturity.stage is MaturityStage.SOURCE_DISCOVERY
    assert bundle.execution_context is None


def test_closed_record_is_scored_for_history_but_cannot_enter_execution() -> None:
    record = _record(status="closed", deadline="2026-07-31")
    bridge = UniversalDailyIntakeBridge(
        adapter=UniversalIntakeAdapter("SAM.gov", "https://sam.gov/"),
        intelligence_pipeline=OpportunityIntelligencePipeline.default(),
    )

    result = bridge.run([record], render_report=lambda records: "ok", generated_at=NOW)
    bundle = result.artifacts[0]
    output = bundle.intelligence_output

    assert output is not None
    assert output.source_verification.status is VerificationStatus.VERIFIED
    assert output.source_verification.temporal_status is TemporalStatus.CLOSED
    assert output.strategic_intelligence is not None
    assert output.commercialization.status is CommercializationStatus.CLOSED_NO_ACTION
    assert output.maturity.stage is MaturityStage.CLOSED
    assert output.maturity.actionable is False
    assert bundle.execution_context is None
