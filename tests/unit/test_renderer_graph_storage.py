from pathlib import Path

from digital_workshop.domain.models import BoundingBox, DrawingObject
from digital_workshop.services.storage import FileStore
from digital_workshop.services.svg_renderer import SvgRenderer

BOX = BoundingBox(0, 0, 10, 10)
OBJECTS = [
    DrawingObject(
        "1",
        "INSERT",
        'LAY"ER',
        BOX,
        block_name="TANK",
        text="T-1",
        primitives=(
            {"t": "poly", "pts": [[0, 0], [1, 1]], "closed": False},
            {"t": "poly", "pts": [[0, 0], [1, 1], [0, 1]], "closed": True},
            {"t": "text", "p": [1, 1], "s": "<b>&", "h": 0.5},
        ),
        id=1,
    ),
    DrawingObject("2", "LINE", "PIPE", BOX, id=2),
]


def test_svg_marks_selection_hidden_layers_and_escapes() -> None:
    svg = SvgRenderer().render(OBJECTS, BOX, frozenset({1}), frozenset({"PIPE"}))
    assert 'class="obj sel" data-id="1"' in svg
    assert 'class="obj hidden" data-id="2"' in svg
    assert "&lt;b&gt;&amp;" in svg and "LAY&quot;ER" in svg
    assert "<polyline" in svg and "<polygon" in svg
    assert 'id="dxf-svg"' in svg
    assert 'data-home="' in svg


def test_svg_without_bbox_still_renders() -> None:
    assert "<svg" in SvgRenderer().render([], None)


def test_file_store_is_content_addressed_and_write_once(tmp_path: Path) -> None:
    store = FileStore(tmp_path / "up")
    digest, path = store.save(b"abc")
    mtime = path.stat().st_mtime_ns
    digest2, path2 = store.save(b"abc")
    assert (digest, path) == (digest2, path2)
    assert path.read_bytes() == b"abc"
    assert path.stat().st_mtime_ns == mtime
    assert path.name == f"{digest}.dxf"
