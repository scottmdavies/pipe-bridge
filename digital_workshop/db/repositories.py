"""Repository layer: the only place that talks SQL / ORM."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import replace
from types import TracebackType

from sqlalchemy import select
from sqlalchemy.orm import Session

from digital_workshop.db.orm import (
    AssetObjectRecord,
    AssetRecord,
    CostItemRecord,
    DrawingRecord,
    DXFObjectRecord,
    ProjectRecord,
    RelationshipRecord,
)
from digital_workshop.domain.models import (
    Asset,
    AssetDetail,
    AssetRequest,
    BoundingBox,
    CostItem,
    Drawing,
    DrawingMetadata,
    DrawingObject,
    ParsedDrawing,
    Project,
    Relationship,
)


class ProjectRepository:
    """Persistence of projects."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to a session."""
        self._session = session

    def get_or_create(self, name: str) -> Project:
        """Return the project called ``name``, creating it if needed."""
        record = self._session.scalar(select(ProjectRecord).where(ProjectRecord.name == name))
        if record is None:
            record = ProjectRecord(name=name)
            self._session.add(record)
            self._session.flush()
        return _project(record)

    def list(self) -> list[Project]:
        """List all projects by name."""
        rows = self._session.scalars(select(ProjectRecord).order_by(ProjectRecord.name))
        return [_project(r) for r in rows]


class DrawingRepository:
    """Persistence of drawings and their objects."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to a session."""
        self._session = session

    def add(
        self,
        project_id: int,
        filename: str,
        sha256: str,
        stored_path: str,
        parsed: ParsedDrawing,
    ) -> Drawing:
        """Store drawing metadata and all of its objects."""
        meta = parsed.metadata
        record = DrawingRecord(
            project_id=project_id,
            filename=filename,
            sha256=sha256,
            stored_path=stored_path,
            layers=meta.layers,
            blocks=meta.blocks,
            insert_count=meta.insert_count,
            text_count=meta.text_count,
            entity_counts=meta.entity_counts,
            bbox=meta.bbox.as_list() if meta.bbox else None,
        )
        self._session.add(record)
        self._session.flush()
        self._session.add_all(
            DXFObjectRecord(
                drawing_id=record.id,
                handle=o.handle,
                entity_type=o.entity_type,
                layer=o.layer,
                block_name=o.block_name,
                text=o.text,
                attributes=o.attributes,
                bbox=o.bbox.as_list(),
                primitives=list(o.primitives),
                connection_segments=[
                    [list(start), list(end)] for start, end in o.connection_segments
                ],
            )
            for o in parsed.objects
        )
        self._session.flush()
        return _drawing(record)

    def get(self, drawing_id: int) -> Drawing | None:
        """Fetch a drawing by id."""
        record = self._session.get(DrawingRecord, drawing_id)
        return _drawing(record) if record else None

    def list_for_project(self, project_id: int) -> list[Drawing]:
        """List drawings of a project, newest first."""
        stmt = (
            select(DrawingRecord)
            .where(DrawingRecord.project_id == project_id)
            .order_by(DrawingRecord.id.desc())
        )
        return [_drawing(r) for r in self._session.scalars(stmt)]

    def list_all(self) -> list[Drawing]:
        """List all drawings, newest first."""
        stmt = select(DrawingRecord).order_by(DrawingRecord.id.desc())
        return [_drawing(r) for r in self._session.scalars(stmt)]

    def list_objects(self, drawing_id: int) -> list[DrawingObject]:
        """List all objects of a drawing."""
        stmt = (
            select(DXFObjectRecord)
            .where(DXFObjectRecord.drawing_id == drawing_id)
            .order_by(DXFObjectRecord.id)
        )
        return [_object(r) for r in self._session.scalars(stmt)]

    def get_objects(self, drawing_id: int, object_ids: Iterable[int]) -> list[DrawingObject]:
        """Fetch specific objects of a drawing, ordered by id."""
        ids = list(object_ids)
        if not ids:
            return []
        stmt = (
            select(DXFObjectRecord)
            .where(DXFObjectRecord.drawing_id == drawing_id, DXFObjectRecord.id.in_(ids))
            .order_by(DXFObjectRecord.id)
        )
        return [_object(r) for r in self._session.scalars(stmt)]


class AssetRepository:
    """Persistence of assets, their objects and relationships."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to a session."""
        self._session = session

    def add(
        self,
        drawing_id: int,
        request: AssetRequest,
        object_ids: Sequence[int],
        relationships: Sequence[Relationship],
    ) -> Asset:
        """Persist a new asset with its object membership and relationships."""
        record = AssetRecord(
            drawing_id=drawing_id,
            name=request.name,
            description=request.description,
            sector=request.sector,
            customer_need=request.customer_need,
            tags=list(request.tags),
        )
        record.objects = [AssetObjectRecord(dxf_object_id=i) for i in object_ids]
        record.relationships = [
            RelationshipRecord(
                source_object_id=r.source_id,
                target_object_id=r.target_id,
                relation_type=r.relation_type,
                distance=r.distance,
            )
            for r in relationships
        ]
        self._session.add(record)
        self._session.flush()
        return _asset(record)

    def replace_relationships(self, asset_id: int, relationships: Sequence[Relationship]) -> bool:
        """Replace an asset's relationships after validating object membership."""
        record = self._session.get(AssetRecord, asset_id)
        if record is None:
            return False
        object_ids = {item.dxf_object_id for item in record.objects}
        if any(
            relationship.source_id == relationship.target_id
            or relationship.source_id not in object_ids
            or relationship.target_id not in object_ids
            for relationship in relationships
        ):
            raise ValueError("Relationships must connect two different objects in this asset.")
        record.relationships = [
            RelationshipRecord(
                source_object_id=relationship.source_id,
                target_object_id=relationship.target_id,
                relation_type=relationship.relation_type,
                distance=relationship.distance,
            )
            for relationship in relationships
        ]
        self._session.flush()
        return True

    def add_objects(self, asset_id: int, object_ids: set[int]) -> bool:
        """Add drawing objects to an asset after validating drawing ownership."""
        record = self._session.get(AssetRecord, asset_id)
        if record is None:
            return False
        existing_ids = {item.dxf_object_id for item in record.objects}
        additions = object_ids - existing_ids
        if not additions:
            return True
        valid_ids = set(
            self._session.scalars(
                select(DXFObjectRecord.id).where(
                    DXFObjectRecord.drawing_id == record.drawing_id,
                    DXFObjectRecord.id.in_(additions),
                )
            )
        )
        if valid_ids != additions:
            raise ValueError("Suggested objects must belong to the asset's drawing.")
        record.objects.extend(AssetObjectRecord(dxf_object_id=object_id) for object_id in additions)
        self._session.flush()
        return True

    def replace_cost_items(self, asset_id: int, cost_items: Sequence[CostItem]) -> bool:
        """Replace an asset's cost schedule after validating linked equipment objects."""
        record = self._session.get(AssetRecord, asset_id)
        if record is None:
            return False
        object_ids = {item.dxf_object_id for item in record.objects}
        categories = {"equipment", "pipework", "electrical", "ma"}
        rows = []
        for item in cost_items:
            currency = item.currency.strip().upper()
            if item.category not in categories:
                raise ValueError(f"Unsupported cost category: {item.category}.")
            if item.category == "equipment":
                if item.object_id not in object_ids:
                    raise ValueError("Equipment costs must reference an object in this asset.")
            elif item.object_id is not None:
                raise ValueError("Scope lump sums cannot reference a single drawing object.")
            if item.quantity <= 0 or item.unit_cost < 0:
                raise ValueError("Cost quantity must be positive and unit cost cannot be negative.")
            if len(currency) != 3 or not currency.isalpha():
                raise ValueError("Currency must be a three-letter code.")
            rows.append(
                CostItemRecord(
                    dxf_object_id=item.object_id,
                    category=item.category,
                    description=item.description.strip(),
                    quantity=item.quantity,
                    unit_cost=item.unit_cost,
                    currency=currency,
                    source=item.source.strip(),
                    basis_date=item.basis_date,
                )
            )
        record.cost_items = rows
        self._session.flush()
        return True

    def list(self) -> list[Asset]:
        """List all assets, newest first."""
        stmt = select(AssetRecord).order_by(AssetRecord.id.desc())
        return [_asset(r) for r in self._session.scalars(stmt)]

    def get_detail(self, asset_id: int) -> AssetDetail | None:
        """Load an asset with its objects and relationships."""
        record = self._session.get(AssetRecord, asset_id)
        if record is None:
            return None
        ids = [o.dxf_object_id for o in record.objects]
        stmt = (
            select(DXFObjectRecord).where(DXFObjectRecord.id.in_(ids)).order_by(DXFObjectRecord.id)
        )
        objects = [_object(r) for r in self._session.scalars(stmt)]
        relationships = [
            Relationship(r.source_object_id, r.target_object_id, r.relation_type, r.distance)
            for r in record.relationships
        ]
        costs = [
            CostItem(
                category=r.category,
                description=r.description,
                quantity=r.quantity,
                unit_cost=r.unit_cost,
                currency=r.currency,
                object_id=r.dxf_object_id,
                source=r.source,
                basis_date=r.basis_date,
                id=r.id,
            )
            for r in record.cost_items
        ]
        return AssetDetail(
            asset=_asset(record), objects=objects, relationships=relationships, cost_items=costs
        )


class UnitOfWork:
    """Transaction scope exposing the repositories.

    Commits on clean exit and rolls back when an exception escapes.
    """

    projects: ProjectRepository
    drawings: DrawingRepository
    assets: AssetRepository

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        """Create a unit of work from a session factory."""
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> UnitOfWork:
        """Open a session and bind the repositories."""
        self._session = self._session_factory()
        self.projects = ProjectRepository(self._session)
        self.drawings = DrawingRepository(self._session)
        self.assets = AssetRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Commit or roll back, then close the session."""
        assert self._session is not None
        try:
            if exc_type is None:
                self._session.commit()
            else:
                self._session.rollback()
        finally:
            self._session.close()
            self._session = None


def _project(r: ProjectRecord) -> Project:
    return Project(id=r.id, name=r.name, created_at=r.created_at)


def _drawing(r: DrawingRecord) -> Drawing:
    meta = DrawingMetadata(
        layers=list(r.layers),
        blocks=list(r.blocks),
        insert_count=r.insert_count,
        text_count=r.text_count,
        entity_counts=dict(r.entity_counts),
        bbox=BoundingBox.from_list(r.bbox),
    )
    return Drawing(
        id=r.id,
        project_id=r.project_id,
        filename=r.filename,
        sha256=r.sha256,
        stored_path=r.stored_path,
        metadata=meta,
        created_at=r.created_at,
    )


def _object(r: DXFObjectRecord) -> DrawingObject:
    base = DrawingObject(
        handle=r.handle,
        entity_type=r.entity_type,
        layer=r.layer,
        bbox=BoundingBox(*r.bbox),
        block_name=r.block_name,
        text=r.text,
        attributes=dict(r.attributes),
        primitives=tuple(r.primitives),
        connection_segments=tuple(
            (
                (float(segment[0][0]), float(segment[0][1])),
                (float(segment[1][0]), float(segment[1][1])),
            )
            for segment in (r.connection_segments or [])
        ),
    )
    return replace(base, id=r.id)


def _asset(r: AssetRecord) -> Asset:
    return Asset(
        id=r.id,
        name=r.name,
        description=r.description,
        sector=r.sector,
        customer_need=r.customer_need,
        tags=tuple(r.tags),
        created_at=r.created_at,
        drawing_id=r.drawing_id,
    )
