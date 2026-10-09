# Briggs Digital Workshop (MVP)

Knowledge capture and productisation tool: load a DXF, select a proven area of a design,
save it as a reusable asset with its objects and relationships. Source DXF files are never
modified (uploads are stored as write-once, content-addressed copies; parsing is read-only).

## Run

```bash
docker compose up -d postgres            # PostgreSQL (see docker-compose.yml)
pip install -e ".[dev]"
export DATABASE_URL="postgresql+psycopg2://<user>:<password>@localhost:5432/workshop"
python -m digital_workshop               # http://localhost:8080
```

Settings (environment): `DATABASE_URL`, `UPLOAD_DIR` (default `var/uploads`),
`MAX_UPLOAD_BYTES`, `PROXIMITY_THRESHOLD` (bounding-box gap, in drawing units, below which
two objects are related; default 50 - tune to the drawing units).

## Develop

```bash
ruff check digital_workshop tests && black --check digital_workshop tests \
  && isort --check-only digital_workshop tests
pytest            # fails under 85% coverage
```

## Selection

* Click: toggle Included/Excluded (clears the rest of the selection)
* Shift-click: include and keep the rest; Ctrl-click: toggle and keep the rest
* Drag: box select (objects fully inside); with Shift/Ctrl it adds to the selection

## Layout

`ui/` NiceGUI pages (no business logic) -> `services/` (DXF parser, SVG renderer, selection,
relationship engine, asset creator, graph builder, `WorkshopService` facade) ->
`db/` repositories + unit of work (SQLAlchemy 2.0) -> PostgreSQL. `bootstrap.py` wires it all.
Relationships are proximity- and layer-based (`services/relationships.py`); a true
connectivity strategy can be added behind the same `RelationshipStrategy` protocol.
