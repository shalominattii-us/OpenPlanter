from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from agent.opportunities import (
    DeterministicExecutionOrchestrator,
    ExecutionEventType,
    ExecutionLifecycle,
    StepStatus,
    UniversalIntakeAdapter,
    build_mission_candidate,
)
from agent.opportunities.runtime import (
    Capability,
    PluginRegistry,
    PluginRuntime,
    ResearchExecutorPlugin,
)


NOW = datetime(2026, 7, 31, 16, 0, tzinfo=timezone.utc)


def build_lifecycle_and_context():
    adapter = UniversalIntakeAdapter(
        source_name="test-source",
        source_url="https://example.test/opportunities",
    )
    record = {
        "external_id": "research-runtime-1",
        "title": "Validate the production executor contract",
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
    context = lifecycle.initialize(opportunity, packet, candidate, occurred_at=NOW)
    return lifecycle, context


def build_runtime() -> PluginRuntime:
    registry = PluginRegistry()
    registry.register(ResearchExecutorPlugin())
    return PluginRuntime(registry)


def test_research_executor_registers_and_routes_by_capability() -> None:
    _, context = build_lifecycle_and_context()
    runtime = build_runtime()
    plugin = runtime.registry.get("research-executor")

    assert plugin.capabilities() == frozenset({Capability.RESEARCH})
    assert plugin.supports(context.execution_plan.steps[0]) is True
    assert plugin.supports(context.execution_plan.steps[1]) is False


def test_runtime_builds_immutable_context_rich_request() -> None:
    _, context = build_lifecycle_and_context()
    runtime = build_runtime()
    step = context.execution_plan.steps[0]
    configuration = {"policy": {"network_access": False}}
    metadata = {"source": {"name": "operator-test"}}

    request = runtime.build_request(
        context,
        step,
        configuration=configuration,
        metadata=metadata,
        trace_id="trace-research-1",
    )

    configuration["policy"]["network_access"] = True
    metadata["source"]["name"] = "mutated"

    assert request.inputs["opportunity_id"] == context.opportunity.opportunity_id
    assert request.metadata["mission_candidate_id"] == context.mission_candidate.mission_candidate_id
    assert request.configuration["policy"]["network_access"] is False
    assert request.metadata["source"]["name"] == "operator-test"
    assert request.trace_id == "trace-research-1"
    with pytest.raises(TypeError):
        request.inputs["title"] = "changed"
    with pytest.raises(FrozenInstanceError):
        request.trace_id = "changed"


def test_research_executor_returns_useful_normalized_result() -> None:
    _, context = build_lifecycle_and_context()
    runtime = build_runtime()
    step = context.execution_plan.steps[0]

    result = runtime.execute(context, step, trace_id="trace-research-2")

    assert result.success is True
    assert result.message == "Opportunity research brief prepared."
    assert result.artifacts[0].name == "validated-opportunity-brief.json"
    assert result.artifacts[0].media_type == "application/json"
    assert result.metrics_map["research.fact_completeness"] == 1.0
    assert result.metrics_map["research.facts_missing"] == 0.0
    assert result.metrics_map["runtime.elapsed_ms"] >= 0
    assert result.metadata_map["brief"]["title"] == context.opportunity.title
    assert result.metadata_map["plugin_id"] == "research-executor"
    assert result.metadata_map["trace_id"] == "trace-research-2"


def test_execution_memory_exposes_completed_steps_without_event_store_access() -> None:
    lifecycle, context = build_lifecycle_and_context()
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    runtime = build_runtime()

    context = orchestrator.start_run(context, actor="operator", occurred_at=NOW)
    first = context.execution_plan.steps[0]
    context = orchestrator.start_step(context, first.step_id, actor="operator", occurred_at=NOW)
    context = orchestrator.complete_step(context, first.step_id, actor="operator", occurred_at=NOW)
    second = context.execution_plan.steps[1]

    request = runtime.build_request(context, second)

    assert len(request.execution_memory.completed_steps) == 1
    assert request.execution_memory.completed_steps[0]["step_id"] == first.step_id
    assert request.execution_memory.variables["execution_plan_id"] == context.execution_plan.execution_plan_id
    with pytest.raises(TypeError):
        request.execution_memory.completed_steps[0]["step_id"] = "changed"


def test_research_result_integrates_without_plugin_specific_orchestrator_logic() -> None:
    lifecycle, context = build_lifecycle_and_context()
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    runtime = build_runtime()
    original_plan = context.execution_plan

    context = orchestrator.start_run(context, actor="operator", occurred_at=NOW)
    step = context.execution_plan.steps[0]
    context = orchestrator.start_step(context, step.step_id, actor="operator", occurred_at=NOW)
    result = runtime.execute(context, step)
    assert result.success is True

    context = orchestrator.complete_step(
        context,
        step.step_id,
        actor="plugin-runtime",
        occurred_at=NOW,
    )

    assert context.execution_plan == original_plan
    assert orchestrator.state(context).step(step.step_id).status == StepStatus.COMPLETED
    assert context.events[-1].event_type == ExecutionEventType.STEP_COMPLETED
    assert all(event.actor != "research-executor" for event in context.events)
