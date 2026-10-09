from digital_workshop.domain.models import BoundingBox, DrawingObject
from digital_workshop.services.relationships import (
    LayerStrategy,
    ProximityStrategy,
    RelationshipEngine,
)


def obj(i: int, x: float, layer: str) -> DrawingObject:
    return DrawingObject(str(i), "INSERT", layer, BoundingBox(x, 0, x + 2, 2), id=i)


OBJECTS = [obj(1, 0, "A"), obj(2, 3, "B"), obj(3, 20, "A")]


def test_proximity_links_close_pairs_left_to_right() -> None:
    rels = ProximityStrategy(threshold=1.5).find(OBJECTS[::-1])
    assert [(r.source_id, r.target_id, r.relation_type) for r in rels] == [(1, 2, "proximity")]
    assert rels[0].distance == 1.0


def test_layer_strategy_chains_members() -> None:
    rels = LayerStrategy().find(OBJECTS)
    assert [(r.source_id, r.target_id, r.relation_type) for r in rels] == [(1, 3, "same_layer")]


def test_engine_combines_and_deduplicates() -> None:
    engine = RelationshipEngine([ProximityStrategy(1.5), ProximityStrategy(1.5), LayerStrategy()])
    rels = engine.build(OBJECTS)
    assert sorted((r.source_id, r.target_id, r.relation_type) for r in rels) == [
        (1, 2, "proximity"),
        (1, 3, "same_layer"),
    ]
    assert RelationshipEngine([]).build(OBJECTS) == []
