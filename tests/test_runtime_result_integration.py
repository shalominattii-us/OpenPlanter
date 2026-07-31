from datetime import datetime, timezone

import pytest

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
    EligibilityExecutorPlugin,
    ExecutionResult,
    ExecutionResultIntegrator,
    PluginRegistry,
    PluginRuntime,
    ResearchExecutorPlugin,
)


NOW = datetime(2026, 7, 31, 17, 0, tzinfo=timezone.utc)


def build_context():
    adapter = UniversalIntakeAdapter(
        source_name="test-source",
        source_url="https://example.test/opportunities",
    )
    record = {
        "external_id": "result-integration-1",
        "title": "Validate result integration",
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
    context = lifecycle.initialize(opportunity, packet, candidate, occurred_at=NOW)
    return lifecycle, context


def build_runtime():
    registry = PluginRegistry()
    registry.register(ResearchExecutorPlugin())
    registry.register(EligibilityExecutorPlugin())
    return PluginRuntime(registry)


def test_successful_result_records_artifacts_then_completes_step() -> None:
    lifecycle, context = build_context()
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    runtime = build_runtime()
    integrator = ExecutionResultIntegrator(orchestrator)

    context = orchestrator.start_run(context, actor="operator", occurred_at=NOW)
    step = context.execution_plan.steps[0]
    context = orchestrator.start_step(context, step.step_id, actor="operator", occurred_at=NOW)
    result = runtime.execute(context, step, trace_id="trace-research")
    context = integrator.apply(context, step, result, actor="runtime", occurred_at=NOW)

    artifacts = lifecycle.store.artifacts_for_run(context.execution_run.execution_run_id)
    assert len(artifacts) == 1
    assert artifacts[0].name == "validated-opportunity-brief.json"
    assert artifacts[0].step_id == step.step_id
    assert orchestrator.state(context).step(step.step_id).status == StepStatus.COMPLETED
    event_types = [event.event_type for event in context.events]
    assert event_types.index(ExecutionEventType.ARTIFACT_RECORDED) < event_types.index(
        ExecutionEventType.STEP_COMPLETED
    )


def test_unsuccessful_result_fails_step_and_run_without_artifacts() -> None:
    lifecycle, context = build_context()
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    integrator = ExecutionResultIntegrator(orchestrator)

    context = orchestrator.start_run(context, actor="operator", occurred_at=NOW)
    step = context.execution_plan.steps[0]
    context = orchestrator.start_step(context, step.step_id, actor="operator", occurred_at=NOW)
    context = integrator.apply(
        context,
        step,
        ExecutionResult.failed(message="research source unavailable"),
        actor="runtime",
        occurred_at=NOW,
    )

    assert orchestrator.state(context).step(step.step_id).status == StepStatus.FAILED
    assert context.execution_run.status == ExecutionRunStatus.FAILED
    assert lifecycle.store.artifacts_for_run(context.execution_run.execution_run_id) == ()


def test_result_cannot_be_applied_before_step_is_running() -> None:
    lifecycle, context = build_context()
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    integrator = ExecutionResultIntegrator(orchestrator)
    step = context.execution_plan.steps[0]

    with pytest.raises(ValueError, match="step must be running"):
        integrator.apply(
            context,
            step,
            ExecutionResult.succeeded(message="not authoritative"),
            actor="runtime",
            occurred_at=NOW,
        )


def test_completed_result_becomes_memory_for_next_executor() -> None:
    lifecycle, context = build_context()
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    runtime = build_runtime()
    integrator = ExecutionResultIntegrator(orchestrator)

    context = orchestrator.start_run(context, actor="operator", occurred_at=NOW)
    research = context.execution_plan.steps[0]
    context = orchestrator.start_step(context, research.step_id, actor="operator", occurred_at=NOW)
    result = runtime.execute(context, research)
    context = integrator.apply(context, research, result, actor="runtime", occurred_at=NOW)

    eligibility = context.execution_plan.steps[1]
    context = orchestrator.start_step(context, eligibility.step_id, actor="operator", occurred_at=NOW)
    request = runtime.build_request(context, eligibility)

    assert len(request.execution_memory.completed_steps) == 1
    details = request.execution_memory.completed_steps[0]["details"]
    assert details["artifact_ids"]
    assert details["result_metadata"]["plugin_id"] == "research-executor"
