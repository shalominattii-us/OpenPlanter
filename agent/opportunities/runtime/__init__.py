"""Capability-driven plugin runtime for the Universal Execution Engine.

The runtime executes work. The orchestrator owns execution state. Plugins return
information through ExecutionResult and never advance workflow state.
"""

from .capabilities import Capability, required_capabilities
from .deliverable import DeliverableBuilderExecutorPlugin
from .eligibility import EligibilityExecutorPlugin
from .executor import PluginRuntime
from .integration import ExecutionResultIntegrator
from .materialization import ArtifactMaterializer, MaterializedArtifact
from .memory import ExecutionMemory
from .noop import NoOpPlugin
from .offer_design import OfferDesignExecutorPlugin
from .outreach import OutreachPreparationExecutorPlugin
from .plugin import ExecutionPlugin
from .registry import PluginRegistrationError, PluginRegistry, PluginResolutionError
from .request import ExecutionRequest
from .research import ResearchExecutorPlugin
from .result import ExecutionArtifactResult, ExecutionResult
from .routing import route_plugin
from .run_loop import DeterministicRunLoop, ExecutionCheckpoint, ExecutionRunReport
from .service import DeterministicExecutionService
from .submission import ApprovalGatedSubmissionExecutorPlugin

__all__ = [
    "ApprovalGatedSubmissionExecutorPlugin",
    "ArtifactMaterializer",
    "Capability",
    "DeliverableBuilderExecutorPlugin",
    "DeterministicExecutionService",
    "DeterministicRunLoop",
    "EligibilityExecutorPlugin",
    "ExecutionArtifactResult",
    "ExecutionCheckpoint",
    "ExecutionMemory",
    "ExecutionPlugin",
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutionResultIntegrator",
    "ExecutionRunReport",
    "MaterializedArtifact",
    "NoOpPlugin",
    "OfferDesignExecutorPlugin",
    "OutreachPreparationExecutorPlugin",
    "PluginRegistrationError",
    "PluginRegistry",
    "PluginResolutionError",
    "PluginRuntime",
    "ResearchExecutorPlugin",
    "required_capabilities",
    "route_plugin",
]
