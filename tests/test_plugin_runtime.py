from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from agent.opportunities import (
    ExecutionLifecycle,
    UniversalIntakeAdapter,
    build_mission_candidate,
)
from agent.opportunities.runtime import (
    Capability,
    ExecutionResult,
    NoOpPlugin,
    PluginRegistrationError,
    PluginRegistry,
    PluginResolutionError,
    PluginRuntime,
    route_plugin,
)


NOW = datetime(2026, 7, 31, 14, 0, tzinfo=timezone.utc)


def build_context():
    adapter = UniversalIntakeAdapter(
        source_name="test-source",
        source_url="https://example.test/opportunities",
    )
    record = {
        "external_id": "runtime-1",
        "title": "Validate plugin runtime",
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
    return lifecycle.initialize(opportunity, packet, candidate, occurred_at=NOW)


def test_registry_rejects_duplicate_plugin_ids() -> None:
    registry = PluginRegistry()
    registry.register(NoOpPlugin(frozenset({Capability.RESEARCH})))

    with pytest.raises(PluginRegistrationError, match="already registered"):
        registry.register(NoOpPlugin(frozenset({Capability.RESEARCH})))


def test_registry_order_is_deterministic() -> None:
    registry = PluginRegistry()
    registry.register(
        NoOpPlugin(frozenset({Capability.RESEARCH}), plugin_id="zeta")
    )
    registry.register(
        NoOpPlugin(frozenset({Capability.RESEARCH}), plugin_id="alpha")
    )

    assert [plugin.plugin_id for plugin in registry.all()] == ["alpha", "zeta"]


def test_router_resolves_exactly_one_supporting_plugin() -> None:
    context = build_context()
    step = context.execution_plan.steps[0]
    registry = PluginRegistry()
    plugin = NoOpPlugin(frozenset({Capability.RESEARCH}))
    registry.register(plugin)

    assert route_plugin(registry, step) is plugin


def test_router_rejects_missing_and_ambiguous_plugins() -> None:
    context = build_context()
    step = context.execution_plan.steps[0]

    with pytest.raises(PluginResolutionError, match="no plugin"):
        route_plugin(PluginRegistry(), step)

    registry = PluginRegistry()
    registry.register(
        NoOpPlugin(frozenset({Capability.RESEARCH}), plugin_id="first")
    )
    registry.register(
        NoOpPlugin(frozenset({Capability.RESEARCH}), plugin_id="second")
    )
    with pytest.raises(PluginResolutionError, match="ambiguous"):
        route_plugin(registry, step)


def test_runtime_executes_plugin_and_preserves_context() -> None:
    context = build_context()
    original_events = context.events
    step = context.execution_plan.steps[0]
    registry = PluginRegistry()
    registry.register(NoOpPlugin(frozenset({Capability.RESEARCH})))

    result = PluginRuntime(registry).execute(context, step)

    assert result.success is True
    assert result.metadata_map["plugin_id"] == "noop"
    assert result.metadata_map["step_id"] == step.step_id
    assert result.metrics_map["runtime.elapsed_ms"] >= 0
    assert context.events == original_events


def test_execution_result_is_frozen_and_normalized() -> None:
    result = ExecutionResult.succeeded(
        metrics={"z": 2.0, "a": 1.0},
        metadata={"z": "last", "a": "first"},
    )

    assert result.metrics == (("a", 1.0), ("z", 2.0))
    assert result.metadata == (("a", "first"), ("z", "last"))
    with pytest.raises(FrozenInstanceError):
        result.success = False
