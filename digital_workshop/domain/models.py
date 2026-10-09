"""Plain domain models shared by services, repositories and the UI."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned bounding box in drawing coordinates."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        """Horizontal extent."""
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        """Vertical extent."""
        return self.max_y - self.min_y

    @property
    def area(self) -> float:
        """Area of the box."""
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        """Centre point."""
        return (self.min_x + self.max_x) / 2, (self.min_y + self.max_y) / 2

    def contains_point(self, x: float, y: float, tolerance: float = 0.0) -> bool:
        """Return True if the point lies within the box expanded by ``tolerance``."""
        return (
            self.min_x - tolerance <= x <= self.max_x + tolerance
            and self.min_y - tolerance <= y <= self.max_y + tolerance
        )

    def contains(self, other: BoundingBox) -> bool:
        """Return True if ``other`` lies entirely within this box."""
        return (
            self.min_x <= other.min_x
            and self.min_y <= other.min_y
            and self.max_x >= other.max_x
            and self.max_y >= other.max_y
        )

    def gap(self, other: BoundingBox) -> float:
        """Shortest distance between two boxes (0 when they touch or overlap)."""
        dx = max(other.min_x - self.max_x, self.min_x - other.max_x, 0.0)
        dy = max(other.min_y - self.max_y, self.min_y - other.max_y, 0.0)
        return math.hypot(dx, dy)

    def union(self, other: BoundingBox) -> BoundingBox:
        """Smallest box containing both boxes."""
        return BoundingBox(
            min(self.min_x, other.min_x),
            min(self.min_y, other.min_y),
            max(self.max_x, other.max_x),
            max(self.max_y, other.max_y),
        )

    def as_list(self) -> list[float]:
        """Return the serialisable ``[min_x, min_y, max_x, max_y]`` form."""
        return [self.min_x, self.min_y, self.max_x, self.max_y]

    @classmethod
    def from_list(cls, values: list[float] | None) -> BoundingBox | None:
        """Inverse of :meth:`as_list`; ``None`` passes through."""
        return cls(*values) if values else None


@dataclass(frozen=True)
class DrawingObject:
    """A selectable top-level modelspace entity.

    Attributes:
        handle: DXF entity handle (unique within the drawing).
        entity_type: DXF type, e.g. ``INSERT`` or ``LWPOLYLINE``.
        layer: Layer name.
        bbox: Bounding box of the entity.
        block_name: Block name for ``INSERT`` entities.
        text: Text content or the tag attribute / first attribute of an ``INSERT``.
        attributes: Block attribute values of an ``INSERT``.
        primitives: Simplified drawable geometry used for SVG rendering.
        id: Database id, ``None`` until stored.
    """

    handle: str
    entity_type: str
    layer: str
    bbox: BoundingBox
    block_name: str | None = None
    text: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)
    primitives: tuple[dict[str, Any], ...] = ()
    id: int | None = None

    @property
    def label(self) -> str:
        """Human readable label used in graphs and lists."""
        return self.text or self.block_name or f"{self.entity_type} {self.handle}"


@dataclass(frozen=True)
class DrawingMetadata:
    """Summary information extracted from a DXF."""

    layers: list[str]
    blocks: list[str]
    insert_count: int
    text_count: int
    entity_counts: dict[str, int]
    bbox: BoundingBox | None


@dataclass(frozen=True)
class ParsedDrawing:
    """Result of parsing a DXF file."""

    metadata: DrawingMetadata
    objects: list[DrawingObject]


@dataclass(frozen=True)
class Project:
    """A customer project containing drawings."""

    id: int
    name: str
    created_at: datetime


@dataclass(frozen=True)
class Drawing:
    """An imported DXF drawing (the source file itself is never modified)."""

    id: int
    project_id: int
    filename: str
    sha256: str
    stored_path: str
    metadata: DrawingMetadata
    created_at: datetime


@dataclass(frozen=True)
class Relationship:
    """Directed relationship between two drawing objects (by database id)."""

    source_id: int
    target_id: int
    relation_type: str
    distance: float | None = None


@dataclass(frozen=True)
class AssetRequest:
    """User input required to create an asset."""

    name: str
    description: str = ""
    sector: str = ""
    customer_need: str = ""
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Asset:
    """A reusable, productised selection of drawing objects."""

    id: int
    name: str
    description: str
    sector: str
    customer_need: str
    tags: tuple[str, ...]
    created_at: datetime
    drawing_id: int | None = None


@dataclass(frozen=True)
class AssetDetail:
    """An asset together with its objects and relationships."""

    asset: Asset
    objects: list[DrawingObject]
    relationships: list[Relationship]
