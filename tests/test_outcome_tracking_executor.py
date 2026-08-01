import json
from datetime import datetime, timezone
from pathlib import Path

from agent.opportunities import (
    DeterministicExecutionOrchestrator,
    ExecutionLifecycle,
    ExecutionRunStatus,
    UniversalIntakeAdapter,
    build_mission_candidate,
)
from agent.opportunities.runtime import (
    ApprovalGatedSubmissionExecutorPlugin,
    DeliverableBuilderExecutorPlugin,
    DeterministicExecutionService,
    EligibilityExecutorPlugin,
    OfferDesignExecutorPlugin,
    OutcomeTrackingExecutorPlugin,
    OutreachPreparationExecutorPlugin,
    PluginRegistry,
    PluginRuntime,
    ResearchExecutorPlugin,
)


NOW = datetime(2026, 7, 31, 23, 50, tzinfo=timezone.utc)


def build_context():
    adapter = UniversalIntakeAdapter(
        source_name="test-source",
        source_url="https://example.test/opportunities",
    )
    record = {
        "external_id": "outcome-1",
        "title": "Complete a deterministic opportunity lifecycle",
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
    registry.register(ApprovalGatedSubmissionExecutorPlugin())
    registry.register(OutcomeTrackingExecutorPlugin())
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    service = DeterministicExecutionService.create(
        orchestrator,
        PluginRuntime(registry),
        artifact_root=artifact_root,
    )
    return service, orchestrator


def complete_lifecycle(service, orchestrator, context):
    current = context
    for _ in range(5):
        current = service.execute_next_step(current, actor="engine", occurred_at=NOW)
    gated = service.execute_next_step(current, actor="engine", occurred_at=NOW)
    submit_step = gated.execution_plan.steps[5]
    approved = orchestrator.approve_step(
        gated,
        submit_step.step_id,
        actor="approver",
        occurred_at=NOW,
    )
    submitted = service.execute_next_step(approved, actor="engine", occurred_at=NOW)
    return service.execute_next_step(submitted, actor="engine", occurred_at=NOW)


def outcome_payload(context):
    artifact = next(item for item in context.artifacts if item.name == "outcome-record.json")
    path = Path(artifact.uri.removeprefix("file://"))
    return artifact, json.loads(path.read_text(encoding="utf-8"))


def test_outcome_tracking_completes_entire_execution_run(tmp_path) -> None:
    lifecycle, context = build_context()
    service, orchestrator = build_service(lifecycle, tmp_path / "artifacts")

    completed = complete_lifecycle(service, orchestrator, context)

    assert completed.execution_run.status == ExecutionRunStatus.COMPLETED
    assert completed.execution_plan.steps[6].kind.value == "track_outcome"
    assert any(item.name == "outcome-record.json" for item in completed.artifacts)
    assert len(completed.artifacts) == 12


def test_outcome_record_is_honest_about_unobserved_external_results(tmp_path) -> None:
    lifecycle, context = build_context()
    service, orchestrator = build_service(lifecycle, tmp_path / "artifacts")
    completed = complete_lifecycle(service, orchestrator, context)

    artifact, payload = outcome_payload(completed)

    assert payload["execution_status"] == "completed"
    assert payload["submission_status"] == "simulated_not_sent"
    assert payload["observed_outcome"] == "awaiting_real_transport_and_external_response"
    assert payload["financial_outcome"]["revenue_recognized"] == 0
    assert payload["financial_outcome"]["award_status"] == "not_observed"
    assert artifact.checksum_sha256


def test_outcome_record_preserves_submission_lineage(tmp_path) -> None:
    lifecycle, context = build_context()
    service, orchestrator = build_service(lifecycle, tmp_path / "artifacts")
    completed = complete_lifecycle(service, orchestrator, context)

    _, payload = outcome_payload(completed)

    assert "submission-receipt.json" in payload["source_artifacts"]
    assert "proposal-draft.md" in payload["source_artifacts"]
    assert "outreach-draft.md" in payload["source_artifacts"]
    assert payload["external_action_performed"] is False


def test_outcome_record_is_deterministic_and_materialized(tmp_path) -> None:
    outcomes = []
    for directory in (tmp_path / "a", tmp_path / "b"):
        lifecycle, context = build_context()
        service, orchestrator = build_service(lifecycle, directory)
        completed = complete_lifecycle(service, orchestrator, context)
        artifact, _ = outcome_payload(completed)
        path = Path(artifact.uri.removeprefix("file://"))
        outcomes.append((path.read_bytes(), artifact.checksum_sha256))

    assert outcomes[0] == outcomes[1]
