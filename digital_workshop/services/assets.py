"""Asset creation."""

from __future__ import annotations

from collections.abc import Callable, Collection

from digital_workshop.db.repositories import UnitOfWork
from digital_workshop.domain.models import (
    Asset,
    AssetDetail,
    AssetObjectSuggestion,
    AssetRequest,
    BoundingBox,
    CostItem,
    Relationship,
)
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

    def replace_relationships(self, asset_id: int, relationships: Collection[Relationship]) -> None:
        """Save human-reviewed relationships for an existing asset."""
        with self._uow_factory() as uow:
            if not uow.assets.replace_relationships(asset_id, list(relationships)):
                raise AssetValidationError(f"Unknown asset {asset_id}.")

    def replace_cost_items(self, asset_id: int, cost_items: Collection[CostItem]) -> None:
        """Save the human-reviewed base-cost schedule for an existing asset."""
        try:
            with self._uow_factory() as uow:
                if not uow.assets.replace_cost_items(asset_id, list(cost_items)):
                    raise AssetValidationError(f"Unknown asset {asset_id}.")
        except ValueError as exc:
            raise AssetValidationError(str(exc)) from exc

    def suggest_additions(self, asset_id: int, tolerance: float) -> list[AssetObjectSuggestion]:
        """Suggest nearby unselected objects without changing the asset."""
        if tolerance < 0:
            raise ValueError("Suggestion tolerance cannot be negative.")
        with self._uow_factory() as uow:
            detail = uow.assets.get_detail(asset_id)
            if detail is None or detail.asset.drawing_id is None:
                return []
            selected_ids = {obj.id for obj in detail.objects}
            line_segments = [
                segment for obj in detail.objects for segment in obj.connection_segments
            ]
            if not line_segments:
                return []
            line_boxes = [
                BoundingBox(
                    min(start[0], end[0]),
                    min(start[1], end[1]),
                    max(start[0], end[0]),
                    max(start[1], end[1]),
                )
                for start, end in line_segments
            ]
            suggestions = []
            for candidate in uow.drawings.list_objects(detail.asset.drawing_id):
                if candidate.id in selected_ids:
                    continue
                distance = min(candidate.bbox.gap(line_box) for line_box in line_boxes)
                if distance > tolerance:
                    continue
                attribute_names = {name.upper() for name in candidate.attributes}
                if "INSERT" == candidate.entity_type and (
                    "CONT_ARROW_LINK" in (candidate.block_name or "").upper()
                    or any("PIPELINES.TAG" in name for name in attribute_names)
                ):
                    reason = "Line tag / size connector"
                elif candidate.entity_type in {"TEXT", "MTEXT"}:
                    reason = "Nearby annotation"
                elif candidate.entity_type == "INSERT":
                    reason = "Nearby symbol"
                else:
                    reason = "Nearby linework"
                suggestions.append(AssetObjectSuggestion(candidate, round(distance, 4), reason))
        return sorted(
            suggestions,
            key=lambda item: (item.distance, item.reason, item.object.label.casefold()),
        )

    def include_suggestions(self, asset_id: int, object_ids: Collection[int]) -> None:
        """Add user-confirmed suggestion rows to an asset and infer new line links."""
        if not object_ids:
            return
        with self._uow_factory() as uow:
            detail = uow.assets.get_detail(asset_id)
            if detail is None or detail.asset.drawing_id is None:
                raise AssetValidationError(f"Unknown asset {asset_id}.")
            existing_ids = {obj.id for obj in detail.objects}
            new_ids = set(object_ids) - existing_ids
            additions = uow.drawings.get_objects(detail.asset.drawing_id, new_ids)
            if len(additions) != len(new_ids):
                raise AssetValidationError("Suggested objects must belong to this drawing.")
            if not new_ids:
                return
            if not uow.assets.add_objects(asset_id, new_ids):
                raise AssetValidationError(f"Unknown asset {asset_id}.")
            all_objects = [*detail.objects, *additions]
            existing_relationships = list(detail.relationships)
            existing_keys = {
                (item.source_id, item.target_id, item.relation_type)
                for item in existing_relationships
            }
            new_relationships = [
                relationship
                for relationship in self._engine.build(all_objects)
                if (relationship.source_id in new_ids or relationship.target_id in new_ids)
                and (
                    relationship.source_id,
                    relationship.target_id,
                    relationship.relation_type,
                )
                not in existing_keys
            ]
            if new_relationships:
                uow.assets.replace_relationships(
                    asset_id, [*existing_relationships, *new_relationships]
                )
