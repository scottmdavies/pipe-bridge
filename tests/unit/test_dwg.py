from __future__ import annotations

import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from digital_workshop.services.dwg import DwgConversionError, DwgConverter, is_dwg
from digital_workshop.services.workshop import DrawingImportError

DWG = b"AC1032" + b"\x00" * 16


def _fake_tool(tmp_path: Path, body: str) -> str:
    script = tmp_path / "fake_dwg2dxf"
    script.write_text(f"#!/bin/sh\n{body}\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_is_dwg():
    assert is_dwg(DWG)
    assert not is_dwg(b"  0\nSECTION\n")


def test_missing_tool():
    converter = DwgConverter("definitely-not-installed-dwg2dxf")
    assert not converter.available
    with pytest.raises(DwgConversionError, match="dwg2dxf"):
        converter.convert(DWG)


def test_convert_success(tmp_path):
    # args: -y -o <dest> <src>
    converter = DwgConverter(_fake_tool(tmp_path, 'printf DXFDATA > "$3"'))
    assert converter.available
    assert converter.convert(DWG) == b"DXFDATA"


def test_convert_no_output(tmp_path):
    with pytest.raises(DwgConversionError, match="failed"):
        DwgConverter(_fake_tool(tmp_path, "exit 1")).convert(DWG)


def test_import_dwg_converts_to_dxf(workshop, sample_dxf):
    dxf = sample_dxf.read_bytes()
    workshop._dwg_converter = SimpleNamespace(convert=lambda content: dxf)
    drawing = workshop.import_drawing("plant.dwg", DWG)
    assert drawing.filename == "plant.dwg"


def test_import_dwg_without_converter(workshop):
    workshop._dwg_converter = None
    with pytest.raises(DrawingImportError, match="DWG"):
        workshop.import_drawing("plant.dwg", DWG)


def test_import_dwg_conversion_error(workshop, monkeypatch):
    def boom(content):
        raise DwgConversionError("nope")

    monkeypatch.setattr(workshop, "_dwg_converter", SimpleNamespace(convert=boom))
    with pytest.raises(DrawingImportError, match="nope"):
        workshop.import_drawing("plant.dwg", DWG)
