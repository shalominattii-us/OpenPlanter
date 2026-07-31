from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .domain import EvidencePacket, MissionCandidate, Opportunity, QualificationStatus
from .execution import ExecutionPlan, ExecutionPolicy
from .execution_record import (
    ExecutionArtifact,
    ExecutionEvent,
    ExecutionEventStore,
    ExecutionRecorder,
    ExecutionRun,
    InMemoryExecutionEventStore,
)


@dataclass(frozen=True)
class ExecutionContext:
    """Immutable handoff contract between planning and execution bounded contexts."""

    opportunity: Opportunity
    evidence_packet: EvidencePacket
    mission_candidate: MissionCandidate
    execution_plan: ExecutionPlan
    execution_run: ExecutionRun
    events: tuple[ExecutionEvent, ...]
    artifacts: tuple[ExecutionArtifact, ...] = ()

    def __post_init__(self) -> None:
        if self.evidence_packet.opportunity_id != self.opportunity.opportunity_id:
            raise ValueError("evidence packet does not belong to opportunity")
        if self.mission_candidate.opportunity_id != self.opportunity.opportunity_id:
            raise ValueError("mission candidate does not belong to opportunity")
        if self.execution_plan.mission_candidate_id != self.mission_candidate.mission_candidate_id:
            raise ValueError("execution plan does not belong to mission candidate")
        if self.execution_run.execution_plan_id != self.execution_plan.execution_plan_id:
            raise ValueError("execution run does not belong to execution plan")
        if any(event.execution_run_id != self.execution_run.execution_run_id for event in self.events):
            raise ValueError("execution context contains events from another run")
        if any(artifact.execution_run_id != self.execution_run.execution_run_id for artifact in self.artifacts):
            raise ValueError("execution context contains artifacts from another run")


class ExecutionLifecycle:
    """Initialize a durable execution lifecycle from qualified domain inputs."""

    def __init__(
        self,
        *,
        recorder: ExecutionRecorder,
        policy: ExecutionPolicy | None = None,
        actor: str = "universal-execution-engine",
    ) -> None:
        self.recorder = recorder
        self.policy = policy or ExecutionPolicy()
        self.actor = actor

    @classmethod
    def in_memory(
        cls,
        *,
        policy: ExecutionPolicy | None = None,
        actor: str = "universal-execution-engine",
    ) -> "ExecutionLifecycle":
        store = InMemoryExecutionEventStore()
        return cls(recorder=ExecutionRecorder(store), policy=policy, actor=actor)

    @property
    def store(self) -> ExecutionEventStore:
        return self.recorder.store

    def initialize(
        self,
        opportunity: Opportunity,
        evidence_packet: EvidencePacket,
        mission_candidate: MissionCandidate,
        *,
        occurred_at: datetime | None = None,
    ) -> ExecutionContext:
        timestamp = occurred_at or datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        if evidence_packet.opportunity_id != opportunity.opportunity_id:
            raise ValueError("evidence packet does not belong to opportunity")
        if mission_candidate.opportunity_id != opportunity.opportunity_id:
            raise ValueError("mission candidate does not belong to opportunity")
        if mission_candidate.evidence_packet_id != evidence_packet.evidence_packet_id:
            raise ValueError("mission candidate does not reference evidence packet")
        if mission_candidate.decision.status == QualificationStatus.REJECTED:
            raise ValueError("rejected mission candidates cannot initialize execution")

        plan = self.policy.plan(opportunity, mission_candidate, created_at=timestamp)
        run = self.recorder.create_for_plan(plan, actor=self.actor, occurred_at=timestamp)
        return ExecutionContext(
            opportunity=opportunity,
            evidence_packet=evidence_packet,
            mission_candidate=mission_candidate,
            execution_plan=plan,
            execution_run=run,
            events=self.recorder.timeline(run.execution_run_id),
            artifacts=self.store.artifacts_for_run(run.execution_run_id),
        )

    def refresh(self, context: ExecutionContext) -> ExecutionContext:
        run = self.store.get_run(context.execution_run.execution_run_id)
        return ExecutionContext(
            opportunity=context.opportunity,
            evidence_packet=context.evidence_packet,
            mission_candidate=context.mission_candidate,
            execution_plan=context.execution_plan,
            execution_run=run,
            events=self.recorder.timeline(run.execution_run_id),
            artifacts=self.store.artifacts_for_run(run.execution_run_id),
        )
