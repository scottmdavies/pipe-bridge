# Pipe Bridge: Engineering Calculation Platform – Brief, Reflection & Roadmap

- **Date:** 2026-10-02
- **Author:** Scott M. Davies
- **Status:** Draft for discussion

## 1. Brief

Keep the **Pipe Bridge** name. Retire the existing material (AWS Lambda / serverless computer-vision
schematic symbol counter: `app.py`, `serverless.yml`, `templates`, `package.json`, `postsetup.js`) and
replace it with a new platform: a suite of engineering calculation and automation tools for process
systems in the **beverage, food and life-science** sectors.

Primary shape: a **Python API** with an optional **web GUI (NiceGUI)**.

Target capabilities:
1. **P&ID to graph** – parse P&IDs / process flow diagrams (e.g. DEXPI XML, which is likely what "def files" refers to — to be confirmed) into a typed graph of equipment, lines, valves and instruments.
2. **Process calculators** – pipe sizing, pressure drop, pump/NPSH, heat transfer, tank/vessel sizing, CIP, utilities, etc., modelled with **Pydantic** models per industry.
3. **Production scheduling** – derive schedules from recipe data stored as **TOML**.
4. **CAD generation** – basic parametric 3D models using **CadQuery**, exported as **STEP** and **IFC** (for Navisworks).
5. **Diagram editing** – modify DEXPI/P&ID and PFD files programmatically.
6. **Costing & proposals** – cost estimates and engineering proposal support from the above.
7. **Longer term** – fine-tune/pre-train an LLM on DEXPI files, automation source code, URS documents and related text, and orchestrate everything like a **Makefile for engineering**: "build engineering as a service", a platform orchestrating services that mirror our team of experts.

## 2. Reflection

- **Fit:** the old project was image-based symbol counting on a cloud-function stack. The new direction is model-based and structured-data-first. Little code is reusable; the name, branding and BOM concept carry over.
- **Key insight:** the P&ID graph is the central data model. Calculators, schedules, CAD, costing and LLM all read from or write to it, so design it first and keep it stable and versioned.
- **Makefile analogy:** a declarative project file (TOML) listing inputs, targets and dependencies, with a DAG executor that caches and rebuilds only what changed. This suits the "orchestrated experts" vision.
- **Risks:**
  - CadQuery needs OpenCASCADE (heavy install; containerise).
  - IFC for process plant has limited schema coverage (IfcPipeSegment, IfcFlowFitting, IfcTank, IfcPump); expect to map by convention.
  - Calculation correctness and liability: needs unit handling, reference test cases, traceability of assumptions.
  - Licensing of libraries (CadQuery Apache-2.0, IfcOpenShell LGPL, NiceGUI MIT) must be checked for commercial use.
  - LLM work depends on data governance of client URS/source code; defer, and keep it local/private.
  - "Def files" and "lim" are interpreted as DEXPI files and LLM; confirm.
- **Open questions:** target deployment (on-prem vs cloud), which P&ID formats we actually receive, which calculators come first, who the users are (engineers vs sales/estimators).

## 3. Python dependency exploration

| Area | Candidates | Notes |
|---|---|---|
| API | **FastAPI**, uvicorn | Pydantic-native, OpenAPI docs |
| Models/validation | **Pydantic v2**, pydantic-settings | Per-sector model packages |
| Web GUI | **NiceGUI** | Mounts onto FastAPI; pure Python |
| Graph | **NetworkX**; optionally rustworkx; pyvis/Cytoscape for display | |
| P&ID formats | **pyDEXPI** (DEXPI Proteus XML), lxml; ezdxf for DXF | Verify maturity |
| Units | **pint** (or `quantities`) | Mandatory for calculators |
| Process properties | **CoolProp**, **thermo/fluids/ht** (Caleb Bell), **scipy**, numpy | Fluids lib covers pipe/pump/valve sizing |
| Scheduling | stdlib `tomllib` (3.11+), **OR-Tools** CP-SAT, pandas | Recipes in TOML |
| CAD | **CadQuery** (OCP), build123d as alternative | STEP export |
| IFC | **IfcOpenShell** | IFC4 export |
| Reports / BOM | pandas, openpyxl, Jinja2, WeasyPrint | Proposals/costing |
| Orchestration | Custom DAG over TOML; consider **Prefect**/Dagster later, or `doit` | |
| Persistence | SQLModel/SQLAlchemy + SQLite → Postgres; files in object storage | |
| Quality | pytest, hypothesis, ruff, mypy, pre-commit | |
| Packaging | **uv** + pyproject.toml workspace, Docker | |
| LLM (later) | transformers, peft, vLLM/Ollama, sentence-transformers + vector DB (RAG first) | Prefer RAG before fine-tuning |

## 4. Proposed structure (monorepo of services)

```
pipe-bridge/
  pyproject.toml            # uv workspace
  packages/
    pb_core/                # shared Pydantic models, units, P&ID graph schema, IDs
    pb_pid/                 # DEXPI/DXF import-export, graph build, edit operations
    pb_calc/                # calculators; subpackages: common, beverage, food, lifescience
    pb_schedule/            # TOML recipes -> production schedules
    pb_cad/                 # CadQuery generators, STEP, IFC export
    pb_cost/                # BOM, costing, proposal reports
    pb_orchestrator/        # Makefile-like project DAG runner
    pb_llm/                 # (later) RAG/fine-tuning pipelines, datasets
  apps/
    api/                    # FastAPI composition of the services
    gui/                    # NiceGUI front end (calls API)
  examples/                 # sample projects (TOML + DEXPI)
  tests/  docs/  legacy/    # legacy = archived old Lambda app (or removed via git history)
```

Principles: each package has a typed public interface, depends only on `pb_core`, and can be run as a
library, CLI, or API router. Start as a modular monolith; split into separate services only when needed.

Example project file (sketch):
```toml
[project]
name = "Dairy Plant A"
[inputs]
pid = "pid/main.xml"
recipes = "recipes/*.toml"
[targets.calc]   needs = ["pid"]
[targets.schedule] needs = ["recipes"]
[targets.cad]    needs = ["pid", "calc"]
[targets.proposal] needs = ["cad", "schedule", "calc"]
```

## 5. Roadmap

**Phase 0 – Foundations (weeks 1–2)**
- Archive/remove legacy Lambda material; new README; pyproject with uv, ruff, pytest, CI.
- Confirm formats (DEXPI?), sectors and first calculators with the team.

**Phase 1 – Core & P&ID graph (weeks 3–6)**
- `pb_core` models (equipment, line, valve, instrument, stream) with units.
- `pb_pid`: import DEXPI → NetworkX graph; BOM/line list export; basic edits.
- FastAPI endpoints + minimal NiceGUI viewer.

**Phase 2 – Calculators (weeks 6–10)**
- Pipe sizing/pressure drop, pump & NPSH, tank sizing, heat exchanger duty, CIP volumes.
- Sector profiles (beverage, food, life science) via Pydantic models; validated against hand calcs.

**Phase 3 – Recipes & scheduling (weeks 10–13)**
- TOML recipe schema; batch/unit-procedure model; OR-Tools scheduler; Gantt in GUI.
- Link schedule to equipment capacity from the graph.

**Phase 4 – CAD / IFC / STEP (weeks 13–18)**
- Parametric equipment and pipe-run generation from the graph; STEP and IFC4 export; Navisworks check.

**Phase 5 – Costing & proposals (weeks 18–22)**
- Cost database, BOM roll-up, proposal document generation.

**Phase 6 – Orchestrator (weeks 22–26)**
- Declarative project file, DAG runner with caching, reproducible builds, CLI (`pipe-bridge build`).

**Phase 7 – LLM assistance (exploratory, after Phase 6)**
- Curate private corpus (DEXPI, PLC/automation code, URS); start with RAG, evaluate fine-tuning;
  agents calling the services as tools.

Each phase ends with a demo project, tests, and documentation. Timings are indicative only.
