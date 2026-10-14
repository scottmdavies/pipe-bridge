"""NiceGUI pages. UI only: all rules live in the injected services."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from nicegui import app, context, events, ui

from digital_workshop.domain.models import (
    AssetObjectSuggestion,
    AssetRequest,
    CostItem,
    Drawing,
    DrawingObject,
    Relationship,
)
from digital_workshop.services.assets import AssetValidationError
from digital_workshop.services.dxf_exporter import DxfExportError
from digital_workshop.services.relationships import (
    CONFIRMED_CONNECTION,
    CONNECTION_CANDIDATE,
)
from digital_workshop.services.selection import SelectionService
from digital_workshop.services.workshop import DEFAULT_PROJECT, DrawingImportError, WorkshopService

STATIC_DIR = Path(__file__).parent / "static"
STATIC_URL = "/workshop-static"


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
        self._asset_relationship_rows: list[dict] = []
        self._relationship_asset_id: int | None = None
        self._relationship_objects: dict[int, str] = {}
        self._cost_asset_id: int | None = None
        self._cost_object_options: dict[int, str] = {}
        self._cost_rows: list[dict] = []
        self._suggestion_asset_id: int | None = None

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
                    label="Upload DXF or DWG",
                    auto_upload=True,
                    max_files=1,
                    on_upload=self._on_upload,
                )
                .props('accept=".dxf,.dwg"')
                .classes("w-full")
            )
            self._drawing_select = ui.select({}, label="Drawing", on_change=self._on_drawing_change)
            self._drawing_select.classes("w-full")
            self._metadata = ui.column().classes("text-caption gap-0")
            ui.separator()
            ui.label("Layers").classes("text-subtitle2")
            self._layers = ui.column().classes("gap-0")

        with ui.tabs().classes("w-full") as self._tabs:
            self._viewer_tab = ui.tab("Viewer")
            assets_tab = ui.tab("Assets")
            costs_tab = ui.tab("Costs")
        with ui.tab_panels(self._tabs, value=self._viewer_tab).classes("w-full"):
            with ui.tab_panel(self._viewer_tab):
                self._build_viewer()
            with ui.tab_panel(assets_tab):
                self._build_assets()
            with ui.tab_panel(costs_tab):
                self._build_cost_schedule()

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
                self._relationship_editor = ui.column().classes("w-full")
                ui.separator()
                ui.label("Nearby objects")
                with ui.row().classes("items-center gap-2"):
                    self._suggestion_tolerance = ui.number(
                        "Radius", value=10.0, min=0, step=1
                    ).classes("w-32")
                    ui.button("Find nearby", on_click=self._find_asset_suggestions).props("dense")
                self._suggestions_area = ui.column().classes("w-full")

    def _build_cost_schedule(self) -> None:
        ui.label("Cost schedule").classes("text-h6")
        with ui.row().classes("w-full items-center gap-2"):
            self._cost_asset_select = ui.select(
                {}, label="Asset", on_change=self._on_cost_asset_change
            ).classes("w-80")
            ui.button("Add cost line", on_click=self._add_cost_row).props("dense")
            ui.button("Apply costs", on_click=self._save_cost_schedule).props("dense color=primary")
        self._cost_total = ui.label("Base cost total: -").classes("text-subtitle2")
        self._cost_editor = ui.column().classes("w-full")

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
        assets = self._workshop.list_assets()
        options = {asset.id: asset.name for asset in assets}
        self._asset_list.clear()
        with self._asset_list:
            for asset in assets:
                ui.button(asset.name, on_click=lambda _, a=asset.id: self.show_asset(a)).props(
                    "flat no-caps align=left"
                ).classes("w-full")
        self._cost_asset_select.set_options(options)
        if self._cost_asset_id not in options:
            self._cost_asset_id = None
            self._cost_asset_select.value = None

    def show_asset(self, asset_id: int) -> None:
        """Display an asset and select its member objects in the drawing viewer."""
        detail = self._workshop.get_asset(asset_id)
        if detail is None:
            return
        asset = detail.asset
        drawing = self._workshop.get_drawing(asset.drawing_id) if asset.drawing_id else None
        if drawing is not None:
            if self._state.drawing is None or self._state.drawing.id != drawing.id:
                self.load_drawing(drawing)
            else:
                self._state.hidden_layers = frozenset()
                self._show_layers(drawing)
                self._client.run_javascript("DigitalWorkshop.setHiddenLayers([])")
            self._state.selected = frozenset(obj.id for obj in detail.objects if obj.id is not None)
            self._push_selection()
        self._asset_info.clear()
        with self._asset_info:
            ui.label(asset.name).classes("text-h6")
            ui.label(f"Sector: {asset.sector or '-'}")
            ui.label(f"Customer need: {asset.customer_need or '-'}")
            ui.label(f"Tags: {', '.join(asset.tags) or '-'}")
            ui.label(asset.description)
            ui.label(f"{len(detail.objects)} objects, {len(detail.relationships)} relationships")
            ui.button(
                "Show in drawing", on_click=lambda: self._show_asset_in_viewer(asset_id)
            ).props("dense")
            ui.button("Export DXF", on_click=lambda: self._export_asset_dxf(asset_id)).props(
                "dense"
            )
        self._render_relationship_editor(detail)
        self._cost_asset_select.value = asset_id
        self._load_cost_schedule(asset_id)
        self._suggestion_asset_id = asset_id

    def _show_asset_in_viewer(self, asset_id: int) -> None:
        self.show_asset(asset_id)
        self._tabs.value = self._viewer_tab

    def _export_asset_dxf(self, asset_id: int) -> None:
        try:
            export = self._workshop.export_asset_dxf(asset_id)
        except DxfExportError as exc:
            ui.notify(str(exc), type="negative")
            return
        if export is None:
            ui.notify("Asset or source drawing not found.", type="negative")
            return
        filename, content = export
        ui.download(content, filename, "application/dxf")

    def _render_relationship_editor(self, detail) -> None:
        self._relationship_asset_id = detail.asset.id
        self._relationship_objects = {
            obj.id: f"#{obj.id} {obj.label} [{obj.entity_type} / {obj.layer}]"
            for obj in detail.objects
            if obj.id is not None
        }
        self._relationship_editor.clear()
        self._asset_relationship_rows = []
        with self._relationship_editor:
            ui.label("Connections").classes("text-subtitle2")
            with ui.row().classes("gap-2"):
                ui.button("Add connection", on_click=self._add_relationship_row).props("dense")
                ui.button("Save connections", on_click=self._save_relationships).props(
                    "dense color=primary"
                )
            for relationship in detail.relationships:
                self._add_relationship_row(relationship)

    def _add_relationship_row(self, relationship: Relationship | None = None) -> None:
        object_ids = list(self._relationship_objects)
        source_id = (
            relationship.source_id if relationship else (object_ids[0] if object_ids else None)
        )
        target_id = (
            relationship.target_id
            if relationship
            else (object_ids[1] if len(object_ids) > 1 else None)
        )
        relation_type = relationship.relation_type if relationship else CONFIRMED_CONNECTION
        relation_options = {
            CONNECTION_CANDIDATE: "Candidate",
            CONFIRMED_CONNECTION: "Confirmed",
        }
        if relation_type not in relation_options:
            relation_options[relation_type] = relation_type.replace("_", " ").title()
        row_data: dict = {"distance": relationship.distance if relationship else None}
        with self._relationship_editor:
            with ui.row().classes("w-full items-center no-wrap gap-2") as row_element:
                row_data["source"] = ui.select(
                    self._relationship_objects, value=source_id, label="From"
                ).classes("col")
                row_data["relation"] = ui.select(
                    relation_options, value=relation_type, label="Type"
                ).classes("col")
                row_data["target"] = ui.select(
                    self._relationship_objects, value=target_id, label="To"
                ).classes("col")
                ui.button(
                    icon="delete", on_click=lambda: self._remove_relationship_row(row_data)
                ).props("flat round dense aria-label=Remove connection")
        row_data["element"] = row_element
        self._asset_relationship_rows.append(row_data)

    def _remove_relationship_row(self, row_data: dict) -> None:
        row_data["element"].delete()
        self._asset_relationship_rows.remove(row_data)

    def _save_relationships(self) -> None:
        if self._relationship_asset_id is None:
            return
        relationships = []
        for row in self._asset_relationship_rows:
            source_id, target_id = row["source"].value, row["target"].value
            if source_id is None or target_id is None or source_id == target_id:
                ui.notify("Choose two different objects for each connection.", type="warning")
                return
            relationships.append(
                Relationship(
                    int(source_id),
                    int(target_id),
                    row["relation"].value,
                    row["distance"],
                )
            )
        asset_id = self._relationship_asset_id
        try:
            self._workshop.update_asset_relationships(asset_id, relationships)
        except AssetValidationError as exc:
            ui.notify(str(exc), type="negative")
            return
        self.show_asset(asset_id)
        ui.notify("Connections saved", type="positive")

    def _on_cost_asset_change(self, e: events.ValueChangeEventArguments) -> None:
        if e.value is not None:
            self._load_cost_schedule(int(e.value))

    def _load_cost_schedule(self, asset_id: int) -> None:
        detail = self._workshop.get_asset(asset_id)
        if detail is None:
            return
        self._cost_asset_id = asset_id
        self._cost_object_options = {
            obj.id: f"#{obj.id} {obj.label}" for obj in detail.objects if obj.id is not None
        }
        self._cost_editor.clear()
        self._cost_rows = []
        for cost_item in detail.cost_items:
            self._add_cost_row(cost_item)
        totals: dict[str, Decimal] = {}
        for item in detail.cost_items:
            totals[item.currency] = totals.get(item.currency, Decimal("0")) + item.total
        summary = ", ".join(
            f"{currency} {amount:,.2f}" for currency, amount in sorted(totals.items())
        )
        self._cost_total.set_text(f"Base cost total: {summary or '-'}")

    def _add_cost_row(self, item: CostItem | None = None) -> None:
        categories = {
            "equipment": "Equipment",
            "pipework": "Pipework lump sum",
            "electrical": "Electrical lump sum",
            "ma": "M&A lump sum",
        }
        category = item.category if item else "equipment"
        row: dict = {}
        with self._cost_editor:
            with ui.row().classes("w-full items-center gap-2") as element:
                row["category"] = ui.select(
                    categories,
                    value=category,
                    label="Category",
                    on_change=lambda e, current=row: current["object"].set_visibility(
                        e.value == "equipment"
                    ),
                ).classes("w-40")
                row["object"] = ui.select(
                    self._cost_object_options,
                    value=item.object_id if item else None,
                    label="Equipment",
                ).classes("w-48")
                row["object"].set_visibility(category == "equipment")
                row["description"] = ui.input(
                    "Description", value=item.description if item else ""
                ).classes("w-48")
                row["quantity"] = ui.number(
                    "Qty",
                    value=float(item.quantity) if item else 1,
                    min=0.001,
                    step=0.001,
                ).classes("w-24")
                row["unit_cost"] = ui.number(
                    "Unit cost",
                    value=float(item.unit_cost) if item else 0,
                    min=0,
                    step=0.01,
                ).classes("w-32")
                row["currency"] = ui.input(
                    "Currency", value=item.currency if item else "GBP"
                ).classes("w-24")
                row["source"] = ui.input("Source", value=item.source if item else "").classes(
                    "w-40"
                )
                row["basis_date"] = (
                    ui.input(
                        "Cost date",
                        value=item.basis_date.isoformat() if item and item.basis_date else "",
                    )
                    .props("type=date")
                    .classes("w-40")
                )
                ui.button(icon="delete", on_click=lambda: self._remove_cost_row(row)).props(
                    "flat round dense aria-label=Remove cost line"
                )
        row["element"] = element
        self._cost_rows.append(row)

    def _remove_cost_row(self, row: dict) -> None:
        row["element"].delete()
        self._cost_rows.remove(row)

    def _save_cost_schedule(self) -> None:
        if self._cost_asset_id is None:
            return
        items = []
        try:
            for row in self._cost_rows:
                category = row["category"].value
                description = (row["description"].value or "").strip()
                if not description:
                    ui.notify("Each cost line needs a description.", type="warning")
                    return
                basis_date_text = row["basis_date"].value
                items.append(
                    CostItem(
                        category=category,
                        description=description,
                        quantity=Decimal(str(row["quantity"].value)),
                        unit_cost=Decimal(str(row["unit_cost"].value)),
                        currency=(row["currency"].value or "").strip().upper(),
                        object_id=(
                            int(row["object"].value)
                            if category == "equipment" and row["object"].value is not None
                            else None
                        ),
                        source=row["source"].value or "",
                        basis_date=date.fromisoformat(basis_date_text) if basis_date_text else None,
                    )
                )
            self._workshop.update_asset_cost_items(self._cost_asset_id, items)
        except (AssetValidationError, InvalidOperation, ValueError) as exc:
            ui.notify(str(exc), type="negative")
            return
        asset_id = self._cost_asset_id
        self._load_cost_schedule(asset_id)
        ui.notify("Cost schedule saved", type="positive")

    def _find_asset_suggestions(self) -> None:
        if self._suggestion_asset_id is None:
            return
        try:
            suggestions = self._workshop.suggest_asset_additions(
                self._suggestion_asset_id, float(self._suggestion_tolerance.value or 0)
            )
        except ValueError as exc:
            ui.notify(str(exc), type="warning")
            return
        self._suggestions_area.clear()
        if not suggestions:
            with self._suggestions_area:
                ui.label("No nearby objects found.").classes("text-caption")
            return

        rows = [self._suggestion_row(suggestion) for suggestion in suggestions]
        with self._suggestions_area:
            self._suggestion_table = ui.table(
                rows=rows,
                columns=[
                    {"name": "label", "label": "Object", "field": "label", "sortable": True},
                    {"name": "type", "label": "Type", "field": "type", "sortable": True},
                    {"name": "layer", "label": "Layer", "field": "layer", "sortable": True},
                    {
                        "name": "distance",
                        "label": "Gap",
                        "field": "distance",
                        "sortable": True,
                    },
                    {"name": "details", "label": "Attributes / suggestion", "field": "details"},
                ],
                row_key="id",
                selection="multiple",
            ).classes("w-full")
            ui.button("Include selected objects", on_click=self._include_asset_suggestions).props(
                "dense"
            )

    @staticmethod
    def _suggestion_row(suggestion: AssetObjectSuggestion) -> dict:
        obj = suggestion.object
        attribute_text = "; ".join(
            f"{key.rsplit('.', 1)[-1].rstrip(')')}: {value}"
            for key, value in obj.attributes.items()
            if value
        )
        return {
            "id": obj.id,
            "label": obj.label,
            "type": obj.entity_type,
            "layer": obj.layer,
            "distance": suggestion.distance,
            "details": attribute_text or suggestion.reason,
        }

    def _include_asset_suggestions(self) -> None:
        if self._suggestion_asset_id is None:
            return
        object_ids = {
            int(row["id"]) for row in (self._suggestion_table.selected or []) if row.get("id")
        }
        if not object_ids:
            ui.notify("Select at least one suggestion.", type="warning")
            return
        asset_id = self._suggestion_asset_id
        try:
            self._workshop.include_asset_suggestions(asset_id, object_ids)
        except AssetValidationError as exc:
            ui.notify(str(exc), type="negative")
            return
        self.show_asset(asset_id)
        self._find_asset_suggestions()
        ui.notify(f"Added {len(object_ids)} object(s) to the asset", type="positive")


def register_pages(workshop: WorkshopService, selection: SelectionService) -> None:
    """Register the workshop page using the injected services."""
    app.add_static_files(STATIC_URL, str(STATIC_DIR))

    @ui.page("/")
    def index() -> None:
        WorkshopPage(workshop, selection).build()
