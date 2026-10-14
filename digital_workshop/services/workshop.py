"""Application service used by the UI: orchestrates import, viewing and assets."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from pathlib import Path

from digital_workshop.db.repositories import UnitOfWork
from digital_workshop.domain.models import (
    Asset,
    AssetDetail,
    AssetObjectSuggestion,
    AssetRequest,
    CostItem,
    Drawing,
    DrawingObject,
    Relationship,
)
from digital_workshop.services.assets import AssetCreator, AssetValidationError
from digital_workshop.services.dwg import DwgConversionError, DwgConverter, is_dwg
from digital_workshop.services.dxf_exporter import DxfExporter, DxfExportError
from digital_workshop.services.dxf_normalization import DxfNormalizer
from digital_workshop.services.dxf_parser import DxfParser
from digital_workshop.services.storage import FileStore
from digital_workshop.services.svg_renderer import SvgRenderer

DEFAULT_PROJECT = "Default Project"
_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]")
_LOGGER = logging.getLogger(__name__)


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
        exporter: DxfExporter,
        max_upload_bytes: int,
        dwg_converter: DwgConverter | None = None,
    ) -> None:
        """Create the service from injected collaborators."""
        self._uow_factory = uow_factory
        self._parser = parser
        self._store = store
        self._renderer = renderer
        self._assets = assets
        self._exporter = exporter
        self._max_upload_bytes = max_upload_bytes
        self._dwg_converter = dwg_converter
        self._dxf_normalizer = DxfNormalizer()

    def import_drawing(
        self, filename: str, content: bytes, project_name: str = DEFAULT_PROJECT
    ) -> Drawing:
        """Import a DXF (or DWG, converted first): keep a read-only copy, extract and store objects.

        Raises:
            DrawingImportError: If the file is too large, empty or not a valid DXF/DWG.
        """
        if not content:
            raise DrawingImportError("The uploaded file is empty.")
        if len(content) > self._max_upload_bytes:
            raise DrawingImportError("The uploaded file is too large.")
        if is_dwg(content):
            if self._dwg_converter is None:
                raise DrawingImportError("DWG files are not supported; upload a DXF.")
            try:
                content = self._dwg_converter.convert(content)
            except DwgConversionError as exc:
                raise DrawingImportError(str(exc)) from exc
            result = self._dxf_normalizer.normalize(content)
            content = result.content
            if result.applied_rules:
                _LOGGER.warning("Applied DXF normalizations: %s", ", ".join(result.applied_rules))
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

    def update_asset_relationships(self, asset_id: int, relationships: list[Relationship]) -> None:
        """Persist the user's reviewed relationship list for an asset."""
        try:
            self._assets.replace_relationships(asset_id, relationships)
        except ValueError as exc:
            raise AssetValidationError(str(exc)) from exc

    def update_asset_cost_items(self, asset_id: int, cost_items: list[CostItem]) -> None:
        """Persist the reviewed, unmarked-up cost schedule for an asset."""
        self._assets.replace_cost_items(asset_id, cost_items)

    def suggest_asset_additions(
        self, asset_id: int, tolerance: float
    ) -> list[AssetObjectSuggestion]:
        """Find unselected annotations and objects near an asset's selected linework."""
        return self._assets.suggest_additions(asset_id, tolerance)

    def include_asset_suggestions(self, asset_id: int, object_ids: set[int]) -> None:
        """Include user-confirmed nearby objects in the asset."""
        self._assets.include_suggestions(asset_id, object_ids)

    def list_assets(self) -> list[Asset]:
        """List all saved assets."""
        with self._uow_factory() as uow:
            return uow.assets.list()

    def get_asset(self, asset_id: int) -> AssetDetail | None:
        """Load an asset with objects and relationships."""
        with self._uow_factory() as uow:
            return uow.assets.get_detail(asset_id)

    def export_asset_dxf(self, asset_id: int) -> tuple[str, bytes] | None:
        """Export an asset as a new DXF, preserving source block definitions."""
        detail = self.get_asset(asset_id)
        if detail is None or detail.asset.drawing_id is None:
            return None
        drawing = self.get_drawing(detail.asset.drawing_id)
        if drawing is None:
            return None
        filename = _UNSAFE.sub("_", detail.asset.name).strip(" .") or "asset"
        try:
            content = self._exporter.export(
                Path(drawing.stored_path), {obj.handle for obj in detail.objects}
            )
        except DxfExportError:
            raise
        return f"{filename}.dxf", content
