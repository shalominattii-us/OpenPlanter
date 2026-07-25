from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from gov_ops.opportunity import Opportunity
from gov_ops.qualification import QualificationResult


@dataclass(frozen=True)
class MissionGraphNode:
    """A durable object reference in the mission lineage graph."""

    node_id: str
    kind: str
    state: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MissionGraphEdge:
    """A typed, directed relationship between two graph nodes."""

    source_id: str
    relation: str
    target_id: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class MissionGraph:
    """Minimal replayable lineage from observation through mission candidacy."""

    graph_id: str
    root_opportunity_id: str
    nodes: tuple[MissionGraphNode, ...]
    edges: tuple[MissionGraphEdge, ...]
    schema_version: str = "aegentix-mission-graph-v0.1"

    def validate(self) -> None:
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Mission graph node IDs must be unique")
        if self.root_opportunity_id not in set(node_ids):
            raise ValueError("Mission graph root must resolve to an opportunity node")

        known = set(node_ids)
        for edge in self.edges:
            if edge.source_id not in known or edge.target_id not in known:
                raise ValueError(
                    f"Mission graph edge contains an unresolved node: {edge.source_id} -> {edge.target_id}"
                )

    def nodes_of_kind(self, kind: str) -> tuple[MissionGraphNode, ...]:
        return tuple(node for node in self.nodes if node.kind == kind)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "graph_id": self.graph_id,
            "root_opportunity_id": self.root_opportunity_id,
            "schema_version": self.schema_version,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }


def _graph_id(opportunity_id: str) -> str:
    digest = hashlib.sha256(opportunity_id.encode("utf-8")).hexdigest()[:12]
    return f"agx-mission-graph-{digest}"


class MissionGraphBuilder:
    """Build the first mission graph without creating or executing a mission."""

    def build(self, opportunity: Opportunity, result: QualificationResult) -> MissionGraph:
        opportunity.validate()
        if result.evidence.opportunity_id != opportunity.opportunity_id:
            raise ValueError("Evidence does not belong to the supplied opportunity")
        if result.decision.opportunity_id != opportunity.opportunity_id:
            raise ValueError("Decision does not belong to the supplied opportunity")
        if result.decision.evidence_id != result.evidence.evidence_id:
            raise ValueError("Decision does not reference the supplied evidence")

        nodes: list[MissionGraphNode] = [
            MissionGraphNode(
                node_id=opportunity.opportunity_id,
                kind="opportunity",
                state="observed",
                data={
                    "source": opportunity.source,
                    "source_record_id": opportunity.source_record_id,
                    "title": opportunity.title,
                },
            ),
            MissionGraphNode(
                node_id=result.evidence.evidence_id,
                kind="evidence",
                state="assembled",
                data=result.evidence.to_dict(),
            ),
            MissionGraphNode(
                node_id=result.decision.decision_id,
                kind="decision",
                state="decided",
                data=result.decision.to_dict(),
            ),
        ]
        edges: list[MissionGraphEdge] = [
            MissionGraphEdge(
                source_id=opportunity.opportunity_id,
                relation="has_evidence",
                target_id=result.evidence.evidence_id,
            ),
            MissionGraphEdge(
                source_id=result.evidence.evidence_id,
                relation="supports_decision",
                target_id=result.decision.decision_id,
            ),
        ]

        if result.mission_candidate is not None:
            candidate = result.mission_candidate
            if candidate.opportunity_id != opportunity.opportunity_id:
                raise ValueError("Mission candidate does not belong to the supplied opportunity")
            if candidate.evidence_id != result.evidence.evidence_id:
                raise ValueError("Mission candidate does not reference the supplied evidence")
            if candidate.decision_id != result.decision.decision_id:
                raise ValueError("Mission candidate does not reference the supplied decision")

            nodes.append(
                MissionGraphNode(
                    node_id=candidate.candidate_id,
                    kind="mission_candidate",
                    state=candidate.state,
                    data=candidate.to_dict(),
                )
            )
            edges.extend(
                [
                    MissionGraphEdge(
                        source_id=result.decision.decision_id,
                        relation="proposes",
                        target_id=candidate.candidate_id,
                    ),
                    MissionGraphEdge(
                        source_id=opportunity.opportunity_id,
                        relation="originates",
                        target_id=candidate.candidate_id,
                    ),
                ]
            )

        graph = MissionGraph(
            graph_id=_graph_id(opportunity.opportunity_id),
            root_opportunity_id=opportunity.opportunity_id,
            nodes=tuple(nodes),
            edges=tuple(edges),
        )
        graph.validate()
        return graph

    def build_many(
        self,
        pairs: Iterable[tuple[Opportunity, QualificationResult]],
    ) -> list[MissionGraph]:
        return [self.build(opportunity, result) for opportunity, result in pairs]
