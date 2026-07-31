from __future__ import annotations

from ..execution import ExecutionStep
from .capabilities import required_capabilities
from .plugin import ExecutionPlugin
from .registry import PluginRegistry, PluginResolutionError


def route_plugin(registry: PluginRegistry, step: ExecutionStep) -> ExecutionPlugin:
    """Resolve exactly one supporting plugin for a step.

    Zero or multiple matches are explicit configuration errors. The runtime never
    guesses, ranks, or silently selects among ambiguous executors.
    """

    required = required_capabilities(step.kind)
    matches = tuple(
        plugin
        for plugin in registry.matching(required)
        if plugin.supports(step)
    )
    if not matches:
        names = ", ".join(sorted(capability.value for capability in required))
        raise PluginResolutionError(
            f"no plugin supports step {step.step_id} with capabilities: {names}"
        )
    if len(matches) > 1:
        plugin_ids = ", ".join(plugin.plugin_id for plugin in matches)
        raise PluginResolutionError(
            f"ambiguous plugins for step {step.step_id}: {plugin_ids}"
        )
    return matches[0]
