import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path

import ezdxf
import pytest
from sqlalchemy import create_engine, inspect, text

from digital_workshop.bootstrap import build_services
from digital_workshop.config import Settings
from digital_workshop.db.session import _upgrade_connection_segments
from digital_workshop.domain.models import AssetRequest, CostItem, Relationship
from digital_workshop.services.assets import AssetValidationError
from digital_workshop.services.workshop import DrawingImportError, WorkshopService


def import_sample(workshop: WorkshopService, path: Path, project: str = "P1"):
    return workshop.import_drawing(path.name, path.read_bytes(), project)


def test_import_persists_metadata_and_objects(workshop: WorkshopService, sample_dxf: Path) -> None:
    drawing = import_sample(workshop, sample_dxf)
    loaded = workshop.get_drawing(drawing.id)
    assert loaded is not None
    assert loaded.metadata.insert_count == 4
    assert loaded.metadata.entity_counts["INSERT"] == 4
    assert loaded.metadata.bbox is not None
    objects = workshop.get_objects(drawing.id)
    assert len(objects) == 11 and all(o.id for o in objects)
    pipe_line = next(o for o in objects if o.entity_type == "LINE" and o.layer == "PIPE")
    assert pipe_line.connection_segments == (((9.0, 2.5), (12.0, 2.5)),)
    assert [d.id for d in workshop.list_drawings()] == [drawing.id]
    assert workshop.get_drawing(999) is None


def test_source_and_stored_copy_are_untouched(workshop: WorkshopService, sample_dxf: Path) -> None:
    before = hashlib.sha256(sample_dxf.read_bytes()).hexdigest()
    drawing = import_sample(workshop, sample_dxf)
    assert hashlib.sha256(sample_dxf.read_bytes()).hexdigest() == before
    assert drawing.sha256 == before
    assert hashlib.sha256(Path(drawing.stored_path).read_bytes()).hexdigest() == before


def test_import_rejects_bad_input(settings: Settings, sample_dxf: Path) -> None:
    workshop, _ = build_services(
        Settings(settings.database_url, settings.upload_dir, max_upload_bytes=10)
    )
    with pytest.raises(DrawingImportError, match="empty"):
        workshop.import_drawing("a.dxf", b"")
    with pytest.raises(DrawingImportError, match="too large"):
        workshop.import_drawing("a.dxf", sample_dxf.read_bytes())
    workshop, _ = build_services(settings)
    with pytest.raises(DrawingImportError):
        workshop.import_drawing("a.dxf", b"not a dxf")


def test_filename_is_sanitised(workshop: WorkshopService, sample_dxf: Path) -> None:
    drawing = workshop.import_drawing("../../etc/pa$$wd.dxf", sample_dxf.read_bytes())
    assert drawing.filename == "pa__wd.dxf"
    assert "etc" not in drawing.stored_path


def test_asset_save_and_load(workshop: WorkshopService, sample_dxf: Path) -> None:
    drawing = import_sample(workshop, sample_dxf)
    objects = workshop.get_objects(drawing.id)
    chosen = [o for o in objects if o.label in {"T-101", "V-101", "P-101"}]
    detail = workshop.create_asset(
        drawing.id,
        frozenset(o.id for o in chosen),
        AssetRequest(
            "2-Vessel CIP System",
            "desc",
            "Beverage",
            "Reduce Water Usage",
            ("cip", " cip ", "water", ""),
        ),
    )
    assert detail.asset.tags == ("cip", "water")
    assert detail.relationships == []
    assets = workshop.list_assets()
    assert [a.name for a in assets] == ["2-Vessel CIP System"]
    loaded = workshop.get_asset(detail.asset.id)
    assert loaded is not None
    assert loaded.asset.customer_need == "Reduce Water Usage"
    assert loaded.asset.sector == "Beverage"
    assert loaded.asset.drawing_id == drawing.id
    assert {o.label for o in loaded.objects} == {"T-101", "V-101", "P-101"}
    assert {(r.source_id, r.target_id, r.relation_type) for r in loaded.relationships} == {
        (r.source_id, r.target_id, r.relation_type) for r in detail.relationships
    }
    assert workshop.get_asset(12345) is None


def test_pipe_asset_uses_geometric_connections(workshop: WorkshopService, sample_dxf: Path) -> None:
    drawing = import_sample(workshop, sample_dxf)
    pipework = [
        obj
        for obj in workshop.get_objects(drawing.id)
        if obj.layer == "PIPE" and obj.connection_segments
    ]

    detail = workshop.create_asset(
        drawing.id,
        frozenset(obj.id for obj in pipework),
        AssetRequest("Pipe run"),
    )

    assert len(detail.objects) == 3
    assert len(detail.relationships) == 2
    assert {relationship.relation_type for relationship in detail.relationships} == {
        "connection_candidate"
    }


def test_asset_relationships_can_be_human_reviewed(
    workshop: WorkshopService, sample_dxf: Path
) -> None:
    drawing = import_sample(workshop, sample_dxf)
    pipework = [
        obj
        for obj in workshop.get_objects(drawing.id)
        if obj.layer == "PIPE" and obj.connection_segments
    ]
    detail = workshop.create_asset(
        drawing.id,
        frozenset(obj.id for obj in pipework),
        AssetRequest("Reviewed pipe run"),
    )
    confirmed = [
        Relationship(
            detail.objects[0].id,
            detail.objects[1].id,
            "confirmed_connection",
        )
    ]

    workshop.update_asset_relationships(detail.asset.id, confirmed)

    loaded = workshop.get_asset(detail.asset.id)
    assert loaded is not None
    assert loaded.relationships == confirmed


def test_asset_suggestions_find_nearby_annotation_and_can_be_included(
    workshop: WorkshopService, sample_dxf: Path
) -> None:
    drawing = import_sample(workshop, sample_dxf)
    objects = workshop.get_objects(drawing.id)
    pipe = next(obj for obj in objects if obj.entity_type == "LWPOLYLINE" and obj.layer == "PIPE")
    asset = workshop.create_asset(
        drawing.id, frozenset({pipe.id}), AssetRequest("Reviewed segment")
    )

    suggestions = workshop.suggest_asset_additions(asset.asset.id, tolerance=1.0)

    label = next(obj for obj in objects if obj.label == "L-001")
    assert label.id in {suggestion.object.id for suggestion in suggestions}
    assert all(suggestion.distance <= 1.0 for suggestion in suggestions)
    workshop.include_asset_suggestions(asset.asset.id, {label.id})
    loaded = workshop.get_asset(asset.asset.id)
    assert loaded is not None
    assert label.id in {obj.id for obj in loaded.objects}


def test_asset_export_keeps_selected_entities_and_source_blocks(
    workshop: WorkshopService, sample_dxf: Path, tmp_path: Path
) -> None:
    drawing = import_sample(workshop, sample_dxf)
    chosen = [obj for obj in workshop.get_objects(drawing.id) if obj.label in {"T-101", "V-101"}]
    asset = workshop.create_asset(
        drawing.id,
        frozenset(obj.id for obj in chosen),
        AssetRequest("T-101 and V-101"),
    )

    exported = workshop.export_asset_dxf(asset.asset.id)

    assert exported is not None
    filename, content = exported
    assert filename == "T-101 and V-101.dxf"
    output = tmp_path / filename
    output.write_bytes(content)
    document = ezdxf.readfile(output)
    audit = document.audit()
    entities = list(document.modelspace())
    assert not audit.errors and not audit.fixes
    assert {entity.dxf.handle for entity in entities} == {obj.handle for obj in chosen}
    assert {entity.dxf.name for entity in entities} == {"TANK", "VALVE"}
    assert {block.name for block in document.blocks} >= {"TANK", "VALVE"}
    tank = next(entity for entity in entities if entity.dxf.name == "TANK")
    assert {attrib.dxf.tag: attrib.dxf.text for attrib in tank.attribs}["TAG"] == "T-101"


def test_asset_cost_schedule_saves_equipment_and_scope_lumpsums(
    workshop: WorkshopService, sample_dxf: Path
) -> None:
    drawing = import_sample(workshop, sample_dxf)
    objects = workshop.get_objects(drawing.id)
    detail = workshop.create_asset(
        drawing.id,
        frozenset(obj.id for obj in objects),
        AssetRequest("Costed asset"),
    )
    tank = next(obj for obj in detail.objects if obj.label == "T-101")
    costs = [
        CostItem(
            category="equipment",
            description="T-101 tank supply",
            object_id=tank.id,
            unit_cost=Decimal("12500.00"),
            source="Supplier budget quote",
            basis_date=date(2026, 10, 14),
        ),
        CostItem(category="pipework", description="Pipework lump sum", unit_cost=Decimal("2400")),
        CostItem(
            category="electrical",
            description="Electrical lump sum",
            unit_cost=Decimal("800"),
        ),
        CostItem(category="ma", description="M&A lump sum", unit_cost=Decimal("1200")),
    ]

    workshop.update_asset_cost_items(detail.asset.id, costs)

    loaded = workshop.get_asset(detail.asset.id)
    assert loaded is not None
    assert [(item.category, item.total) for item in loaded.cost_items] == [
        ("equipment", Decimal("12500.00")),
        ("pipework", Decimal("2400.00")),
        ("electrical", Decimal("800.00")),
        ("ma", Decimal("1200.00")),
    ]
    equipment = loaded.cost_items[0]
    assert equipment.object_id == tank.id
    assert equipment.source == "Supplier budget quote"
    assert equipment.basis_date == date(2026, 10, 14)
    with pytest.raises(AssetValidationError, match="reference an object"):
        workshop.update_asset_cost_items(
            detail.asset.id,
            [
                CostItem(
                    category="equipment",
                    description="Out-of-asset item",
                    object_id=999999,
                    unit_cost=Decimal("1"),
                )
            ],
        )


def test_asset_validation(workshop: WorkshopService, sample_dxf: Path) -> None:
    drawing = import_sample(workshop, sample_dxf)
    other = import_sample(workshop, sample_dxf.parent / "sample.dxf", "P2")
    ids = frozenset(o.id for o in workshop.get_objects(drawing.id)[:2])
    with pytest.raises(AssetValidationError, match="name"):
        workshop.create_asset(drawing.id, ids, AssetRequest("  "))
    with pytest.raises(AssetValidationError, match="at least one"):
        workshop.create_asset(drawing.id, frozenset(), AssetRequest("x"))
    with pytest.raises(AssetValidationError, match="Unknown drawing"):
        workshop.create_asset(9999, ids, AssetRequest("x"))
    with pytest.raises(AssetValidationError, match="not in this drawing"):
        workshop.create_asset(other.id, ids, AssetRequest("x"))
    assert workshop.list_assets() == []


def test_projects_are_reused(workshop: WorkshopService, sample_dxf: Path) -> None:
    a = import_sample(workshop, sample_dxf, "Same")
    b = import_sample(workshop, sample_dxf, "Same")
    c = import_sample(workshop, sample_dxf, " ")
    assert a.project_id == b.project_id != c.project_id
    assert len(workshop.list_drawings()) == 3


def test_unit_of_work_rolls_back_on_error(services, sample_dxf: Path) -> None:
    from digital_workshop.db.repositories import UnitOfWork
    from digital_workshop.db.session import create_db_engine, create_session_factory

    factory = create_session_factory(create_db_engine("sqlite://"))
    with pytest.raises(RuntimeError):
        with UnitOfWork(factory) as uow:
            uow.projects.get_or_create("temp")
            raise RuntimeError
    with UnitOfWork(factory) as uow:
        assert uow.projects.list() == []
        uow.projects.get_or_create("keep")
    with UnitOfWork(factory) as uow:
        assert [p.name for p in uow.projects.list()] == ["keep"]
        assert uow.drawings.list_for_project(1) == []
        assert uow.drawings.get_objects(1, []) == []


def test_existing_database_gets_connection_segments_column() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE dxf_objects (id INTEGER PRIMARY KEY)"))

    _upgrade_connection_segments(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("dxf_objects")}
    assert "connection_segments" in columns
