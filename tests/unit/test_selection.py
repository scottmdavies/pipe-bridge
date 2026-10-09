from digital_workshop.domain.models import BoundingBox, DrawingObject
from digital_workshop.services.selection import SelectionService

svc = SelectionService()


def obj(i: int, x: float, layer: str = "L") -> DrawingObject:
    return DrawingObject(str(i), "INSERT", layer, BoundingBox(x, 0, x + 2, 2), id=i)


A, B, C = obj(1, 0), obj(2, 10), obj(3, 20, "HIDDEN")
ALL = [A, B, C]


def test_hit_test_prefers_smallest_object() -> None:
    big = DrawingObject("9", "LWPOLYLINE", "L", BoundingBox(-5, -5, 30, 30), id=9)
    assert svc.hit_test([big, A], 1, 1) is A
    assert svc.hit_test(ALL, 50, 50) is None
    assert svc.hit_test(ALL, 2.4, 1, tolerance=0.5) is A


def test_plain_click_toggles_included_excluded() -> None:
    selected = svc.click(frozenset(), A)
    assert selected == {1}
    assert svc.click(selected, A) == frozenset()
    assert svc.click(selected, B) == {2}
    assert svc.click(selected, None) == frozenset()


def test_multi_select_modifiers() -> None:
    assert svc.click(frozenset({1}), B, shift=True) == {1, 2}
    assert svc.click(frozenset({1, 2}), B, shift=True) == {1, 2}
    assert svc.click(frozenset({1}), B, ctrl=True) == {1, 2}
    assert svc.click(frozenset({1, 2}), B, ctrl=True) == {1}
    assert svc.click(frozenset({1}), None, ctrl=True) == {1}


def test_box_select_replace_and_additive() -> None:
    assert svc.box_select(frozenset({3}), ALL, -1, -1, 5, 5) == {1}
    assert svc.box_select(frozenset({3}), ALL, 5, 5, -1, -1, additive=True) == {1, 3}
    assert svc.box_select(frozenset(), ALL, 0.5, 0.5, 1, 1) == frozenset()
    assert svc.box_select(frozenset(), ALL, -1, -1, 13, 3) == {1, 2}


def test_hidden_layers_are_not_selectable() -> None:
    visible = svc.visible(ALL, frozenset({"HIDDEN"}))
    assert C not in visible
    assert svc.box_select(frozenset(), visible, -1, -1, 30, 5) == {1, 2}
