from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import IntelligenceStage
from .plugin import OpportunityIntelligencePlugin


class IntelligencePluginRegistrationError(ValueError):
    pass


_REQUIRED_STAGES = (
    IntelligenceStage.SOURCE_VERIFICATION,
    IntelligenceStage.STRATEGIC_INTELLIGENCE,
    IntelligenceStage.COMMERCIALIZATION_ROUTING,
    IntelligenceStage.MATURITY_OUTPUT,
)


@dataclass
class OpportunityIntelligencePluginRegistry:
    """Deterministic registry for the four-stage Cybercore intelligence chain."""

    _plugins: dict[str, OpportunityIntelligencePlugin] = field(default_factory=dict)

    def register(self, plugin: OpportunityIntelligencePlugin) -> None:
        plugin_id = plugin.plugin_id.strip()
        version = plugin.version.strip()
        if not plugin_id or not version:
            raise IntelligencePluginRegistrationError("plugin id and version are required")
        if plugin_id in self._plugins:
            raise IntelligencePluginRegistrationError(
                f"intelligence plugin already registered: {plugin_id}"
            )
        if any(item.stage is plugin.stage for item in self._plugins.values()):
            raise IntelligencePluginRegistrationError(
                f"intelligence stage already registered: {plugin.stage.value}"
            )
        if any(item.order == plugin.order for item in self._plugins.values()):
            raise IntelligencePluginRegistrationError(
                f"intelligence plugin order already registered: {plugin.order}"
            )
        self._plugins[plugin_id] = plugin

    def all(self) -> tuple[OpportunityIntelligencePlugin, ...]:
        return tuple(
            sorted(
                self._plugins.values(),
                key=lambda item: (item.order, item.plugin_id),
            )
        )

    def validated_chain(self) -> tuple[OpportunityIntelligencePlugin, ...]:
        plugins = self.all()
        stages = tuple(plugin.stage for plugin in plugins)
        orders = tuple(plugin.order for plugin in plugins)
        if stages != _REQUIRED_STAGES:
            raise IntelligencePluginRegistrationError(
                "intelligence chain must register source verification, strategic "
                "intelligence, commercialization routing, and maturity output in order"
            )
        if orders != tuple(range(1, len(_REQUIRED_STAGES) + 1)):
            raise IntelligencePluginRegistrationError(
                "intelligence plugin orders must be contiguous from 1 through 4"
            )
        return plugins
