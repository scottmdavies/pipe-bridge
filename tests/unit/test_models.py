from digital_workshop.domain.models import BoundingBox, DrawingObject


def test_bbox_geometry() -> None:
    a = BoundingBox(0, 0, 4, 6)
    assert (a.width, a.height, a.area, a.center) == (4, 6, 24, (2, 3))
    assert a.contains_point(1, 1)
    assert not a.contains_point(5, 1)
    assert a.contains_point(5, 1, tolerance=1.5)
    assert a.contains(BoundingBox(1, 1, 2, 2))
    assert not a.contains(BoundingBox(1, 1, 5, 2))


def test_bbox_gap_union_roundtrip() -> None:
    a, b = BoundingBox(0, 0, 1, 1), BoundingBox(4, 5, 6, 7)
    assert a.gap(b) == 5.0
    assert a.gap(BoundingBox(0.5, 0.5, 2, 2)) == 0.0
    assert a.union(b) == BoundingBox(0, 0, 6, 7)
    assert BoundingBox.from_list(a.as_list()) == a
    assert BoundingBox.from_list(None) is None


def test_object_label_fallbacks() -> None:
    box = BoundingBox(0, 0, 1, 1)
    assert DrawingObject("A", "INSERT", "L", box, block_name="TANK", text="T-1").label == "T-1"
    assert DrawingObject("A", "INSERT", "L", box, block_name="TANK").label == "TANK"
    assert DrawingObject("A", "LINE", "L", box).label == "LINE A"
