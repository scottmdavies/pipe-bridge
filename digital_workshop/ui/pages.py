"""NiceGUI pages. UI only: all rules live in the injected services."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from nicegui import app, context, events, ui

from digital_workshop.domain.models import AssetRequest, Drawing, DrawingObject
from digital_workshop.services.assets import AssetValidationError
from digital_workshop.services.selection import SelectionService
from digital_workshop.services.workshop import DEFAULT_PROJECT, DrawingImportError, WorkshopService

STATIC_DIR = Path(__file__).parent / "static"
STATIC_URL = "/workshop-static"
GRAPH_URL = "/assets/{asset_id}/graph"


@dataclass
class ViewerState:
    """Per-browser-session UI state (created for each page load, never shared)."""

    drawing: Drawing | None = None
    objects: list[DrawingObject] = field(default_factory=list)
    selected: frozenset[int] = frozenset()
    hidden_layers: frozenset[str] = frozenset()


class WorkshopPage:
    """Builds the page for one browser session and wires events to the services."""

    def __init__(self, workshop: WorkshopService, selection: SelectionService) -> None:
        """Create a page controller with injected services and fresh state."""
        self._workshop = workshop
        self._selection = selection
        self._state = ViewerState()
        self._client = context.client

    @property
    def state(self) -> ViewerState:
        """Current session state (exposed for tests)."""
        return self._state

    def build(self) -> None:
        """Create all UI elements."""
        ui.add_head_html(f'<script src="{STATIC_URL}/viewer.js"></script>')
        with ui.header().classes("items-center bg-slate-800"):
            ui.label("Briggs Digital Workshop").classes("text-h6")
            ui.label("Asset productisation - read-only against source drawings").classes(
                "text-caption"
            )

        with ui.left_drawer(fixed=False).classes("gap-2").props("width=320"):
            self._project_input = ui.input("Project", value=DEFAULT_PROJECT).classes("w-full")
            self._upload = (
                ui.upload(
                    label="Upload DXF",
                    auto_upload=True,
                    max_files=1,
                    on_upload=self._on_upload,
                )
                .props('accept=".dxf"')
                .classes("w-full")
            )
            self._drawing_select = ui.select({}, label="Drawing", on_change=self._on_drawing_change)
            self._drawing_select.classes("w-full")
            self._metadata = ui.column().classes("text-caption gap-0")
            ui.separator()
            ui.label("Layers").classes("text-subtitle2")
            self._layers = ui.column().classes("gap-0")

        with ui.tabs().classes("w-full") as tabs:
            viewer_tab = ui.tab("Viewer")
            assets_tab = ui.tab("Assets")
        with ui.tab_panels(tabs, value=viewer_tab).classes("w-full"):
            with ui.tab_panel(viewer_tab):
                self._build_viewer()
            with ui.tab_panel(assets_tab):
                self._build_assets()

        ui.on("dxf_click", self._on_click)
        ui.on("dxf_box", self._on_box)
        ui.timer(0.1, self._attach_viewer, once=True)
        self._refresh_drawings()
        self._refresh_assets()

    def _build_viewer(self) -> None:
        with ui.row().classes("items-center gap-2"):
            ui.toggle(
                {"select": "Select", "pan": "Pan"}, value="select", on_change=self._on_mode
            ).props("dense")
            ui.button(
                "Fit", on_click=lambda: self._client.run_javascript("DigitalWorkshop.fit()")
            ).props("dense flat")
            ui.button("Clear selection", on_click=self._clear_selection).props("dense flat")
            self._selection_label = ui.label("0 objects included")
            self._create_button = ui.button("Create Asset", on_click=self._open_asset_dialog)
            self._create_button.props("color=primary dense")
        ui.label(
            "Click: toggle object | Shift/Ctrl-click: multi-select | "
            "Drag: box select | Wheel: zoom | Pan mode or middle-drag: pan"
        ).classes("text-caption text-grey")
        self._viewer = ui.html("", sanitize=False).props("id=dxf-host")
        self._viewer.classes("w-full border").style("height: 65vh; overflow: hidden")

    def _build_assets(self) -> None:
        with ui.row().classes("w-full no-wrap"):
            self._asset_list = ui.column().classes("w-1/4")
            with ui.column().classes("w-3/4"):
                self._asset_info = ui.column().classes("gap-0")
                self._graph = ui.element("iframe").props("sandbox=allow-scripts").classes("w-full")
                self._graph.style("height: 500px; border: 1px solid #ccc")

    async def _attach_viewer(self) -> None:
        await self._client.run_javascript("DigitalWorkshop.attach()")

    def _on_mode(self, e: events.ValueChangeEventArguments) -> None:
        self._client.run_javascript(f"DigitalWorkshop.setMode({e.value!r})")

    async def _on_upload(self, e: events.UploadEventArguments) -> None:
        content = await e.file.read()
        try:
            drawing = self._workshop.import_drawing(
                e.file.name, content, self._project_input.value or DEFAULT_PROJECT
            )
        except DrawingImportError as exc:
            ui.notify(f"Import failed: {exc}", type="negative")
            return
        ui.notify(f"Imported {drawing.filename}", type="positive")
        self._refresh_drawings()
        self._drawing_select.value = drawing.id
        self._upload.reset()

    def _refresh_drawings(self) -> None:
        options = {d.id: f"{d.filename} (#{d.id})" for d in self._workshop.list_drawings()}
        self._drawing_select.set_options(options)

    def _on_drawing_change(self, e: events.ValueChangeEventArguments) -> None:
        if e.value is None:
            return
        drawing = self._workshop.get_drawing(e.value)
        if drawing is None:
            return
        self.load_drawing(drawing)

    def load_drawing(self, drawing: Drawing) -> None:
        """Show a drawing and reset selection and layer visibility."""
        self._state = ViewerState(drawing=drawing, objects=self._workshop.get_objects(drawing.id))
        self._viewer.set_content(self._workshop.render_drawing(drawing, self._state.objects))
        self._show_metadata(drawing)
        self._show_layers(drawing)
        self._update_selection_label()

    def _show_metadata(self, drawing: Drawing) -> None:
        meta = drawing.metadata
        self._metadata.clear()
        with self._metadata:
            ui.label(f"Layers: {len(meta.layers)}  Blocks: {len(meta.blocks)}")
            ui.label(f"Inserts: {meta.insert_count}  Text: {meta.text_count}")
            counts = ", ".join(f"{k}: {v}" for k, v in meta.entity_counts.items())
            ui.label(f"Entities - {counts}")
            if meta.bbox:
                b = meta.bbox
                ui.label(f"Extent: ({b.min_x:g}, {b.min_y:g}) to ({b.max_x:g}, {b.max_y:g})")

    def _show_layers(self, drawing: Drawing) -> None:
        used = sorted({o.layer for o in self._state.objects})
        self._layers.clear()
        with self._layers:
            for layer in used:
                ui.checkbox(
                    layer,
                    value=True,
                    on_change=lambda e, name=layer: self.set_layer_visible(name, e.value),
                ).props("dense")

    def set_layer_visible(self, layer: str, visible: bool) -> None:
        """Show or hide a layer; hidden objects are removed from the selection."""
        hidden = set(self._state.hidden_layers)
        hidden.discard(layer) if visible else hidden.add(layer)
        self._state.hidden_layers = frozenset(hidden)
        hidden_ids = {o.id for o in self._state.objects if o.layer in hidden}
        self._state.selected = frozenset(self._state.selected - hidden_ids)
        self._client.run_javascript(f"DigitalWorkshop.setHiddenLayers({sorted(hidden)!r})")
        self._push_selection()

    def _visible_objects(self) -> list[DrawingObject]:
        return self._selection.visible(self._state.objects, self._state.hidden_layers)

    def _on_click(self, e: events.GenericEventArguments) -> None:
        self.handle_click(
            e.args["x"],
            e.args["y"],
            e.args.get("tol", 0),
            e.args.get("shift", False),
            e.args.get("ctrl", False),
        )

    def handle_click(
        self, x: float, y: float, tolerance: float = 0.0, shift: bool = False, ctrl: bool = False
    ) -> None:
        """Handle a click at drawing coordinates."""
        target = self._selection.hit_test(self._visible_objects(), x, y, tolerance)
        self._state.selected = self._selection.click(
            self._state.selected, target, shift=shift, ctrl=ctrl
        )
        self._push_selection()

    def _on_box(self, e: events.GenericEventArguments) -> None:
        a = e.args
        self.handle_box(
            a["x1"],
            a["y1"],
            a["x2"],
            a["y2"],
            additive=a.get("shift", False) or a.get("ctrl", False),
        )

    def handle_box(
        self, x1: float, y1: float, x2: float, y2: float, additive: bool = False
    ) -> None:
        """Handle a box selection in drawing coordinates."""
        self._state.selected = self._selection.box_select(
            self._state.selected, self._visible_objects(), x1, y1, x2, y2, additive=additive
        )
        self._push_selection()

    def _clear_selection(self) -> None:
        self._state.selected = frozenset()
        self._push_selection()

    def _push_selection(self) -> None:
        self._client.run_javascript(
            f"DigitalWorkshop.setSelection({sorted(self._state.selected)!r})"
        )
        self._update_selection_label()

    def _update_selection_label(self) -> None:
        count = len(self._state.selected)
        self._selection_label.set_text(f"{count} object{'s' if count != 1 else ''} included")
        self._create_button.set_enabled(count > 0)

    def _open_asset_dialog(self) -> None:
        if self._state.drawing is None or not self._state.selected:
            ui.notify("Select at least one object first.", type="warning")
            return
        with ui.dialog() as dialog, ui.card().classes("w-96"):
            ui.label("Create Asset").classes("text-h6")
            name = ui.input("Name").classes("w-full")
            description = ui.textarea("Description").classes("w-full")
            sector = ui.input("Sector").classes("w-full")
            need = ui.input("Customer Need").classes("w-full")
            tags = ui.input("Tags (comma separated)").classes("w-full")
            with ui.row():
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button(
                    "Save",
                    on_click=lambda: self._save_asset(
                        dialog, name.value, description.value, sector.value, need.value, tags.value
                    ),
                )
        dialog.open()

    def _save_asset(
        self, dialog: ui.dialog, name: str, description: str, sector: str, need: str, tags: str
    ) -> None:
        assert self._state.drawing is not None
        request = AssetRequest(
            name=name or "",
            description=description or "",
            sector=sector or "",
            customer_need=need or "",
            tags=tuple((tags or "").split(",")),
        )
        try:
            detail = self._workshop.create_asset(
                self._state.drawing.id, self._state.selected, request
            )
        except AssetValidationError as exc:
            ui.notify(str(exc), type="negative")
            return
        dialog.close()
        ui.notify(
            f"Saved asset '{detail.asset.name}' with {len(detail.objects)} objects "
            f"and {len(detail.relationships)} relationships",
            type="positive",
        )
        self._refresh_assets()
        self.show_asset(detail.asset.id)

    def _refresh_assets(self) -> None:
        self._asset_list.clear()
        with self._asset_list:
            for asset in self._workshop.list_assets():
                ui.button(asset.name, on_click=lambda _, a=asset.id: self.show_asset(a)).props(
                    "flat no-caps align=left"
                ).classes("w-full")

    def show_asset(self, asset_id: int) -> None:
        """Display an asset's details and relationship graph."""
        detail = self._workshop.get_asset(asset_id)
        if detail is None:
            return
        asset = detail.asset
        self._asset_info.clear()
        with self._asset_info:
            ui.label(asset.name).classes("text-h6")
            ui.label(f"Sector: {asset.sector or '-'}")
            ui.label(f"Customer need: {asset.customer_need or '-'}")
            ui.label(f"Tags: {', '.join(asset.tags) or '-'}")
            ui.label(asset.description)
            ui.label(f"{len(detail.objects)} objects, {len(detail.relationships)} relationships")
        self._graph.props(f"src={GRAPH_URL.format(asset_id=int(asset_id))}")
        self._graph.update()


def register_graph_route(workshop: WorkshopService) -> None:
    """Serve each asset's PyVis relationship graph as an HTML document (for the iframe)."""

    @app.get("/assets/{asset_id}/graph")
    def asset_graph(asset_id: int) -> HTMLResponse:
        graph_html = workshop.asset_graph_html(asset_id)
        if graph_html is None:
            raise HTTPException(status_code=404, detail="Unknown asset")
        return HTMLResponse(graph_html)


def register_pages(workshop: WorkshopService, selection: SelectionService) -> None:
    """Register the workshop page and graph routes using the injected services."""
    app.add_static_files(STATIC_URL, str(STATIC_DIR))
    register_graph_route(workshop)

    @ui.page("/")
    def index() -> None:
        WorkshopPage(workshop, selection).build()
