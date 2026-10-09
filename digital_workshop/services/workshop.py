"""Application service used by the UI: orchestrates import, viewing and assets."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from digital_workshop.db.repositories import UnitOfWork
from digital_workshop.domain.models import (
    Asset,
    AssetDetail,
    AssetRequest,
    Drawing,
    DrawingObject,
)
from digital_workshop.services.assets import AssetCreator
from digital_workshop.services.dxf_parser import DxfParser
from digital_workshop.services.graph import GraphBuilder
from digital_workshop.services.storage import FileStore
from digital_workshop.services.svg_renderer import SvgRenderer

DEFAULT_PROJECT = "Default Project"
_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]")


class DrawingImportError(Exception):
    """Raised when an uploaded file cannot be imported."""


class WorkshopService:
    """Facade over the application services; contains no UI code."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        parser: DxfParser,
        store: FileStore,
        renderer: SvgRenderer,
        assets: AssetCreator,
        graphs: GraphBuilder,
        max_upload_bytes: int,
    ) -> None:
        """Create the service from injected collaborators."""
        self._uow_factory = uow_factory
        self._parser = parser
        self._store = store
        self._renderer = renderer
        self._assets = assets
        self._graphs = graphs
        self._max_upload_bytes = max_upload_bytes

    def import_drawing(
        self, filename: str, content: bytes, project_name: str = DEFAULT_PROJECT
    ) -> Drawing:
        """Import a DXF: keep a read-only copy, extract metadata and objects, store them.

        Raises:
            DrawingImportError: If the file is too large, empty or not a valid DXF.
        """
        if not content:
            raise DrawingImportError("The uploaded file is empty.")
        if len(content) > self._max_upload_bytes:
            raise DrawingImportError("The uploaded file is too large.")
        safe_name = _UNSAFE.sub("_", Path(filename).name)[:255] or "drawing.dxf"
        digest, path = self._store.save(content)
        try:
            parsed = self._parser.parse(path)
        except Exception as exc:
            raise DrawingImportError(str(exc)) from exc
        with self._uow_factory() as uow:
            project = uow.projects.get_or_create(project_name.strip() or DEFAULT_PROJECT)
            return uow.drawings.add(project.id, safe_name, digest, str(path), parsed)

    def list_drawings(self) -> list[Drawing]:
        """List all imported drawings."""
        with self._uow_factory() as uow:
            return uow.drawings.list_all()

    def get_drawing(self, drawing_id: int) -> Drawing | None:
        """Fetch one drawing."""
        with self._uow_factory() as uow:
            return uow.drawings.get(drawing_id)

    def get_objects(self, drawing_id: int) -> list[DrawingObject]:
        """Fetch all objects of a drawing."""
        with self._uow_factory() as uow:
            return uow.drawings.list_objects(drawing_id)

    def render_drawing(self, drawing: Drawing, objects: list[DrawingObject]) -> str:
        """Render a drawing's objects as SVG."""
        return self._renderer.render(objects, drawing.metadata.bbox)

    def create_asset(
        self, drawing_id: int, object_ids: frozenset[int], request: AssetRequest
    ) -> AssetDetail:
        """Create an asset from the selected objects."""
        return self._assets.create(drawing_id, object_ids, request)

    def list_assets(self) -> list[Asset]:
        """List all saved assets."""
        with self._uow_factory() as uow:
            return uow.assets.list()

    def get_asset(self, asset_id: int) -> AssetDetail | None:
        """Load an asset with objects and relationships."""
        with self._uow_factory() as uow:
            return uow.assets.get_detail(asset_id)

    def asset_graph_html(self, asset_id: int) -> str | None:
        """Render an asset's relationship graph as PyVis HTML."""
        detail = self.get_asset(asset_id)
        if detail is None:
            return None
        return self._graphs.to_html(self._graphs.build(detail))
