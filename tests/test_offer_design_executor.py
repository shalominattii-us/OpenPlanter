import json
from datetime import datetime, timezone
from pathlib import Path

from agent.opportunities import (
    DeterministicExecutionOrchestrator,
    ExecutionLifecycle,
    UniversalIntakeAdapter,
    build_mission_candidate,
)
from agent.opportunities.runtime import (
    DeterministicExecutionService,
    EligibilityExecutorPlugin,
    OfferDesignExecutorPlugin,
    PluginRegistry,
    PluginRuntime,
    ResearchExecutorPlugin,
)


NOW = datetime(2026, 7, 31, 22, 0, tzinfo=timezone.utc)


def build_context():
    adapter = UniversalIntakeAdapter(
        source_name="test-source",
        source_url="https://example.test/opportunities",
    )
    record = {
        "external_id": "offer-design-1",
        "title": "Design a mutually beneficial cyber resilience engagement",
        "source": "test-source",
        "jurisdiction": "US",
        "type": "partnership",
        "status": "open",
        "issuer": "Example Agency",
        "deadline": "2026-09-15",
        "eligibility": ["US small business"],
        "submission_path": "mailto:opportunities@example.test",
        "strategic_fit": "very high",
        "urgency": "high",
        "complexity": "low",
        "eligibility_fit": "very high",
        "amount_max": 500000,
    }
    opportunity = adapter.opportunity_from_record(record, retrieved_at=NOW)
    packet = adapter.evidence_from_record(opportunity, record, created_at=NOW)
    candidate = build_mission_candidate(opportunity, packet, created_at=NOW)
    lifecycle = ExecutionLifecycle.in_memory()
    return lifecycle, lifecycle.initialize(opportunity, packet, candidate, occurred_at=NOW)


def build_service(lifecycle, artifact_root):
    registry = PluginRegistry()
    registry.register(ResearchExecutorPlugin())
    registry.register(EligibilityExecutorPlugin())
    registry.register(OfferDesignExecutorPlugin())
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    return DeterministicExecutionService.create(
        orchestrator,
        PluginRuntime(registry),
        artifact_root=artifact_root,
    )


def advance_three(service, context):
    current = context
    for _ in range(3):
        current = service.execute_next_step(current, actor="engine", occurred_at=NOW)
    return current


def artifact_payload(context, name):
    artifact = next(item for item in context.artifacts if item.name == name)
    path = Path(artifact.uri.removeprefix("file://"))
    return json.loads(path.read_text(encoding="utf-8")), artifact


def test_offer_design_routes_without_runtime_or_orchestrator_special_case(tmp_path) -> None:
    lifecycle, context = build_context()
    completed = advance_three(build_service(lifecycle, tmp_path / "artifacts"), context)

    assert {item.name for item in completed.artifacts} == {
        "validated-opportunity-brief.json",
        "eligibility-matrix.json",
        "offer-design.json",
        "value-model.json",
    }
    assert completed.execution_plan.steps[2].kind.value == "design_offer"


def test_offer_design_produces_mutually_beneficial_reviewable_model(tmp_path) -> None:
    lifecycle, context = build_context()
    completed = advance_three(build_service(lifecycle, tmp_path / "artifacts"), context)

    offer, _ = artifact_payload(completed, "offer-design.json")
    value, _ = artifact_payload(completed, "value-model.json")

    assert offer["schema_version"] == "universal-offer-design-v1"
    assert offer["recipient"] == "Example Agency"
    assert "recipient_outcome" in offer
    assert "provider_outcome" in offer
    assert len(offer["success_criteria"]) == 4
    assert value["commercial_model"]["pricing_status"] == "requires_operator_review"
    assert "recipient_receives" in value["value_exchange"]
    assert "provider_receives" in value["value_exchange"]


def test_offer_design_consumes_research_and_eligibility_memory(tmp_path) -> None:
    lifecycle, context = build_context()
    completed = advance_three(build_service(lifecycle, tmp_path / "artifacts"), context)

    offer, _ = artifact_payload(completed, "offer-design.json")

    assert "validated-opportunity-brief.json" in offer["source_artifacts"]
    assert "eligibility-matrix.json" in offer["source_artifacts"]
    completed_event = next(
        event
        for event in reversed(completed.events)
        if event.step_id == completed.execution_plan.steps[2].step_id
        and event.event_type.value == "step_completed"
    )
    assert completed_event.details["metrics"]["offer.output_count"] == 2.0


def test_offer_design_files_are_deterministic_and_checksummed(tmp_path) -> None:
    lifecycle_a, context_a = build_context()
    first = advance_three(build_service(lifecycle_a, tmp_path / "a"), context_a)
    lifecycle_b, context_b = build_context()
    second = advance_three(build_service(lifecycle_b, tmp_path / "b"), context_b)

    for name in ("offer-design.json", "value-model.json"):
        payload_a, artifact_a = artifact_payload(first, name)
        payload_b, artifact_b = artifact_payload(second, name)
        assert payload_a == payload_b
        assert artifact_a.checksum_sha256 == artifact_b.checksum_sha256
        assert artifact_a.metadata["materialized"] is True
        assert artifact_b.metadata["materialized"] is True
