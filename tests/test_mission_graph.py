from __future__ import annotations

from datetime import datetime, timezone

import pytest

from gov_ops.mission_graph import (
    MissionGraph,
    MissionGraphBuilder,
    MissionGraphEdge,
    MissionGraphNode,
)
from gov_ops.opportunity import Opportunity
from gov_ops.qualification import QualificationEngine


OBSERVED_AT = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


def _qualified_opportunity() -> Opportunity:
    return Opportunity(
        opportunity_id="sam-graph-qualified",
        source="sam.gov",
        source_record_id="graph-qualified",
        title="Adaptive Manufacturing Demonstration",
        agency="Department of Example",
        due_date="2026-10-15",
        naics=["541715"],
        description="Demonstrate an adaptive manufacturing capability.",
        urls=["https://sam.gov/opp/graph-qualified/view"],
    )


def test_graph_preserves_observation_to_candidate_lineage() -> None:
    opportunity = _qualified_opportunity()
    result = QualificationEngine().qualify(opportunity, observed_at=OBSERVED_AT)

    graph = MissionGraphBuilder().build(opportunity, result)

    assert graph.root_opportunity_id == opportunity.opportunity_id
    assert len(graph.nodes_of_kind("opportunity")) == 1
    assert len(graph.nodes_of_kind("evidence")) == 1
    assert len(graph.nodes_of_kind("decision")) == 1
    assert len(graph.nodes_of_kind("mission_candidate")) == 1
    assert any(edge.relation == "has_evidence" for edge in graph.edges)
    assert any(edge.relation == "supports_decision" for edge in graph.edges)
    assert any(edge.relation == "proposes" for edge in graph.edges)
    assert all(node.kind != "mission" for node in graph.nodes)


def test_operator_review_graph_contains_no_candidate_or_mission() -> None:
    opportunity = Opportunity(
        opportunity_id="sam-graph-review",
        source="sam.gov",
        source_record_id="graph-review",
        title="Incomplete Research Notice",
        agency="Department of Example",
    )
    result = QualificationEngine().qualify(opportunity, observed_at=OBSERVED_AT)

    graph = MissionGraphBuilder().build(opportunity, result)

    assert result.decision.outcome == "operator_review"
    assert graph.nodes_of_kind("mission_candidate") == ()
    assert graph.nodes_of_kind("mission") == ()
    assert len(graph.nodes) == 3


def test_graph_identity_is_stable_across_rebuilds() -> None:
    opportunity = _qualified_opportunity()
    result = QualificationEngine().qualify(opportunity, observed_at=OBSERVED_AT)
    builder = MissionGraphBuilder()

    first = builder.build(opportunity, result)
    second = builder.build(opportunity, result)

    assert first.graph_id == second.graph_id
    assert first.to_dict() == second.to_dict()


def test_graph_rejects_unresolved_edges() -> None:
    graph = MissionGraph(
        graph_id="agx-mission-graph-invalid",
        root_opportunity_id="opportunity-1",
        nodes=(MissionGraphNode("opportunity-1", "opportunity", "observed"),),
        edges=(MissionGraphEdge("opportunity-1", "has_evidence", "missing"),),
    )

    with pytest.raises(ValueError, match="unresolved node"):
        graph.validate()
