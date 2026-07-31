from datetime import datetime, timezone

from agent.opportunities import (
    DeterministicExecutionOrchestrator,
    ExecutionLifecycle,
    ExecutionRunStatus,
    UniversalIntakeAdapter,
    build_mission_candidate,
)
from agent.opportunities.runtime import (
    Capability,
    DeterministicExecutionService,
    DeterministicRunLoop,
    EligibilityExecutorPlugin,
    ExecutionCheckpoint,
    NoOpPlugin,
    PluginRegistry,
    PluginRuntime,
    ResearchExecutorPlugin,
)


NOW = datetime(2026, 7, 31, 19, 0, tzinfo=timezone.utc)


def build_context():
    adapter = UniversalIntakeAdapter(
        source_name="test-source",
        source_url="https://example.test/opportunities",
    )
    record = {
        "external_id": "loop-1",
        "title": "Validate deterministic run loop",
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


def build_loop(lifecycle, *plugins):
    registry = PluginRegistry()
    for plugin in plugins:
        registry.register(plugin)
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    service = DeterministicExecutionService.create(orchestrator, PluginRuntime(registry))
    return DeterministicRunLoop(service), orchestrator


def all_plugins():
    return (
        ResearchExecutorPlugin(),
        EligibilityExecutorPlugin(),
        NoOpPlugin(frozenset({Capability.OFFER_DESIGN}), plugin_id="offer"),
        NoOpPlugin(frozenset({Capability.DOCUMENT}), plugin_id="document"),
        NoOpPlugin(frozenset({Capability.OUTREACH}), plugin_id="outreach"),
        NoOpPlugin(frozenset({Capability.SUBMISSION}), plugin_id="submission"),
        NoOpPlugin(frozenset({Capability.REPORTING}), plugin_id="reporting"),
    )


def test_loop_advances_until_explicit_approval_checkpoint() -> None:
    lifecycle, context = build_context()
    loop, _ = build_loop(lifecycle, *all_plugins())

    report = loop.execute_until_checkpoint(context, actor="engine", occurred_at=NOW)

    assert report.checkpoint == ExecutionCheckpoint.AWAITING_APPROVAL
    assert report.steps_attempted == 6
    assert report.context.execution_run.status == ExecutionRunStatus.AWAITING_APPROVAL
    assert len(report.context.artifacts) == 2
    assert report.events_recorded > 0


def test_loop_resumes_after_approval_and_completes_run() -> None:
    lifecycle, context = build_context()
    loop, orchestrator = build_loop(lifecycle, *all_plugins())
    first = loop.execute_until_checkpoint(context, actor="engine", occurred_at=NOW)
    gated = first.context.execution_plan.steps[5]
    approved = orchestrator.approve_step(
        first.context,
        gated.step_id,
        actor="approver",
        occurred_at=NOW,
    )

    report = loop.execute_until_checkpoint(approved, actor="engine", occurred_at=NOW)

    assert report.checkpoint == ExecutionCheckpoint.COMPLETED
    assert report.context.execution_run.status == ExecutionRunStatus.COMPLETED
    assert report.steps_attempted == 2


def test_loop_stops_at_step_limit_without_bypassing_state() -> None:
    lifecycle, context = build_context()
    loop, _ = build_loop(lifecycle, *all_plugins())

    report = loop.execute_until_checkpoint(
        context,
        actor="engine",
        occurred_at=NOW,
        max_steps=2,
    )

    assert report.checkpoint == ExecutionCheckpoint.STEP_LIMIT_REACHED
    assert report.steps_attempted == 2
    assert report.context.execution_run.status == ExecutionRunStatus.RUNNING


def test_loop_reports_authoritative_failure_checkpoint() -> None:
    lifecycle, context = build_context()
    loop, _ = build_loop(lifecycle)

    report = loop.execute_until_checkpoint(context, actor="engine", occurred_at=NOW)

    assert report.checkpoint == ExecutionCheckpoint.FAILED
    assert report.steps_attempted == 1
    assert report.context.execution_run.status == ExecutionRunStatus.FAILED
