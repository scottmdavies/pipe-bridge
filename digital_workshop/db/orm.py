"""SQLAlchemy 2.0 ORM tables. Only the repository layer touches these classes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for all tables."""


class ProjectRecord(Base):
    """Table ``projects``."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DrawingRecord(Base):
    """Table ``drawings`` holding DXF metadata (never the DXF contents themselves)."""

    __tablename__ = "drawings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    stored_path: Mapped[str] = mapped_column(Text)
    layers: Mapped[list[str]] = mapped_column(JSON)
    blocks: Mapped[list[str]] = mapped_column(JSON)
    insert_count: Mapped[int] = mapped_column(Integer, default=0)
    text_count: Mapped[int] = mapped_column(Integer, default=0)
    entity_counts: Mapped[dict[str, int]] = mapped_column(JSON)
    bbox: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DXFObjectRecord(Base):
    """Table ``dxf_objects``: one row per selectable modelspace entity."""

    __tablename__ = "dxf_objects"
    __table_args__ = (UniqueConstraint("drawing_id", "handle"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    drawing_id: Mapped[int] = mapped_column(ForeignKey("drawings.id"), index=True)
    handle: Mapped[str] = mapped_column(String(32))
    entity_type: Mapped[str] = mapped_column(String(32))
    layer: Mapped[str] = mapped_column(String(255))
    block_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    attributes: Mapped[dict[str, str]] = mapped_column(JSON)
    bbox: Mapped[list[float]] = mapped_column(JSON)
    primitives: Mapped[list[dict[str, Any]]] = mapped_column(JSON)


class AssetRecord(Base):
    """Table ``assets``."""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    drawing_id: Mapped[int | None] = mapped_column(ForeignKey("drawings.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    sector: Mapped[str] = mapped_column(String(255), default="")
    customer_need: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    objects: Mapped[list[AssetObjectRecord]] = relationship(
        cascade="all, delete-orphan", order_by="AssetObjectRecord.id"
    )
    relationships: Mapped[list[RelationshipRecord]] = relationship(
        cascade="all, delete-orphan", order_by="RelationshipRecord.id"
    )


class AssetObjectRecord(Base):
    """Table ``asset_objects``: membership of a DXF object in an asset."""

    __tablename__ = "asset_objects"
    __table_args__ = (UniqueConstraint("asset_id", "dxf_object_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    dxf_object_id: Mapped[int] = mapped_column(ForeignKey("dxf_objects.id"))


class RelationshipRecord(Base):
    """Table ``relationships``: directed edge between two objects of an asset."""

    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    source_object_id: Mapped[int] = mapped_column(ForeignKey("dxf_objects.id"))
    target_object_id: Mapped[int] = mapped_column(ForeignKey("dxf_objects.id"))
    relation_type: Mapped[str] = mapped_column(String(64))
    distance: Mapped[float | None] = mapped_column(Float, nullable=True)
