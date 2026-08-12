from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..execution import ExecutionStep, ExecutionStepKind
from .capabilities import Capability
from .request import ExecutionRequest
from .result import ExecutionArtifactResult, ExecutionResult


_REQUIRED_ARTIFACTS = frozenset(
    {
        "proposal-draft.md",
        "implementation-plan.json",
        "budget-assumptions.json",
    }
)


@dataclass(frozen=True)
class OutreachPreparationExecutorPlugin:
    """Prepare reviewable contact and submission materials without sending them."""

    plugin_id: str = "outreach-preparation-executor"
    version: str = "1.0.0"

    def capabilities(self) -> frozenset[Capability]:
        return frozenset({Capability.OUTREACH})

    def supports(self, step: ExecutionStep) -> bool:
        return step.kind is ExecutionStepKind.PREPARE_OUTREACH

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if not self.supports(request.step):
            return ExecutionResult.failed(
                message=(
                    "outreach preparation executor does not support step kind "
                    f"{request.step.kind.value}"
                ),
                metadata={"request_id": request.request_id, "step_id": request.step.step_id},
            )

        available = frozenset(item.name for item in request.execution_memory.artifacts)
        missing = tuple(sorted(_REQUIRED_ARTIFACTS - available))
        if missing:
            return ExecutionResult.failed(
                message="outreach preparation requires a completed response package",
                metadata={
                    "request_id": request.request_id,
                    "step_id": request.step.step_id,
                    "missing_artifacts": missing,
                },
            )

        title = str(request.inputs.get("title") or "Untitled opportunity")
        issuer = str(request.inputs.get("issuer") or "Opportunity issuer")
        deadline = request.inputs.get("deadline")
        submission_path = request.inputs.get("submission_path")

        contact_brief = {
            "schema_version": "universal-contact-brief-v1",
            "opportunity_id": request.inputs.get("opportunity_id"),
            "recipient": issuer,
            "subject": f"Response regarding {title}",
            "deadline": deadline,
            "submission_path": submission_path,
            "attachment_names": tuple(sorted(_REQUIRED_ARTIFACTS)),
            "review_status": "requires_operator_review",
            "external_action_performed": False,
        }
        checklist = _submission_checklist(
            title=title,
            deadline=deadline,
            submission_path=submission_path,
        )
        outreach = _outreach_draft(title=title, issuer=issuer)

        artifacts = (
            ExecutionArtifactResult(
                name="outreach-draft.md",
                uri=_uri(request, "outreach-draft.md"),
                media_type="text/markdown",
                content=outreach,
            ),
            ExecutionArtifactResult(
                name="submission-checklist.md",
                uri=_uri(request, "submission-checklist.md"),
                media_type="text/markdown",
                content=checklist,
            ),
            ExecutionArtifactResult(
                name="contact-brief.json",
                uri=_uri(request, "contact-brief.json"),
                media_type="application/json",
                content=_json_bytes(contact_brief),
            ),
        )
        return ExecutionResult.succeeded(
            message="Outreach and submission materials prepared for operator review.",
            artifacts=artifacts,
            metrics={
                "outreach.source_artifacts": float(len(available)),
                "outreach.output_count": float(len(artifacts)),
                "outreach.external_actions": 0.0,
            },
            metadata={
                "request_id": request.request_id,
                "execution_run_id": request.execution_run_id,
                "step_id": request.step.step_id,
                "source_artifacts": tuple(sorted(available)),
                "requires_operator_review": True,
                "external_action_performed": False,
                "trace_id": request.trace_id,
            },
        )


def _uri(request: ExecutionRequest, name: str) -> str:
    return f"execution://{request.execution_run_id}/steps/{request.step.step_id}/{name}"


def _json_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _outreach_draft(*, title: str, issuer: str) -> str:
    return f"""# Outreach Draft: {title}

To: {issuer}
Subject: Response regarding {title}

Hello,

We have prepared a reviewable response to the opportunity titled \"{title}.\" The package is designed to align the recipient's desired outcomes with a bounded, evidence-backed delivery approach, explicit acceptance criteria, and controlled commercial assumptions.

The attached materials remain drafts pending final operator review and approval. No contractual commitment is expressed by this message.

Respectfully,
Authorized Representative

---
Status: Draft only. Not sent.
"""


def _submission_checklist(*, title: str, deadline: Any, submission_path: Any) -> str:
    return f"""# Submission Checklist: {title}

- [ ] Confirm authoritative opportunity source and current status.
- [ ] Resolve all eligibility evidence gaps.
- [ ] Approve final scope, schedule, pricing, and legal terms.
- [ ] Verify proposal, implementation plan, and budget assumptions.
- [ ] Confirm recipient identity and authorized submission channel.
- [ ] Confirm deadline: {deadline or 'not specified'}.
- [ ] Confirm submission path: {submission_path or 'not specified'}.
- [ ] Verify required attachments and file formats.
- [ ] Obtain explicit approval for external submission.
- [ ] Record submission receipt after sending.

Status: Operator review required. Nothing has been sent.
"""