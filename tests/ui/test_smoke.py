"""UI smoke tests: upload, select, save (NiceGUI user simulation, no browser)."""

from __future__ import annotations

from pathlib import Path

import pytest
from nicegui import ui
from nicegui.elements.upload_files import SmallFileUpload
from nicegui.testing import User

from digital_workshop.ui.pages import WorkshopPage, register_graph_route, register_pages

pytestmark = pytest.mark.nicegui_main_file("")


@pytest.fixture
def pages(services) -> list[WorkshopPage]:
    workshop, selection = services
    created: list[WorkshopPage] = []
    register_graph_route(workshop)

    @ui.page("/")
    def index() -> None:
        page = WorkshopPage(workshop, selection)
        created.append(page)
        page.build()

    return created


async def upload(user: User, path: Path, name: str | None = None) -> None:
    element = user.find(ui.upload).elements.pop()
    await element.handle_uploads(
        [SmallFileUpload(name or path.name, "application/dxf", path.read_bytes())]
    )


async def test_upload_select_and_save(user: User, pages, sample_dxf: Path) -> None:
    await user.open("/")
    await user.should_see("Briggs Digital Workshop")
    await upload(user, sample_dxf)
    await user.should_see("Imported sample.dxf")
    page = pages[0]
    state = page.state
    assert state.drawing is not None and state.drawing.filename == "sample.dxf"
    assert len(state.objects) == 11

    by_label = {o.label: o for o in state.objects}
    tank = by_label["T-101"]
    page.handle_click(2, 3)
    assert state.selected == {tank.id}
    page.handle_click(2, 3)
    assert state.selected == frozenset()
    page.handle_click(2, 3)
    page.handle_click(8.5, 2.5, shift=True)
    assert state.selected == {tank.id, by_label["V-101"].id}
    page.handle_box(-1, -1, 25, 7)
    assert by_label["P-101"].id in state.selected

    page.set_layer_visible("EQUIP", False)
    assert not any(by_label[t].id in state.selected for t in ("T-101", "P-101", "T-102"))
    page.handle_click(2, 3)
    assert state.selected == frozenset()
    page.set_layer_visible("EQUIP", True)
    page.handle_box(-1, -1, 25, 7)

    await user.should_see("included")
    user.find("Create Asset").click()
    user.find("Name").type("2-Vessel CIP System")
    user.find("Customer Need").type("Reduce Water Usage")
    user.find("Tags (comma separated)").type("cip, water")
    user.find("Save").click()
    await user.should_see("Saved asset")
    await user.should_see("2-Vessel CIP System")

    workshop = page._workshop
    [asset] = workshop.list_assets()
    detail = workshop.get_asset(asset.id)
    assert detail is not None
    assert asset.customer_need == "Reduce Water Usage"
    assert asset.tags == ("cip", "water")
    assert len(detail.objects) == len(state.selected)

    response = await user.http_client.get(f"/assets/{asset.id}/graph")
    assert response.status_code == 200 and "T-101" in response.text
    assert (await user.http_client.get("/assets/999/graph")).status_code == 404


async def test_rejects_invalid_upload(user: User, pages, tmp_path: Path) -> None:
    bad = tmp_path / "bad.dxf"
    bad.write_text("nope")
    await user.open("/")
    await upload(user, bad)
    await user.should_see("Import failed")
    assert pages[0].state.drawing is None


async def test_create_asset_requires_selection_and_name(
    user: User, pages, sample_dxf: Path
) -> None:
    await user.open("/")
    user.find("Create Asset").click()
    await user.should_see("Select at least one object")
    await upload(user, sample_dxf)
    await user.should_see("Imported sample.dxf")
    pages[0].handle_click(2, 3)
    user.find("Create Asset").click()
    user.find("Save").click()
    await user.should_see("Asset name is required")


def test_register_pages_adds_route(services) -> None:
    register_pages(*services)
