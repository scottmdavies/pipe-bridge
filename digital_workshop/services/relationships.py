"""Relationship discovery between selected objects."""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import combinations
from typing import Protocol

from digital_workshop.domain.models import DrawingObject, Relationship

PROXIMITY = "proximity"
SAME_LAYER = "same_layer"
CONNECTION_CANDIDATE = "connection_candidate"
CONFIRMED_CONNECTION = "confirmed_connection"


class RelationshipStrategy(Protocol):
    """A rule that proposes relationships between objects."""

    def find(self, objects: Sequence[DrawingObject]) -> list[Relationship]:
        """Return relationships between the given (stored) objects."""
        ...


def _ordered(a: DrawingObject, b: DrawingObject) -> tuple[DrawingObject, DrawingObject]:
    """Order a pair consistently; this does not indicate process flow direction."""
    key_a, key_b = a.bbox.center, b.bbox.center
    return (a, b) if (key_a, a.id) <= (key_b, b.id) else (b, a)


class ProximityStrategy:
    """Relate objects whose bounding boxes are within ``threshold`` of each other."""

    def __init__(self, threshold: float) -> None:
        """Create the strategy with a gap threshold in drawing units."""
        self._threshold = threshold

    def find(self, objects: Sequence[DrawingObject]) -> list[Relationship]:
        """Return a relationship for every close pair, directed left-to-right."""
        result = []
        for a, b in combinations(objects, 2):
            gap = a.bbox.gap(b.bbox)
            if gap <= self._threshold:
                source, target = _ordered(a, b)
                result.append(Relationship(source.id, target.id, PROXIMITY, round(gap, 4)))
        return result


class PipeConnectionStrategy:
    """Find linework whose endpoints meet other line segments in XY."""

    def __init__(self, tolerance: float) -> None:
        """Create the strategy with a tolerance in the drawing's units."""
        if tolerance < 0:
            raise ValueError("Connection tolerance cannot be negative.")
        self._tolerance = tolerance

    def find(self, objects: Sequence[DrawingObject]) -> list[Relationship]:
        """Return one undirected candidate for each touching pair of linework objects."""
        result = []
        linework = [
            obj
            for obj in objects
            if obj.id is not None
            and obj.entity_type in {"LINE", "LWPOLYLINE", "POLYLINE"}
            and obj.connection_segments
        ]
        for first, second in combinations(linework, 2):
            distance = min(
                _endpoint_to_segment_distance(point, segment)
                for first_segment in first.connection_segments
                for second_segment in second.connection_segments
                for point, segment in (
                    (first_segment[0], second_segment),
                    (first_segment[1], second_segment),
                    (second_segment[0], first_segment),
                    (second_segment[1], first_segment),
                )
            )
            if distance <= self._tolerance:
                source, target = _ordered(first, second)
                result.append(
                    Relationship(
                        source.id,
                        target.id,
                        CONNECTION_CANDIDATE,
                        round(distance, 4),
                    )
                )
        return result


def _endpoint_to_segment_distance(
    point: tuple[float, float],
    segment: tuple[tuple[float, float], tuple[float, float]],
) -> float:
    (start_x, start_y), (end_x, end_y) = segment
    dx, dy = end_x - start_x, end_y - start_y
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return math.hypot(point[0] - start_x, point[1] - start_y)
    projection = max(
        0.0,
        min(1.0, ((point[0] - start_x) * dx + (point[1] - start_y) * dy) / length_squared),
    )
    nearest_x = start_x + projection * dx
    nearest_y = start_y + projection * dy
    return math.hypot(point[0] - nearest_x, point[1] - nearest_y)


class LayerStrategy:
    """Chain objects that share a layer, ordered left-to-right.

    A chain (rather than every pair) keeps the graph readable for large layers.
    """

    def find(self, objects: Sequence[DrawingObject]) -> list[Relationship]:
        """Return same-layer chain relationships."""
        by_layer: dict[str, list[DrawingObject]] = {}
        for obj in objects:
            by_layer.setdefault(obj.layer, []).append(obj)
        result = []
        for members in by_layer.values():
            members.sort(key=lambda o: (o.bbox.center, o.id))
            for a, b in zip(members, members[1:], strict=False):
                result.append(Relationship(a.id, b.id, SAME_LAYER, round(a.bbox.gap(b.bbox), 4)))
        return result


class RelationshipEngine:
    """Combines strategies into a de-duplicated relationship list.

    Initial strategies are proximity and layer based; a connectivity strategy can be
    injected later without changing callers.
    """

    def __init__(self, strategies: Sequence[RelationshipStrategy]) -> None:
        """Create the engine from injected strategies."""
        self._strategies = list(strategies)

    def build(self, objects: Sequence[DrawingObject]) -> list[Relationship]:
        """Run all strategies, dropping duplicate (source, target, type) edges."""
        seen: set[tuple[int, int, str]] = set()
        result: list[Relationship] = []
        for strategy in self._strategies:
            for rel in strategy.find(objects):
                key = (rel.source_id, rel.target_id, rel.relation_type)
                if rel.source_id != rel.target_id and key not in seen:
                    seen.add(key)
                    result.append(rel)
        return result
