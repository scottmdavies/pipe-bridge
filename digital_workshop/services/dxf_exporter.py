"""Export selected modelspace entities while retaining their source DXF definitions."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import ezdxf

_LOGGER = logging.getLogger(__name__)


class DxfExportError(Exception):
    """Raised when selected source entities cannot be exported."""


class DxfExporter:
    """Create a new DXF containing selected source entities and original block definitions."""

    def export(self, source: Path, entity_handles: set[str]) -> bytes:
        """Return a DXF copy containing only modelspace entities identified by their handles."""
        if not entity_handles:
            raise DxfExportError("Select at least one object to export.")
        try:
            document = ezdxf.readfile(source)
            modelspace = document.modelspace()
            xref_names = {
                block.name for block in document.blocks if int(block.block.dxf.get("flags", 0)) & 12
            }
            found: set[str] = set()
            for entity in list(modelspace):
                handle = entity.dxf.handle
                if handle in entity_handles:
                    if entity.dxftype() == "INSERT" and entity.dxf.name in xref_names:
                        raise DxfExportError(
                            "Selected object is an external reference and cannot be exported alone."
                        )
                    found.add(handle)
                else:
                    modelspace.delete_entity(entity)
            missing = entity_handles - found
            if missing:
                raise DxfExportError(
                    f"Source drawing is missing {len(missing)} selected object(s)."
                )
            for layout in document.layouts:
                if layout.name != "Model":
                    layout.delete_all_entities()
            for name in xref_names:
                document.blocks.delete_block(name, safe=False)
            auditor = document.audit()
            if auditor.errors:
                raise DxfExportError(
                    f"DXF audit found {len(auditor.errors)} unrecoverable issue(s)."
                )
            if auditor.fixes:
                _LOGGER.warning("Repaired %s DXF issue(s) during asset export.", len(auditor.fixes))
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory, "asset.dxf")
                document.saveas(output)
                return output.read_bytes()
        except DxfExportError:
            raise
        except (OSError, ezdxf.DXFError) as exc:
            raise DxfExportError(f"Unable to export DXF: {exc}") from exc
