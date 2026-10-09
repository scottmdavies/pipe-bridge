"""Write-once storage for uploaded DXF files."""

from __future__ import annotations

import hashlib
from pathlib import Path


class FileStore:
    """Keeps an immutable, content-addressed copy of each uploaded DXF.

    Files are named by their SHA-256 digest, so user supplied file names never
    influence the storage path. Existing files are never overwritten.
    """

    def __init__(self, directory: Path) -> None:
        """Create a store rooted at ``directory``."""
        self._directory = directory

    def save(self, content: bytes) -> tuple[str, Path]:
        """Store ``content`` and return its SHA-256 digest and path."""
        digest = hashlib.sha256(content).hexdigest()
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / f"{digest}.dxf"
        if not path.exists():
            with path.open("xb") as handle:
                handle.write(content)
        return digest, path
