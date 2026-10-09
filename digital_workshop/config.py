"""Application settings, read from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATABASE_URL = "postgresql+psycopg2://localhost:5432/workshop"


@dataclass(frozen=True)
class Settings:
    """Runtime configuration.

    Attributes:
        database_url: SQLAlchemy URL of the PostgreSQL database.
        upload_dir: Directory where uploaded DXF files are stored (write-once copies).
        max_upload_bytes: Maximum accepted DXF upload size.
        proximity_threshold: Maximum bounding-box gap (drawing units) for a proximity relationship.
    """

    database_url: str = DEFAULT_DATABASE_URL
    upload_dir: Path = Path("var/uploads")
    max_upload_bytes: int = 50 * 1024 * 1024
    proximity_threshold: float = 50.0

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from ``DATABASE_URL``, ``UPLOAD_DIR`` and related variables."""
        return cls(
            database_url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
            upload_dir=Path(os.environ.get("UPLOAD_DIR", "var/uploads")),
            max_upload_bytes=int(os.environ.get("MAX_UPLOAD_BYTES", 50 * 1024 * 1024)),
            proximity_threshold=float(os.environ.get("PROXIMITY_THRESHOLD", 50.0)),
        )
