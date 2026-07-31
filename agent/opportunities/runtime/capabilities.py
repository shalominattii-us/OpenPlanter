from __future__ import annotations

from enum import Enum

from ..execution import ExecutionStepKind


class Capability(str, Enum):
    """Technology-neutral abilities requested by execution steps."""

    RESEARCH = "research"
    ELIGIBILITY = "eligibility"
    OFFER_DESIGN = "offer_design"
    DOCUMENT = "document"
    OUTREACH = "outreach"
    SUBMISSION = "submission"
    REPORTING = "reporting"
    GITHUB = "github"
    HTTP = "http"
    LLM = "llm"
    FILESYSTEM = "filesystem"
    DATABASE = "database"
    EMAIL = "email"
    CRM = "crm"


_STEP_CAPABILITIES: dict[ExecutionStepKind, frozenset[Capability]] = {
    ExecutionStepKind.RESEARCH: frozenset({Capability.RESEARCH}),
    ExecutionStepKind.VERIFY_ELIGIBILITY: frozenset({Capability.ELIGIBILITY}),
    ExecutionStepKind.DESIGN_OFFER: frozenset({Capability.OFFER_DESIGN}),
    ExecutionStepKind.BUILD_DELIVERABLE: frozenset({Capability.DOCUMENT}),
    ExecutionStepKind.PREPARE_OUTREACH: frozenset({Capability.OUTREACH}),
    ExecutionStepKind.SUBMIT_RESPONSE: frozenset({Capability.SUBMISSION}),
    ExecutionStepKind.TRACK_OUTCOME: frozenset({Capability.REPORTING}),
}


def required_capabilities(kind: ExecutionStepKind) -> frozenset[Capability]:
    """Return the stable capability contract for an execution-step kind."""

    return _STEP_CAPABILITIES[kind]
