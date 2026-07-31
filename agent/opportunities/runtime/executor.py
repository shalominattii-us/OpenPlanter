from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from ..execution import ExecutionStep
from ..lifecycle import ExecutionContext
from .registry import PluginRegistry
from .result import ExecutionResult
from .routing import route_plugin


@dataclass(frozen=True)
class PluginRuntime:
    """Execute a routed plugin without mutating orchestration state."""

    registry: PluginRegistry

    def execute(
        self,
        context: ExecutionContext,
        step: ExecutionStep,
    ) -> ExecutionResult:
        plugin = route_plugin(self.registry, step)
        started = perf_counter()
        result = plugin.execute(context, step)
        if not isinstance(result, ExecutionResult):
            raise TypeError(
                f"plugin {plugin.plugin_id} returned {type(result).__name__}; "
                "expected ExecutionResult"
            )
        elapsed_ms = (perf_counter() - started) * 1000
        metadata = result.metadata_map
        metadata.update(
            {
                "plugin_id": plugin.plugin_id,
                "plugin_version": plugin.version,
            }
        )
        metrics = result.metrics_map
        metrics.setdefault("runtime.elapsed_ms", elapsed_ms)
        return ExecutionResult(
            success=result.success,
            message=result.message,
            artifacts=result.artifacts,
            metrics=tuple(sorted(metrics.items())),
            metadata=tuple(sorted(metadata.items())),
        )
