import hashlib
from pathlib import Path

import pytest

from digital_workshop.bootstrap import build_services
from digital_workshop.config import Settings
from digital_workshop.domain.models import AssetRequest
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
    assert detail.relationships

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
    assert workshop.asset_graph_html(12345) is None
    html = workshop.asset_graph_html(detail.asset.id)
    assert html and "T-101" in html


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
