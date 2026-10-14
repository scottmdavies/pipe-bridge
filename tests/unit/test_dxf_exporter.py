from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from digital_workshop.services.dxf_exporter import DxfExporter, DxfExportError


def test_export_removes_paperspace_xref_and_keeps_linetype(tmp_path: Path) -> None:
    source = tmp_path / "source.dxf"
    document = ezdxf.new("R2018")
    document.linetypes.new("HIDDEN2", dxfattribs={"pattern": [0.5, 0.25, -0.25]})
    line = document.modelspace().add_line((0, 0), (10, 0), dxfattribs={"linetype": "HIDDEN2"})
    document.blocks.new(
        "A1BB-SHEET",
        dxfattribs={"flags": ezdxf.const.BLK_XREF, "xref_path": r"G:\acad\REF\A1BB-SHEET.dwg"},
    )
    document.layouts.get("Layout1").add_blockref("A1BB-SHEET", (0, 0))
    document.saveas(source)

    content = DxfExporter().export(source, {line.dxf.handle})
    output = tmp_path / "exported.dxf"
    output.write_bytes(content)
    exported = ezdxf.readfile(output)
    audit = exported.audit()

    assert [entity.dxf.handle for entity in exported.modelspace()] == [line.dxf.handle]
    assert exported.linetypes.has_entry("HIDDEN2")
    assert list(exported.layouts.get("Layout1")) == []
    assert not any(int(block.block.dxf.get("flags", 0)) & 12 for block in exported.blocks)
    assert not audit.errors and not audit.fixes


def test_export_rejects_selected_xref_insert(tmp_path: Path) -> None:
    source = tmp_path / "source.dxf"
    document = ezdxf.new("R2018")
    document.blocks.new(
        "MISSING-DRAWING",
        dxfattribs={"flags": ezdxf.const.BLK_XREF, "xref_path": "missing.dwg"},
    )
    reference = document.modelspace().add_blockref("MISSING-DRAWING", (0, 0))
    document.saveas(source)

    with pytest.raises(DxfExportError, match="external reference"):
        DxfExporter().export(source, {reference.dxf.handle})
