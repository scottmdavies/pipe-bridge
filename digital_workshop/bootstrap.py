"""Composition root: wires concrete implementations together (dependency injection)."""

from __future__ import annotations

from sqlalchemy import Engine

from digital_workshop.config import Settings
from digital_workshop.db.repositories import UnitOfWork
from digital_workshop.db.session import create_db_engine, create_session_factory
from digital_workshop.services.assets import AssetCreator
from digital_workshop.services.dxf_parser import DxfParser
from digital_workshop.services.graph import GraphBuilder
from digital_workshop.services.relationships import (
    LayerStrategy,
    ProximityStrategy,
    RelationshipEngine,
)
from digital_workshop.services.selection import SelectionService
from digital_workshop.services.storage import FileStore
from digital_workshop.services.svg_renderer import SvgRenderer
from digital_workshop.services.workshop import WorkshopService


def build_services(
    settings: Settings, engine: Engine | None = None
) -> tuple[WorkshopService, SelectionService]:
    """Create the application services for the given settings."""
    engine = engine or create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    def uow_factory() -> UnitOfWork:
        return UnitOfWork(session_factory)

    relationship_engine = RelationshipEngine(
        [ProximityStrategy(settings.proximity_threshold), LayerStrategy()]
    )
    workshop = WorkshopService(
        uow_factory=uow_factory,
        parser=DxfParser(),
        store=FileStore(settings.upload_dir),
        renderer=SvgRenderer(),
        assets=AssetCreator(uow_factory, relationship_engine),
        graphs=GraphBuilder(),
        max_upload_bytes=settings.max_upload_bytes,
    )
    return workshop, SelectionService()
