"""Asset creation."""

from __future__ import annotations

from collections.abc import Callable, Collection

from digital_workshop.db.repositories import UnitOfWork
from digital_workshop.domain.models import Asset, AssetDetail, AssetRequest
from digital_workshop.services.relationships import RelationshipEngine


class AssetValidationError(ValueError):
    """Raised when an asset request is invalid."""


class AssetCreator:
    """Packages a selection of drawing objects as a reusable asset."""

    def __init__(self, uow_factory: Callable[[], UnitOfWork], engine: RelationshipEngine) -> None:
        """Create the service from a unit-of-work factory and a relationship engine."""
        self._uow_factory = uow_factory
        self._engine = engine

    def create(
        self, drawing_id: int, object_ids: Collection[int], request: AssetRequest
    ) -> AssetDetail:
        """Create and store an asset from the selected objects.

        Raises:
            AssetValidationError: If the name is blank, nothing is selected, or ids do
                not belong to the drawing.
        """
        name = request.name.strip()
        if not name:
            raise AssetValidationError("Asset name is required.")
        if not object_ids:
            raise AssetValidationError("Select at least one object.")
        cleaned = AssetRequest(
            name=name,
            description=request.description.strip(),
            sector=request.sector.strip(),
            customer_need=request.customer_need.strip(),
            tags=tuple(dict.fromkeys(t.strip() for t in request.tags if t.strip())),
        )
        with self._uow_factory() as uow:
            if uow.drawings.get(drawing_id) is None:
                raise AssetValidationError(f"Unknown drawing {drawing_id}.")
            objects = uow.drawings.get_objects(drawing_id, object_ids)
            if len(objects) != len(set(object_ids)):
                raise AssetValidationError("Selection contains objects not in this drawing.")
            relationships = self._engine.build(objects)
            asset: Asset = uow.assets.add(
                drawing_id, cleaned, [o.id for o in objects], relationships
            )
        return AssetDetail(asset=asset, objects=objects, relationships=relationships)
