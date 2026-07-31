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


NOW = datetime(2026, 7, 31, 4, 30, tzinfo=timezone.utc)


def build_context():
    adapter = UniversalIntakeAdapter(
        source_name="test-source",
        source_url="https://example.test/opportunities",
    )
    record = {
        "external_id": "orchestrator-1",
        "title": "Build an execution orchestration pilot",
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


def test_run_and_first_step_transition_deterministically() -> None:
    lifecycle, context = build_context()
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)

    context = orchestrator.start_run(context, actor="operator", occurred_at=NOW)
    first = context.execution_plan.steps[0]
    context = orchestrator.start_step(context, first.step_id, actor="operator", occurred_at=NOW)

    state = orchestrator.state(context)
    assert context.execution_run.status == ExecutionRunStatus.RUNNING
    assert state.step(first.step_id).status == StepStatus.RUNNING
    assert context.events[-1].event_type == ExecutionEventType.STEP_STARTED


def test_steps_cannot_start_out_of_order() -> None:
    lifecycle, context = build_context()
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    context = orchestrator.start_run(context, actor="operator", occurred_at=NOW)

    with pytest.raises(ValueError, match="deterministic plan order|dependencies"):
        orchestrator.start_step(
            context,
            context.execution_plan.steps[1].step_id,
            actor="operator",
            occurred_at=NOW,
        )


def test_explicit_approval_gate_pauses_then_resumes_execution() -> None:
    lifecycle, context = build_context()
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    context = orchestrator.start_run(context, actor="operator", occurred_at=NOW)

    for step in context.execution_plan.steps[:-2]:
        context = orchestrator.start_step(context, step.step_id, actor="operator", occurred_at=NOW)
        context = orchestrator.complete_step(context, step.step_id, actor="operator", occurred_at=NOW)

    gated = context.execution_plan.steps[-2]
    context = orchestrator.start_step(context, gated.step_id, actor="operator", occurred_at=NOW)
    assert context.execution_run.status == ExecutionRunStatus.AWAITING_APPROVAL
    assert orchestrator.state(context).step(gated.step_id).status == StepStatus.AWAITING_APPROVAL

    context = orchestrator.approve_step(context, gated.step_id, actor="approver", occurred_at=NOW)
    assert context.execution_run.status == ExecutionRunStatus.RUNNING
    assert orchestrator.state(context).step(gated.step_id).status == StepStatus.RUNNING


def test_step_failure_fails_run_and_replays_reason() -> None:
    lifecycle, context = build_context()
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    context = orchestrator.start_run(context, actor="operator", occurred_at=NOW)
    step = context.execution_plan.steps[0]
    context = orchestrator.start_step(context, step.step_id, actor="operator", occurred_at=NOW)
    context = orchestrator.fail_step(
        context,
        step.step_id,
        actor="operator",
        reason="executor unavailable",
        occurred_at=NOW,
    )

    state = orchestrator.state(context)
    assert context.execution_run.status == ExecutionRunStatus.FAILED
    assert state.step(step.step_id).status == StepStatus.FAILED
    assert state.step(step.step_id).failure_reason == "executor unavailable"
    assert context.events[-1].event_type == ExecutionEventType.RUN_FAILED


def test_completing_all_steps_completes_run() -> None:
    lifecycle, context = build_context()
    orchestrator = DeterministicExecutionOrchestrator(lifecycle)
    context = orchestrator.start_run(context, actor="operator", occurred_at=NOW)

    for step in context.execution_plan.steps:
        context = orchestrator.start_step(context, step.step_id, actor="operator", occurred_at=NOW)
        if orchestrator.state(context).step(step.step_id).status == StepStatus.AWAITING_APPROVAL:
            context = orchestrator.approve_step(
                context, step.step_id, actor="approver", occurred_at=NOW
            )
        context = orchestrator.complete_step(context, step.step_id, actor="operator", occurred_at=NOW)

    assert context.execution_run.status == ExecutionRunStatus.COMPLETED
    assert all(
        state.status == StepStatus.COMPLETED
        for state in orchestrator.state(context).steps
    )
    assert context.events[-1].event_type == ExecutionEventType.RUN_COMPLETED
