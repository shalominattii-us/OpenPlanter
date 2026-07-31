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
    DeliverableBuilderExecutorPlugin,
    DeterministicExecutionService,
    EligibilityExecutorPlugin,
    OfferDesignExecutorPlugin,
    PluginRegistry,
    PluginRuntime,
    ResearchExecutorPlugin,
)


NOW = datetime(2026, 7, 31, 23, 0, tzinfo=timezone.utc)


def build_context():
    adapter = UniversalIntakeAdapter(
        source_name="test-source",
        source_url="https://example.test/opportunities",
    )
    record = {
        "external_id": "deliverable-1",
        "title": "Build a cyber resilience response package",
        "source": "test-source",
        "jurisdiction": "US",
        "type": "contract",
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
    registry.register(DeliverableBuilderExecutorPlugin())
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    return DeterministicExecutionService.create(
        orchestrator,
        PluginRuntime(registry),
        artifact_root=artifact_root,
    )


def advance_four(service, context):
    current = context
    for _ in range(4):
        current = service.execute_next_step(current, actor="engine", occurred_at=NOW)
    return current


def payload(context, name):
    artifact = next(item for item in context.artifacts if item.name == name)
    path = Path(artifact.uri.removeprefix("file://"))
    return path.read_text(encoding="utf-8"), artifact


def test_deliverable_builder_routes_through_existing_contract(tmp_path) -> None:
    lifecycle, context = build_context()
    completed = advance_four(build_service(lifecycle, tmp_path / "artifacts"), context)

    names = {item.name for item in completed.artifacts}
    assert {
        "proposal-draft.md",
        "implementation-plan.json",
        "budget-assumptions.json",
    }.issubset(names)
    assert completed.execution_plan.steps[3].kind.value == "build_deliverable"


def test_deliverable_builder_produces_reviewable_nonbinding_package(tmp_path) -> None:
    lifecycle, context = build_context()
    completed = advance_four(build_service(lifecycle, tmp_path / "artifacts"), context)

    proposal, _ = payload(completed, "proposal-draft.md")
    plan_text, _ = payload(completed, "implementation-plan.json")
    budget_text, _ = payload(completed, "budget-assumptions.json")
    plan = json.loads(plan_text)
    budget = json.loads(budget_text)

    assert "Not submitted. Not contractually binding." in proposal
    assert plan["schema_version"] == "universal-implementation-plan-v1"
    assert len(plan["phases"]) == 3
    assert plan["governance"]["external_submission"] == "explicit_approval_required"
    assert budget["pricing_status"] == "requires_operator_review"
    assert budget["committed_amount"] is None


def test_deliverable_builder_consumes_all_prior_artifacts(tmp_path) -> None:
    lifecycle, context = build_context()
    completed = advance_four(build_service(lifecycle, tmp_path / "artifacts"), context)
    step = completed.execution_plan.steps[3]
    event = next(
        item for item in reversed(completed.events)
        if item.step_id == step.step_id and item.event_type.value == "step_completed"
    )

    assert event.details["metrics"]["deliverable.source_artifacts"] == 4.0
    assert event.details["metrics"]["deliverable.output_count"] == 3.0
    assert event.details["result_metadata"]["external_action_performed"] is False


def test_deliverable_files_are_deterministic_and_checksummed(tmp_path) -> None:
    lifecycle_a, context_a = build_context()
    first = advance_four(build_service(lifecycle_a, tmp_path / "a"), context_a)
    lifecycle_b, context_b = build_context()
    second = advance_four(build_service(lifecycle_b, tmp_path / "b"), context_b)

    for name in (
        "proposal-draft.md",
        "implementation-plan.json",
        "budget-assumptions.json",
    ):
        text_a, artifact_a = payload(first, name)
        text_b, artifact_b = payload(second, name)
        assert text_a == text_b
        assert artifact_a.checksum_sha256 == artifact_b.checksum_sha256
        assert artifact_a.metadata["materialized"] is True
        assert artifact_b.metadata["materialized"] is True
