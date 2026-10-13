# Pipe Bridge

Engineering tools platform. The current MVP is the Briggs Digital Workshop (see [digital_workshop/README.md](digital_workshop/README.md)); direction is in [docs/](docs/2026-10-02-platform-brief-and-roadmap.md).

## Quick start (testing)

**Docker (app + PostgreSQL, DWG support included):**

```bash
docker compose up --build          # http://localhost:8080
```

**Dev container:** open in VS Code / Codespaces; it builds from the same [Dockerfile](Dockerfile), so
`dwg2dxf` is available. Then:

```bash
DATABASE_URL="sqlite:///var/workshop.db" python -m digital_workshop   # http://localhost:8080
```

**Plain Python (3.12+), no Docker:**

```bash
pip install -e ".[dev]"
DATABASE_URL="sqlite:///var/workshop.db" python -m digital_workshop
```

## DWG uploads

DWG files are converted to DXF on upload with LibreDWG's `dwg2dxf`. It is a native tool, not a Python
package: the [Dockerfile](Dockerfile) builds it from source (it is not in Debian), and both compose and
the dev container use that Dockerfile. On a plain host, install it yourself and put it on `PATH`;
otherwise DWG uploads are rejected with a message and DXF still works.

## Tests

```bash
pytest
```
