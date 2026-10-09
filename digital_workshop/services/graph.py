"""Relationship graph construction and PyVis rendering."""

from __future__ import annotations

import networkx as nx
from pyvis.network import Network

from digital_workshop.domain.models import AssetDetail

TYPE_COLOURS = {
    "TANK": "#4dabf7",
    "PUMP": "#51cf66",
    "VALVE": "#ffa94d",
}
DEFAULT_COLOUR = "#adb5bd"
EDGE_COLOURS = {"proximity": "#868e96", "same_layer": "#c0a0e0"}


class GraphBuilder:
    """Builds NetworkX graphs from assets and renders them with PyVis."""

    def build(self, detail: AssetDetail) -> nx.DiGraph:
        """Create a directed graph: one node per object, one edge per relationship."""
        graph = nx.DiGraph(name=detail.asset.name)
        for obj in detail.objects:
            graph.add_node(
                obj.id,
                label=obj.label,
                layer=obj.layer,
                entity_type=obj.entity_type,
                block_name=obj.block_name,
            )
        for rel in detail.relationships:
            graph.add_edge(
                rel.source_id, rel.target_id, relation_type=rel.relation_type, distance=rel.distance
            )
        return graph

    def to_html(self, graph: nx.DiGraph) -> str:
        """Render the graph as a self-contained interactive HTML document."""
        net = Network(
            height="480px",
            width="100%",
            directed=True,
            cdn_resources="in_line",
            notebook=False,
        )
        for node_id, data in graph.nodes(data=True):
            key = (data.get("block_name") or data.get("entity_type") or "").upper()
            net.add_node(
                node_id,
                label=data["label"],
                title=f"{data['entity_type']} on {data['layer']}",
                color=TYPE_COLOURS.get(key, DEFAULT_COLOUR),
            )
        for source, target, data in graph.edges(data=True):
            net.add_edge(
                source,
                target,
                title=data["relation_type"],
                color=EDGE_COLOURS.get(data["relation_type"], DEFAULT_COLOUR),
            )
        return net.generate_html(notebook=False)
