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
    OutreachPreparationExecutorPlugin,
    PluginRegistry,
    PluginRuntime,
    ResearchExecutorPlugin,
)


NOW = datetime(2026, 7, 31, 23, 30, tzinfo=timezone.utc)


def build_context():
    adapter = UniversalIntakeAdapter(
        source_name="test-source",
        source_url="https://example.test/opportunities",
    )
    record = {
        "external_id": "submission-1",
        "title": "Validate an approval-gated submission path",
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
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    service = DeterministicExecutionService.create(
        orchestrator,
        PluginRuntime(registry),
        artifact_root=artifact_root,
    )
    return service, orchestrator


def advance_to_submission_gate(service, context):
    current = context
    for _ in range(5):
        current = service.execute_next_step(current, actor="engine", occurred_at=NOW)
    return service.execute_next_step(current, actor="engine", occurred_at=NOW)


def test_submission_does_not_dispatch_before_explicit_approval(tmp_path) -> None:
    lifecycle, context = build_context()
    service, _ = build_service(lifecycle, tmp_path / "artifacts")

    gated = advance_to_submission_gate(service, context)

    assert gated.execution_run.status == ExecutionRunStatus.AWAITING_APPROVAL
    assert all(item.name != "submission-receipt.json" for item in gated.artifacts)
    submit_step = gated.execution_plan.steps[5]
    assert submit_step.kind.value == "submit_response"


def test_approved_submission_produces_local_durable_receipt(tmp_path) -> None:
    lifecycle, context = build_context()
    service, orchestrator = build_service(lifecycle, tmp_path / "artifacts")
    gated = advance_to_submission_gate(service, context)
    submit_step = gated.execution_plan.steps[5]
    approved = orchestrator.approve_step(
        gated,
        submit_step.step_id,
        actor="approver",
        occurred_at=NOW,
    )

    completed = service.execute_next_step(approved, actor="engine", occurred_at=NOW)

    receipt = next(item for item in completed.artifacts if item.name == "submission-receipt.json")
    payload = json.loads(Path(receipt.uri.removeprefix("file://")).read_text(encoding="utf-8"))
    assert payload["submission_status"] == "simulated_not_sent"
    assert payload["external_action_performed"] is False
    assert payload["transport"] == "local_receipt"
    assert receipt.checksum_sha256


def test_submission_receipt_records_approval_boundary_and_source_package(tmp_path) -> None:
    lifecycle, context = build_context()
    service, orchestrator = build_service(lifecycle, tmp_path / "artifacts")
    gated = advance_to_submission_gate(service, context)
    submit_step = gated.execution_plan.steps[5]
    approved = orchestrator.approve_step(
        gated,
        submit_step.step_id,
        actor="approver",
        occurred_at=NOW,
    )
    completed = service.execute_next_step(approved, actor="engine", occurred_at=NOW)

    receipt = next(item for item in completed.artifacts if item.name == "submission-receipt.json")
    payload = json.loads(Path(receipt.uri.removeprefix("file://")).read_text(encoding="utf-8"))
    assert payload["approval_boundary"] == "satisfied_by_orchestrator_before_dispatch"
    assert "outreach-draft.md" in payload["source_artifacts"]
    assert "submission-checklist.md" in payload["source_artifacts"]
    assert "proposal-draft.md" in payload["source_artifacts"]


def test_local_submission_receipt_is_deterministic(tmp_path) -> None:
    receipts = []
    for directory in (tmp_path / "a", tmp_path / "b"):
        lifecycle, context = build_context()
        service, orchestrator = build_service(lifecycle, directory)
        gated = advance_to_submission_gate(service, context)
        submit_step = gated.execution_plan.steps[5]
        approved = orchestrator.approve_step(
            gated,
            submit_step.step_id,
            actor="approver",
            occurred_at=NOW,
        )
        completed = service.execute_next_step(approved, actor="engine", occurred_at=NOW)
        receipt = next(item for item in completed.artifacts if item.name == "submission-receipt.json")
        path = Path(receipt.uri.removeprefix("file://"))
        receipts.append((path.read_bytes(), receipt.checksum_sha256))

    assert receipts[0] == receipts[1]
