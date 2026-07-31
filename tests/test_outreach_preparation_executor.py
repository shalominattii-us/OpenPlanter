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
    OutreachPreparationExecutorPlugin,
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
        "external_id": "outreach-1",
        "title": "Prepare a cyber resilience response",
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
    registry.register(DeliverableBuilderExecutorPlugin())
    registry.register(OutreachPreparationExecutorPlugin())
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    return DeterministicExecutionService.create(
        orchestrator,
        PluginRuntime(registry),
        artifact_root=artifact_root,
    )


def advance_five(service, context):
    current = context
    for _ in range(5):
        current = service.execute_next_step(current, actor="engine", occurred_at=NOW)
    return current


def artifact(context, name):
    item = next(value for value in context.artifacts if value.name == name)
    path = Path(item.uri.removeprefix("file://"))
    return item, path


def test_outreach_routes_without_runtime_or_orchestrator_special_case(tmp_path) -> None:
    lifecycle, context = build_context()
    completed = advance_five(build_service(lifecycle, tmp_path / "artifacts"), context)

    names = {item.name for item in completed.artifacts}
    assert {"outreach-draft.md", "submission-checklist.md", "contact-brief.json"} <= names
    assert len(completed.artifacts) == 10
    assert completed.execution_plan.steps[4].kind.value == "prepare_outreach"


def test_outreach_materials_are_reviewable_and_never_sent(tmp_path) -> None:
    lifecycle, context = build_context()
    completed = advance_five(build_service(lifecycle, tmp_path / "artifacts"), context)

    _, outreach_path = artifact(completed, "outreach-draft.md")
    _, checklist_path = artifact(completed, "submission-checklist.md")
    _, brief_path = artifact(completed, "contact-brief.json")
    outreach = outreach_path.read_text(encoding="utf-8")
    checklist = checklist_path.read_text(encoding="utf-8")
    brief = json.loads(brief_path.read_text(encoding="utf-8"))

    assert "Status: Draft only. Not sent." in outreach
    assert "explicit approval" in checklist.lower()
    assert brief["review_status"] == "requires_operator_review"
    assert brief["external_action_performed"] is False


def test_outreach_consumes_completed_response_package(tmp_path) -> None:
    lifecycle, context = build_context()
    completed = advance_five(build_service(lifecycle, tmp_path / "artifacts"), context)

    completed_event = next(
        event
        for event in reversed(completed.events)
        if event.step_id == completed.execution_plan.steps[4].step_id
        and event.event_type.value == "step_completed"
    )
    source_artifacts = completed_event.details["result_metadata"]["source_artifacts"]
    assert "proposal-draft.md" in source_artifacts
    assert "implementation-plan.json" in source_artifacts
    assert "budget-assumptions.json" in source_artifacts
    assert completed_event.details["metrics"]["outreach.external_actions"] == 0.0


def test_outreach_files_are_deterministic_and_checksummed(tmp_path) -> None:
    lifecycle_a, context_a = build_context()
    first = advance_five(build_service(lifecycle_a, tmp_path / "a"), context_a)
    lifecycle_b, context_b = build_context()
    second = advance_five(build_service(lifecycle_b, tmp_path / "b"), context_b)

    for name in ("outreach-draft.md", "submission-checklist.md", "contact-brief.json"):
        artifact_a, path_a = artifact(first, name)
        artifact_b, path_b = artifact(second, name)
        assert path_a.read_bytes() == path_b.read_bytes()
        assert artifact_a.checksum_sha256 == artifact_b.checksum_sha256
        assert artifact_a.metadata["materialized"] is True
        assert artifact_b.metadata["materialized"] is True
