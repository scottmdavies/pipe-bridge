from digital_workshop.domain.models import BoundingBox, DrawingObject
from digital_workshop.services.relationships import (
    CONNECTION_CANDIDATE,
    LayerStrategy,
    PipeConnectionStrategy,
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


def line_object(
    object_id: int,
    segments: tuple[tuple[tuple[float, float], tuple[float, float]], ...],
) -> DrawingObject:
    points = [point for segment in segments for point in segment]
    return DrawingObject(
        str(object_id),
        "LINE",
        "PIPE",
        BoundingBox(
            min(point[0] for point in points),
            min(point[1] for point in points),
            max(point[0] for point in points),
            max(point[1] for point in points),
        ),
        connection_segments=segments,
        id=object_id,
    )


def test_pipe_connection_joins_gapped_endpoints_within_tolerance() -> None:
    first = line_object(1, (((0, 0), (5, 0)),))
    second = line_object(2, (((5.4, 0), (8, 0)),))

    relationships = PipeConnectionStrategy(0.5).find([second, first])

    assert [(r.source_id, r.target_id, r.relation_type, r.distance) for r in relationships] == [
        (1, 2, CONNECTION_CANDIDATE, 0.4)
    ]


def test_pipe_connection_connects_endpoint_to_segment_interior() -> None:
    horizontal = line_object(1, (((0, 0), (10, 0)),))
    tee = line_object(2, (((5, 0.25), (5, 3)),))

    relationships = PipeConnectionStrategy(0.3).find([horizontal, tee])

    assert len(relationships) == 1
    assert relationships[0].distance == 0.25


def test_pipe_connection_does_not_join_crossing_segment_interiors() -> None:
    horizontal = line_object(1, (((0, 0), (10, 0)),))
    vertical = line_object(2, (((5, -5), (5, 5)),))

    assert PipeConnectionStrategy(0.1).find([horizontal, vertical]) == []
