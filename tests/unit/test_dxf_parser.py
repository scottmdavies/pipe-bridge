import hashlib
from pathlib import Path

import ezdxf
import pytest

from digital_workshop.services.dxf_parser import DxfParseError, DxfParser


def test_metadata_extraction(sample_dxf: Path) -> None:
    parsed = DxfParser().parse(sample_dxf)
    meta = parsed.metadata
    assert {"EQUIP", "VALVES", "PIPE", "TEXT"} <= set(meta.layers)
    assert meta.blocks == ["PUMP", "TANK", "VALVE"]
    assert meta.insert_count == 4
    assert meta.text_count == 2
    assert meta.entity_counts["INSERT"] == 4
    assert meta.entity_counts["LWPOLYLINE"] == 2
    assert meta.bbox is not None
    assert meta.bbox.min_x == 0.0


def test_objects_and_attributes(sample_dxf: Path) -> None:
    parsed = DxfParser().parse(sample_dxf)
    by_label = {o.label: o for o in parsed.objects}
    tank = by_label["T-101"]
    assert tank.entity_type == "INSERT"
    assert tank.block_name == "TANK"
    assert tank.layer == "EQUIP"
    assert (tank.bbox.min_x, tank.bbox.max_x, tank.bbox.max_y) == (0.0, 4.0, 6.0)
    assert by_label["V-101"].attributes == {"TAG": "V-101", "SIZE": "DN50"}
    assert by_label["Note"].entity_type == "MTEXT"
    assert any(p["t"] == "text" for p in by_label["L-001"].primitives)
    assert any(p["t"] == "poly" for p in tank.primitives)
    pipe_line = next(o for o in parsed.objects if o.entity_type == "LINE" and o.layer == "PIPE")
    assert pipe_line.connection_segments == (((9.0, 2.5), (12.0, 2.5)),)
    pipe_path = next(
        o
        for o in parsed.objects
        if o.entity_type == "LWPOLYLINE" and o.layer == "PIPE" and len(o.connection_segments) == 3
    )
    assert pipe_path.connection_segments == (
        ((14.0, 2.0), (17.0, 2.0)),
        ((17.0, 2.0), (17.0, 3.0)),
        ((17.0, 3.0), (20.0, 3.0)),
    )
    assert len(parsed.objects) == 11


def test_parsing_never_modifies_source(sample_dxf: Path) -> None:
    before = hashlib.sha256(sample_dxf.read_bytes()).hexdigest()
    DxfParser().parse(sample_dxf)
    assert hashlib.sha256(sample_dxf.read_bytes()).hexdigest() == before


def test_extracts_segments_from_legacy_polyline(tmp_path: Path) -> None:
    path = tmp_path / "legacy-polyline.dxf"
    document = ezdxf.new("R2018")
    document.modelspace().add_polyline2d([(1, 2), (4, 2), (4, 7)])
    document.saveas(path)

    parsed = DxfParser().parse(path)

    assert parsed.objects[0].connection_segments == (
        ((1.0, 2.0), (4.0, 2.0)),
        ((4.0, 2.0), (4.0, 7.0)),
    )


def test_invalid_file_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.dxf"
    bad.write_text("this is not a dxf")
    with pytest.raises(DxfParseError):
        DxfParser().parse(bad)
    with pytest.raises(DxfParseError):
        DxfParser().parse(tmp_path / "missing.dxf")
