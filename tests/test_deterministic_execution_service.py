from datetime import datetime, timezone

from agent.opportunities import (
    DeterministicExecutionOrchestrator,
    ExecutionEventType,
    ExecutionLifecycle,
    ExecutionRunStatus,
    StepStatus,
    UniversalIntakeAdapter,
    build_mission_candidate,
)
from agent.opportunities.runtime import (
    Capability,
    DeterministicExecutionService,
    EligibilityExecutorPlugin,
    NoOpPlugin,
    PluginRegistry,
    PluginRuntime,
    ResearchExecutorPlugin,
)


NOW = datetime(2026, 7, 31, 18, 0, tzinfo=timezone.utc)


def build_context():
    adapter = UniversalIntakeAdapter(
        source_name="test-source",
        source_url="https://example.test/opportunities",
    )
    record = {
        "external_id": "service-1",
        "title": "Validate deterministic execution service",
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
    return lifecycle, lifecycle.initialize(
        opportunity,
        packet,
        candidate,
        occurred_at=NOW,
    )


def build_service(lifecycle, *plugins):
    registry = PluginRegistry()
    for plugin in plugins:
        registry.register(plugin)
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    return (
        DeterministicExecutionService.create(
            orchestrator,
            PluginRuntime(registry),
        ),
        orchestrator,
    )


def test_service_starts_run_executes_research_and_records_result() -> None:
    lifecycle, context = build_context()
    service, orchestrator = build_service(lifecycle, ResearchExecutorPlugin())

    context = service.execute_next_step(context, actor="engine", occurred_at=NOW)
    first = context.execution_plan.steps[0]
    artifacts = lifecycle.store.artifacts_for_run(
        context.execution_run.execution_run_id
    )

    assert context.execution_run.status == ExecutionRunStatus.RUNNING
    assert orchestrator.state(context).step(first.step_id).status == StepStatus.COMPLETED
    assert [event.event_type for event in context.events[-3:]] == [
        ExecutionEventType.STEP_STARTED,
        ExecutionEventType.ARTIFACT_RECORDED,
        ExecutionEventType.STEP_COMPLETED,
    ]
    assert artifacts[0].name == "validated-opportunity-brief.json"


def test_service_executes_next_plugin_with_prior_memory() -> None:
    lifecycle, context = build_context()
    service, orchestrator = build_service(
        lifecycle,
        ResearchExecutorPlugin(),
        EligibilityExecutorPlugin(),
    )

    context = service.execute_next_step(context, actor="engine", occurred_at=NOW)
    context = service.execute_next_step(context, actor="engine", occurred_at=NOW)
    second = context.execution_plan.steps[1]
    completion = next(
        event
        for event in reversed(context.events)
        if event.event_type == ExecutionEventType.STEP_COMPLETED
        and event.step_id == second.step_id
    )
    artifacts = lifecycle.store.artifacts_for_run(
        context.execution_run.execution_run_id
    )

    assert orchestrator.state(context).step(second.step_id).status == StepStatus.COMPLETED
    assert completion.details["result_metadata"]["prior_research_completed"] is True
    assert {artifact.name for artifact in artifacts} == {
        "validated-opportunity-brief.json",
        "eligibility-matrix.json",
    }


def test_service_stops_before_explicit_approval_without_dispatching() -> None:
    lifecycle, context = build_context()
    service, orchestrator = build_service(
        lifecycle,
        ResearchExecutorPlugin(),
        EligibilityExecutorPlugin(),
        NoOpPlugin(frozenset({Capability.OFFER_DESIGN}), plugin_id="offer"),
        NoOpPlugin(frozenset({Capability.DOCUMENT}), plugin_id="document"),
        NoOpPlugin(frozenset({Capability.OUTREACH}), plugin_id="outreach"),
        NoOpPlugin(frozenset({Capability.SUBMISSION}), plugin_id="submission"),
    )

    for _ in range(6):
        context = service.execute_next_step(context, actor="engine", occurred_at=NOW)

    gated = context.execution_plan.steps[5]
    state = orchestrator.state(context)
    assert context.execution_run.status == ExecutionRunStatus.AWAITING_APPROVAL
    assert state.step(gated.step_id).status == StepStatus.AWAITING_APPROVAL
    assert not any(
        event.event_type in {
            ExecutionEventType.STEP_COMPLETED,
            ExecutionEventType.STEP_FAILED,
        }
        and event.step_id == gated.step_id
        for event in context.events
    )


def test_service_converts_runtime_exception_into_authoritative_failure() -> None:
    lifecycle, context = build_context()
    service, orchestrator = build_service(lifecycle)

    context = service.execute_next_step(context, actor="engine", occurred_at=NOW)
    first = context.execution_plan.steps[0]

    assert context.execution_run.status == ExecutionRunStatus.FAILED
    assert orchestrator.state(context).step(first.step_id).status == StepStatus.FAILED
    assert "PluginResolutionError" in orchestrator.state(context).step(first.step_id).failure_reason
    assert context.events[-1].event_type == ExecutionEventType.RUN_FAILED
