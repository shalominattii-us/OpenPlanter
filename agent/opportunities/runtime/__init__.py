"""Capability-driven plugin runtime for the Universal Execution Engine.

The runtime executes work. The orchestrator owns execution state. Plugins return
information through ExecutionResult and never advance workflow state.
"""

from .capabilities import Capability, required_capabilities
from .executor import PluginRuntime
from .memory import ExecutionMemory
from .noop import NoOpPlugin
from .plugin import ExecutionPlugin
from .registry import PluginRegistrationError, PluginRegistry, PluginResolutionError
from .request import ExecutionRequest
from .result import ExecutionArtifactResult, ExecutionResult
from .routing import route_plugin

__all__ = [
    "Capability",
    "ExecutionArtifactResult",
    "ExecutionMemory",
    "ExecutionPlugin",
    "ExecutionRequest",
    "ExecutionResult",
    "NoOpPlugin",
    "PluginRegistrationError",
    "PluginRegistry",
    "PluginResolutionError",
    "PluginRuntime",
    "required_capabilities",
    "route_plugin",
]
