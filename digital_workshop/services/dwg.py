"""DWG to DXF conversion via an external converter (LibreDWG ``dwg2dxf``)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

_DWG_MAGIC = b"AC10"
_TIMEOUT_SECONDS = 120


class DwgConversionError(Exception):
    """Raised when a DWG file cannot be converted."""


def is_dwg(content: bytes) -> bool:
    """Return True if ``content`` starts with a DWG version signature (AC10xx)."""
    return content.startswith(_DWG_MAGIC)


class DwgConverter:
    """Converts DWG bytes to DXF bytes using the ``dwg2dxf`` command line tool."""

    def __init__(self, executable: str = "dwg2dxf") -> None:
        """Create a converter that runs ``executable`` (looked up on ``PATH``)."""
        self._executable = executable

    @property
    def available(self) -> bool:
        """Whether the converter executable can be found."""
        return shutil.which(self._executable) is not None

    def convert(self, content: bytes) -> bytes:
        """Convert DWG ``content`` to DXF bytes.

        Raises:
            DwgConversionError: If the tool is missing, fails or produces no output.
        """
        exe = shutil.which(self._executable)
        if exe is None:
            raise DwgConversionError(
                "DWG upload needs the 'dwg2dxf' tool (LibreDWG) on PATH; "
                "install it or convert the file to DXF first."
            )
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp, "in.dwg"), Path(tmp, "out.dxf")
            src.write_bytes(content)
            try:
                subprocess.run(  # noqa: S603 - fixed argv, no shell, temp paths only
                    [exe, "-y", "-o", str(dest), str(src)],
                    check=False,
                    capture_output=True,
                    timeout=_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as exc:
                raise DwgConversionError("DWG conversion timed out.") from exc
            # dwg2dxf may exit non-zero on warnings yet still write usable output
            if not dest.exists() or dest.stat().st_size == 0:
                raise DwgConversionError("DWG conversion failed; the file may be unsupported.")
            return dest.read_bytes()
