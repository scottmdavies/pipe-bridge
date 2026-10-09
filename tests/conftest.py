from __future__ import annotations

from pathlib import Path

import ezdxf
import pytest

from digital_workshop.bootstrap import build_services
from digital_workshop.config import Settings
from digital_workshop.services.selection import SelectionService
from digital_workshop.services.workshop import WorkshopService


def make_sample_dxf(path: Path) -> Path:
    """Tank -> valve -> pump -> tank with pipes, a label and misc entities."""
    doc = ezdxf.new("R2018")
    for layer in ("EQUIP", "VALVES", "PIPE", "TEXT"):
        doc.layers.add(layer)
    for name, pts in {
        "TANK": [(0, 0), (4, 0), (4, 6), (0, 6)],
        "VALVE": [(0, 0), (1, 0.5), (0, 1), (1, 0.5)],
        "PUMP": [(0, 0), (2, 0), (2, 2), (0, 2)],
    }.items():
        block = doc.blocks.new(name)
        block.add_lwpolyline(pts, close=True)
        block.add_attdef("TAG", (0, -1))
        block.add_attdef("SIZE", (0, -2))
    msp = doc.modelspace()
    for block, pos, tag, size, layer in [
        ("TANK", (0, 0), "T-101", "", "EQUIP"),
        ("VALVE", (8, 2), "V-101", "DN50", "VALVES"),
        ("PUMP", (12, 1), "P-101", "DN50", "EQUIP"),
        ("TANK", (20, 0), "T-102", "", "EQUIP"),
    ]:
        ref = msp.add_blockref(block, pos, dxfattribs={"layer": layer})
        ref.add_auto_attribs({"TAG": tag, "SIZE": size})
    msp.add_lwpolyline([(4, 3), (8, 3)], dxfattribs={"layer": "PIPE"})
    msp.add_line((9, 2.5), (12, 2.5), dxfattribs={"layer": "PIPE"})
    msp.add_lwpolyline([(14, 2), (17, 2), (17, 3), (20, 3)], dxfattribs={"layer": "PIPE"})
    msp.add_text("L-001", height=0.3, dxfattribs={"layer": "TEXT", "insert": (5, 3.3)})
    msp.add_circle((10, 8), 1, dxfattribs={"layer": "PIPE"})
    msp.add_arc((10, 8), 2, 0, 90, dxfattribs={"layer": "PIPE"})
    msp.add_mtext("Note", dxfattribs={"layer": "TEXT", "insert": (0, 9), "char_height": 0.5})
    doc.saveas(path)
    return path


@pytest.fixture
def sample_dxf(tmp_path: Path) -> Path:
    return make_sample_dxf(tmp_path / "sample.dxf")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url="sqlite://", upload_dir=tmp_path / "uploads", proximity_threshold=2.0
    )


@pytest.fixture
def services(settings: Settings) -> tuple[WorkshopService, SelectionService]:
    return build_services(settings)


@pytest.fixture
def workshop(services: tuple[WorkshopService, SelectionService]) -> WorkshopService:
    return services[0]
