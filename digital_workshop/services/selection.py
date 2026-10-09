"""Selection logic: hit testing, box selection and Included/Excluded toggling."""

from __future__ import annotations

from collections.abc import Iterable

from digital_workshop.domain.models import BoundingBox, DrawingObject


class SelectionService:
    """Pure selection rules operating on immutable id sets.

    A selection is a ``frozenset`` of object ids: ids in the set are *Included*,
    all other objects are *Excluded*. Objects on hidden layers can never be picked.
    """

    def visible(
        self, objects: Iterable[DrawingObject], hidden_layers: frozenset[str]
    ) -> list[DrawingObject]:
        """Filter out objects on hidden layers."""
        return [o for o in objects if o.layer not in hidden_layers]

    def hit_test(
        self, objects: Iterable[DrawingObject], x: float, y: float, tolerance: float = 0.0
    ) -> DrawingObject | None:
        """Return the most specific (smallest bbox) object under a point."""
        hits = [o for o in objects if o.id is not None and o.bbox.contains_point(x, y, tolerance)]
        return min(hits, key=lambda o: o.bbox.area, default=None)

    def click(
        self,
        current: frozenset[int],
        target: DrawingObject | None,
        *,
        shift: bool = False,
        ctrl: bool = False,
    ) -> frozenset[int]:
        """Apply a click.

        * Plain click toggles the clicked object and excludes everything else.
        * Ctrl-click toggles the clicked object and keeps the rest of the selection.
        * Shift-click includes the clicked object and keeps the rest of the selection.
        * Clicking empty space with no modifier clears the selection.
        """
        multi = shift or ctrl
        if target is None or target.id is None:
            return current if multi else frozenset()
        if shift:
            return current | {target.id}
        if ctrl:
            return current ^ {target.id}
        return frozenset() if target.id in current else frozenset({target.id})

    def box_select(
        self,
        current: frozenset[int],
        objects: Iterable[DrawingObject],
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        *,
        additive: bool = False,
    ) -> frozenset[int]:
        """Select all objects fully inside the rectangle.

        The rectangle corners may be given in any order. With ``additive`` (shift or
        ctrl held) the result is added to the current selection, otherwise it
        replaces it.
        """
        area = BoundingBox(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        inside = frozenset(o.id for o in objects if o.id is not None and area.contains(o.bbox))
        return current | inside if additive else inside
