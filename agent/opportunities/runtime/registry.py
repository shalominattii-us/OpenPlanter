from __future__ import annotations

from dataclasses import dataclass, field

from .capabilities import Capability
from .plugin import ExecutionPlugin


class PluginRegistrationError(ValueError):
    pass


class PluginResolutionError(LookupError):
    pass


@dataclass
class PluginRegistry:
    """Explicit, deterministic registry for execution plugins."""

    _plugins: dict[str, ExecutionPlugin] = field(default_factory=dict)

    def register(self, plugin: ExecutionPlugin) -> None:
        plugin_id = plugin.plugin_id.strip()
        if not plugin_id:
            raise PluginRegistrationError("plugin_id is required")
        if not plugin.version.strip():
            raise PluginRegistrationError("plugin version is required")
        if plugin_id in self._plugins:
            raise PluginRegistrationError(f"plugin already registered: {plugin_id}")
        self._plugins[plugin_id] = plugin

    def unregister(self, plugin_id: str) -> ExecutionPlugin:
        try:
            return self._plugins.pop(plugin_id)
        except KeyError as exc:
            raise PluginResolutionError(f"unknown plugin: {plugin_id}") from exc

    def get(self, plugin_id: str) -> ExecutionPlugin:
        try:
            return self._plugins[plugin_id]
        except KeyError as exc:
            raise PluginResolutionError(f"unknown plugin: {plugin_id}") from exc

    def all(self) -> tuple[ExecutionPlugin, ...]:
        return tuple(self._plugins[key] for key in sorted(self._plugins))

    def matching(self, required: frozenset[Capability]) -> tuple[ExecutionPlugin, ...]:
        return tuple(
            plugin
            for plugin in self.all()
            if required.issubset(plugin.capabilities())
        )
