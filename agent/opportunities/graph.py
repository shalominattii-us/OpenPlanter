from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Sequence

from .domain import EvidencePacket, MissionCandidate, Opportunity, to_primitive


MISSION_GRAPH_SCHEMA_VERSION = "universal-opportunity-mission-graph-v1"


@dataclass(frozen=True)
class MissionGraphNode:
    node_id: str
    kind: str
    version: int
    data: Mapping[str, Any]


@dataclass(frozen=True)
class MissionGraphEdge:
    source_id: str
    relation: str
    target_id: str


@dataclass(frozen=True)
class MissionGraph:
    graph_id: str
    root_opportunity_id: str
    nodes: tuple[MissionGraphNode, ...]
    edges: tuple[MissionGraphEdge, ...]
    schema_version: str = MISSION_GRAPH_SCHEMA_VERSION

    def validate(self) -> None:
        node_ids = [node.node_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("mission graph node IDs must be unique")
        known = set(node_ids)
        if self.root_opportunity_id not in known:
            raise ValueError("mission graph root must resolve to a node")
        for edge in self.edges:
            if edge.source_id not in known or edge.target_id not in known:
                raise ValueError("mission graph edge contains an unresolved node")

    def to_primitive(self) -> dict[str, Any]:
        self.validate()
        return {
            "graph_id": self.graph_id,
            "root_opportunity_id": self.root_opportunity_id,
            "schema_version": self.schema_version,
            "nodes": [to_primitive(node) for node in self.nodes],
            "edges": [to_primitive(edge) for edge in self.edges],
        }


def build_mission_graph(
    opportunity: Opportunity,
    evidence_packet: EvidencePacket,
    mission_candidate: MissionCandidate,
) -> MissionGraph:
    """Build deterministic lineage without promoting a candidate to a mission."""

    if evidence_packet.opportunity_id != opportunity.opportunity_id:
        raise ValueError("evidence packet does not belong to opportunity")
    if mission_candidate.opportunity_id != opportunity.opportunity_id:
        raise ValueError("mission candidate does not belong to opportunity")
    if mission_candidate.evidence_packet_id != evidence_packet.evidence_packet_id:
        raise ValueError("mission candidate does not reference evidence packet")

    graph_key = "|".join(
        (
            opportunity.opportunity_id,
            str(opportunity.version),
            evidence_packet.evidence_packet_id,
            mission_candidate.mission_candidate_id,
        )
    )
    graph_id = f"mig_{sha256(graph_key.encode('utf-8')).hexdigest()[:20]}"
    nodes = (
        MissionGraphNode(
            node_id=opportunity.opportunity_id,
            kind="opportunity",
            version=opportunity.version,
            data=to_primitive(opportunity),
        ),
        MissionGraphNode(
            node_id=evidence_packet.evidence_packet_id,
            kind="evidence_packet",
            version=evidence_packet.version,
            data=to_primitive(evidence_packet),
        ),
        MissionGraphNode(
            node_id=mission_candidate.mission_candidate_id,
            kind="mission_candidate",
            version=1,
            data=to_primitive(mission_candidate),
        ),
    )
    edges = (
        MissionGraphEdge(
            source_id=opportunity.opportunity_id,
            relation="has_evidence",
            target_id=evidence_packet.evidence_packet_id,
        ),
        MissionGraphEdge(
            source_id=evidence_packet.evidence_packet_id,
            relation="supports_candidate",
            target_id=mission_candidate.mission_candidate_id,
        ),
        MissionGraphEdge(
            source_id=opportunity.opportunity_id,
            relation="originates_candidate",
            target_id=mission_candidate.mission_candidate_id,
        ),
    )
    graph = MissionGraph(
        graph_id=graph_id,
        root_opportunity_id=opportunity.opportunity_id,
        nodes=nodes,
        edges=edges,
    )
    graph.validate()
    return graph
