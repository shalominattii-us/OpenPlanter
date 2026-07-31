from datetime import datetime, timezone

from agent.opportunities import (
    DeterministicExecutionOrchestrator,
    ExecutionLifecycle,
    UniversalIntakeAdapter,
    build_mission_candidate,
)
from agent.opportunities.runtime import (
    EligibilityExecutorPlugin,
    PluginRegistry,
    PluginRuntime,
    ResearchExecutorPlugin,
)


NOW = datetime(2026, 7, 31, 16, 0, tzinfo=timezone.utc)


def build_context():
    adapter = UniversalIntakeAdapter(
        source_name="test-source",
        source_url="https://example.test/opportunities",
    )
    record = {
        "external_id": "eligibility-1",
        "title": "Validate eligibility execution",
        "source": "test-source",
        "jurisdiction": "US",
        "type": "contract",
        "status": "open",
        "issuer": "Example Agency",
        "deadline": "2026-09-15",
        "eligibility": ["US small business", "Active registration"],
        "submission_path": "https://example.test/submit",
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
        opportunity, packet, candidate, occurred_at=NOW
    )


def build_runtime() -> PluginRuntime:
    registry = PluginRegistry()
    registry.register(ResearchExecutorPlugin())
    registry.register(EligibilityExecutorPlugin())
    return PluginRuntime(registry)


def test_eligibility_executor_uses_the_existing_plugin_contract() -> None:
    _, context = build_context()
    step = context.execution_plan.steps[1]
    runtime = build_runtime()

    result = runtime.execute(context, step)

    assert result.success is True
    assert result.metadata_map["plugin_id"] == "eligibility-executor"
    assert result.metadata_map["requirements"] == (
        "US small business",
        "Active registration",
    )
    assert result.metrics_map["eligibility.requirement_count"] == 2.0
    assert result.artifacts[0].name == "eligibility-matrix.json"


def test_eligibility_matrix_marks_unverified_requirements_for_review() -> None:
    _, context = build_context()
    result = build_runtime().execute(context, context.execution_plan.steps[1])
    matrix = result.metadata_map["matrix"]

    assert len(matrix) == 2
    assert all(item["status"] == "requires_evidence" for item in matrix)
    assert all(item["owner"] is None for item in matrix)
    assert result.metadata_map["requires_operator_review"] is True


def test_eligibility_executor_receives_completed_research_through_memory() -> None:
    lifecycle, context = build_context()
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    runtime = build_runtime()

    context = orchestrator.start_run(context, actor="operator", occurred_at=NOW)
    research_step = context.execution_plan.steps[0]
    context = orchestrator.start_step(
        context, research_step.step_id, actor="operator", occurred_at=NOW
    )
    research_result = runtime.execute(context, research_step)
    assert research_result.success is True
    context = orchestrator.complete_step(
        context, research_step.step_id, actor="operator", occurred_at=NOW
    )

    eligibility_step = context.execution_plan.steps[1]
    context = orchestrator.start_step(
        context, eligibility_step.step_id, actor="operator", occurred_at=NOW
    )
    original_events = context.events
    result = runtime.execute(context, eligibility_step)

    assert result.success is True
    assert result.metadata_map["prior_research_completed"] is True
    assert result.metrics_map["eligibility.prior_steps"] == 1.0
    assert context.events == original_events


def test_second_executor_requires_no_runtime_or_orchestrator_special_case() -> None:
    lifecycle, context = build_context()
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    runtime = build_runtime()

    context = orchestrator.start_run(context, actor="operator", occurred_at=NOW)
    research_step = context.execution_plan.steps[0]
    context = orchestrator.start_step(
        context, research_step.step_id, actor="operator", occurred_at=NOW
    )
    context = orchestrator.complete_step(
        context, research_step.step_id, actor="operator", occurred_at=NOW
    )
    eligibility_step = context.execution_plan.steps[1]
    context = orchestrator.start_step(
        context, eligibility_step.step_id, actor="operator", occurred_at=NOW
    )

    result = runtime.execute(context, eligibility_step)
    context = orchestrator.complete_step(
        context, eligibility_step.step_id, actor="operator", occurred_at=NOW
    )

    assert result.success is True
    assert orchestrator.state(context).step(eligibility_step.step_id).status.value == "completed"
