"""DXF parsing: metadata extraction and selectable object discovery (read-only)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import bbox as ezbbox
from ezdxf import path as ezpath
from ezdxf.entities import DXFEntity

from digital_workshop.domain.models import (
    BoundingBox,
    DrawingMetadata,
    DrawingObject,
    ParsedDrawing,
)

SELECTABLE_TYPES = frozenset(
    {
        "INSERT",
        "TEXT",
        "MTEXT",
        "LINE",
        "LWPOLYLINE",
        "POLYLINE",
        "CIRCLE",
        "ARC",
        "ELLIPSE",
        "SPLINE",
    }
)
TAG_ATTRIBUTE_NAMES = ("TAG", "NAME", "ID")
MAX_INSERT_DEPTH = 3
FLATTEN_DIVISOR = 200.0
DECIMALS = 4


class DxfParseError(Exception):
    """Raised when a file cannot be read as a DXF drawing."""


class DxfParser:
    """Read-only DXF reader built on ezdxf.

    The parser only ever opens the supplied file for reading.
    """

    def parse(self, path: Path) -> ParsedDrawing:
        """Parse a DXF file into metadata and selectable objects.

        Args:
            path: Path of the DXF file.

        Returns:
            Parsed metadata and the list of objects found in modelspace.

        Raises:
            DxfParseError: If the file is not a valid DXF.
        """
        try:
            doc = ezdxf.readfile(path)
        except (OSError, ezdxf.DXFError) as exc:
            raise DxfParseError(f"Unable to read DXF: {exc}") from exc

        modelspace = doc.modelspace()
        entities = list(modelspace)
        counts = Counter(entity.dxftype() for entity in entities)
        objects = [obj for entity in entities if (obj := self._to_object(entity)) is not None]

        bbox: BoundingBox | None = None
        for obj in objects:
            bbox = obj.bbox if bbox is None else bbox.union(obj.bbox)

        metadata = DrawingMetadata(
            layers=sorted(layer.dxf.name for layer in doc.layers),
            blocks=sorted(b.name for b in doc.blocks if not b.name.startswith("*")),
            insert_count=counts.get("INSERT", 0),
            text_count=counts.get("TEXT", 0) + counts.get("MTEXT", 0),
            entity_counts=dict(sorted(counts.items())),
            bbox=bbox,
        )
        return ParsedDrawing(metadata=metadata, objects=objects)

    def _to_object(self, entity: DXFEntity) -> DrawingObject | None:
        """Convert a modelspace entity into a DrawingObject, or None if unsupported."""
        entity_type = entity.dxftype()
        if entity_type not in SELECTABLE_TYPES:
            return None
        box = _entity_bbox(entity)
        if box is None:
            return None

        block_name: str | None = None
        text: str | None = None
        attributes: dict[str, str] = {}
        if entity_type == "INSERT":
            block_name = entity.dxf.name
            attributes = {a.dxf.tag: a.dxf.text for a in entity.attribs}
            text = _pick_tag(attributes)
        elif entity_type == "TEXT":
            text = entity.dxf.text
        elif entity_type == "MTEXT":
            text = entity.plain_text()

        scale = max(box.width, box.height)
        return DrawingObject(
            handle=entity.dxf.handle,
            entity_type=entity_type,
            layer=entity.dxf.layer,
            bbox=box,
            block_name=block_name,
            text=text or None,
            attributes=attributes,
            primitives=tuple(_primitives(entity, scale)),
        )


def _pick_tag(attributes: dict[str, str]) -> str | None:
    """Choose the most identifying attribute value of a block reference."""
    for name in TAG_ATTRIBUTE_NAMES:
        if attributes.get(name):
            return attributes[name]
    return next((v for v in attributes.values() if v), None)


def _entity_bbox(entity: DXFEntity) -> BoundingBox | None:
    """Compute an entity's bounding box, returning None when it has no extent."""
    try:
        # Block references are measured by their geometry only, so that attribute labels
        # (which may be long or oddly placed) do not inflate the selectable area.
        source = list(entity.virtual_entities()) if entity.dxftype() == "INSERT" else [entity]
        extents = ezbbox.extents(source)
    except Exception:  # noqa: BLE001 - malformed entities are skipped, not fatal
        return None
    if not extents.has_data:
        return None
    return BoundingBox(
        round(extents.extmin.x, DECIMALS),
        round(extents.extmin.y, DECIMALS),
        round(extents.extmax.x, DECIMALS),
        round(extents.extmax.y, DECIMALS),
    )


def _text_primitive(x: float, y: float, text: str, height: float) -> dict[str, Any]:
    return {
        "t": "text",
        "p": [round(x, DECIMALS), round(y, DECIMALS)],
        "s": text,
        "h": round(height or 1.0, DECIMALS),
    }


def _primitives(entity: DXFEntity, scale: float, depth: int = 0) -> list[dict[str, Any]]:
    """Reduce an entity to simple polyline / text primitives for rendering."""
    entity_type = entity.dxftype()
    if entity_type == "TEXT":
        x, y = entity.dxf.insert.x, entity.dxf.insert.y
        return [_text_primitive(x, y, entity.dxf.text, entity.dxf.height)]
    if entity_type == "MTEXT":
        x, y = entity.dxf.insert.x, entity.dxf.insert.y
        return [_text_primitive(x, y, entity.plain_text(), entity.dxf.char_height)]
    if entity_type == "INSERT":
        return _insert_primitives(entity, scale, depth)
    return _path_primitives(entity, scale)


def _insert_primitives(entity: DXFEntity, scale: float, depth: int) -> list[dict[str, Any]]:
    if depth >= MAX_INSERT_DEPTH:
        return []
    result: list[dict[str, Any]] = []
    try:
        children = list(entity.virtual_entities())
    except Exception:  # noqa: BLE001 - unresolved blocks render as empty
        children = []
    for child in children:
        result.extend(_primitives(child, scale, depth + 1))
    for attrib in entity.attribs:
        if attrib.dxf.text and not attrib.dxf.flags & 1:
            insert = attrib.dxf.insert
            result.append(_text_primitive(insert.x, insert.y, attrib.dxf.text, attrib.dxf.height))
    return result


def _path_primitives(entity: DXFEntity, scale: float) -> list[dict[str, Any]]:
    try:
        path = ezpath.make_path(entity)
    except Exception:  # noqa: BLE001 - unsupported geometry is simply not drawn
        return []
    distance = max(scale / FLATTEN_DIVISOR, 1e-6)
    result: list[dict[str, Any]] = []
    for sub in path.sub_paths():
        points = [[round(v.x, DECIMALS), round(v.y, DECIMALS)] for v in sub.flattening(distance)]
        if len(points) >= 2:
            result.append({"t": "poly", "pts": points, "closed": bool(sub.is_closed)})
    return result
