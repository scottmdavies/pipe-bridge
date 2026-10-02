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
1. **P&ID to graph** – parse P&IDs / process flow diagrams (DXF files as the primary input; DEXPI XML as an optional later exchange format) into a typed graph of equipment, lines, valves and instruments.
2. **Process calculators** – pipe sizing, pressure drop, pump/NPSH, heat transfer, tank/vessel sizing, CIP, utilities, etc., modelled with **Pydantic** models per industry.
3. **Production scheduling** – derive schedules from recipe data stored as **TOML**.
4. **CAD generation** – basic parametric 3D models using **CadQuery**, exported as **STEP** and **IFC** (for Navisworks).
5. **Diagram editing** – modify DXF P&ID and PFD files programmatically.
6. **Costing & proposals** – cost estimates and engineering proposal support from the above.
7. **Longer term** – fine-tune/pre-train an LLM on DXF files, automation source code, URS documents and related text, and orchestrate everything like a **Makefile for engineering**: "build engineering as a service", a platform orchestrating services that mirror our team of experts.

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
  - DXF is geometry-first: connectivity may need inference from line endpoints and symbol blocks; agree a layer/block/tag convention.
  - "lim" is read as LLM; confirm.
- **Open questions:** target deployment (on-prem vs cloud), whether DXFs carry intelligent blocks/attributes or are plain geometry (affects whether connectivity must be inferred), which calculators come first, who the users are (engineers vs sales/estimators).

## 3. Python dependency exploration

| Area | Candidates | Notes |
|---|---|---|
| API | **FastAPI**, uvicorn | Pydantic-native, OpenAPI docs |
| Models/validation | **Pydantic v2**, pydantic-settings | Per-sector model packages |
| Web GUI | **NiceGUI** | Mounts onto FastAPI; pure Python |
| Graph | **NetworkX**; optionally rustworkx; pyvis/Cytoscape for display | |
| P&ID formats | **ezdxf** (read/write DXF; block/attribute/layer extraction); optional pyDEXPI/lxml for DEXPI XML | DXF primary; DEXPI later |
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
    pb_pid/                 # DXF import-export (DEXPI optional), graph build, edit operations
    pb_calc/                # calculators; subpackages: common, beverage, food, lifescience
    pb_schedule/            # TOML recipes -> production schedules
    pb_cad/                 # CadQuery generators, STEP, IFC export
    pb_cost/                # BOM, costing, proposal reports
    pb_orchestrator/        # Makefile-like project DAG runner
    pb_llm/                 # (later) RAG/fine-tuning pipelines, datasets
  apps/
    api/                    # FastAPI composition of the services
    gui/                    # NiceGUI front end (calls API)
  examples/                 # sample projects (TOML + DXF)
  tests/  docs/  legacy/    # legacy = archived old Lambda app (or removed via git history)
```

Principles: each package has a typed public interface, depends only on `pb_core`, and can be run as a
library, CLI, or API router. Start as a modular monolith; split into separate services only when needed.

Example project file (sketch):
```toml
[project]
name = "Dairy Plant A"
[inputs]
pid = "pid/main.dxf"
recipes = "recipes/*.toml"
[targets.calc]   needs = ["pid"]
[targets.schedule] needs = ["recipes"]
[targets.cad]    needs = ["pid", "calc"]
[targets.proposal] needs = ["cad", "schedule", "calc"]
```

## 5. Roadmap

**Phase 0 – Foundations (weeks 1–2)**
- Archive/remove legacy Lambda material; new README; pyproject with uv, ruff, pytest, CI.
- Confirm DXF conventions (layers, block/symbol libraries, tag attributes), sectors and first calculators with the team.

**Phase 1 – Core & P&ID graph (weeks 3–6)**
- `pb_core` models (equipment, line, valve, instrument, stream) with units.
- `pb_pid`: import DXF (blocks, attributes, polylines) → NetworkX graph; BOM/line list export; basic edits.
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
- Curate private corpus (DXF, PLC/automation code, URS); start with RAG, evaluate fine-tuning;
  agents calling the services as tools.

Each phase ends with a demo project, tests, and documentation. Timings are indicative only.

## 6. Priority update (2026-10-02): DXF extraction service first

The first deliverable is a standalone **DXF unpacking service** (`pb_pid`, exposed via CLI and a FastAPI endpoint) that reads a DXF and emits a structured YAML (or JSON) document in two views:

1. **Schedule of components** – one record per symbol/block instance: tag, type (block name), layer, position, rotation, attributes (size, rating, service, etc.), plus a summary count per type (a BOM/equipment/valve/instrument list).
2. **Connection map** – graph of nodes (components) and edges (lines/polylines joining connection points), with line attributes (line number, size, spec) where present.

Design notes:
- Pipeline: `ezdxf` read -> classify entities (INSERT blocks, LINE/LWPOLYLINE, TEXT/MTEXT, attributes) by layer/block conventions -> attach nearby text to symbols/lines -> infer connectivity from endpoints within a tolerance, snapped to block connection points -> NetworkX graph -> serialise.
- Output models are Pydantic (`pb_core`) so YAML, JSON and the API schema share one definition; versioned with a `schema_version` field. Write YAML with `ruamel.yaml` or PyYAML.
- A TOML/YAML **mapping config** lets users declare layer names, block-to-type mapping and tolerances per client, since DXF conventions vary.
- Emit warnings for unconnected nodes, dangling lines, and unrecognised blocks rather than failing.
- Test with a few small hand-made DXFs (generated via `ezdxf`) and golden-file YAML comparisons.

Sketch of output:
```yaml
schema_version: 1
source: pid_001.dxf
components:
  - id: V-101
    type: ball_valve
    layer: VALVES
    position: [120.5, 80.0]
    attributes: {size: DN50}
connections:
  - from: T-101
    to: V-101
    line: L-001-DN50
summary: {ball_valve: 4, tank: 2}
```

Revised near-term roadmap: Phase 0 (repo reset) -> **Phase 1a: DXF extract (components YAML)** -> **1b: connection map** -> 1c: API/CLI and mapping config -> then calculators, per the phases above, which consume this output.

## 7. Additions (2026-10-02): DXF round-trip and equipment sizing

### 7.1 DXF round-trip editing (`pb_pid`)
`ezdxf` can write DXF, so the extraction service becomes two-way:
- **Edit labels/attributes:** change `TEXT`/`MTEXT` strings and block attribute values (tag, size, service) on a *copy* of the source DXF.
- **Add or swap parts without drawing:** insert an existing block from a symbol library (a template DXF or `ezdxf` Importer) at a position with attributes; swap a part by changing the block name.
- **Change set model:** users edit the YAML (or submit a patch via the API); the service diffs it against the extracted graph and applies the changes to a new DXF. The original is never overwritten.
- **Known limits:** moving a component requires updating connected pipe endpoints in the graph logic; text resizing/layout is ours to handle; exotic proxy entities may not round-trip; tag convention is needed to match edits to entities.
- Roadmap: Phase 1d, after extraction (1a–1c).

### 7.2 Equipment sizing service (`pb_sizing`)
Worked example: sizing a **cooker**. The method generalises to any batch or semi-continuous equipment:
1. **Demand:** product quantity per period (from orders/forecast/recipe, in TOML).
2. **Schedule:** convert demand to batches using batch size and recipe step times (load, heat, hold, cook, unload, clean/CIP, changeover) to produce a production schedule.
3. **Capacity test:** for N candidate units, simulate or solve the schedule and compute:
   - **Utilisation** = busy time / available time (target typically below ~80–85% to leave headroom; configurable).
   - **Waiting time/queueing** of batches (and of upstream/downstream blocking), makespan and on-time delivery.
4. **Decision:** smallest N (and batch size) meeting utilisation and waiting-time targets; sensitivity to demand growth, downtime and shift pattern.

Approach and dependencies:
- **Pydantic** models for demand, recipe/step, equipment, shifts and targets; **TOML** inputs.
- Start with a deterministic schedule/Gantt (OR-Tools CP-SAT or simple dispatch rules), then add **SimPy** discrete-event simulation with stochastic times/breakdowns for waiting-time distributions; **pandas**/numpy for KPIs; analytic queueing check (M/M/c, Erlang) as a quick sanity bound.
- Output: YAML/JSON report (N units, utilisation, waiting, Gantt data) feeding costing and the P&ID component schedule (e.g. number of cookers to place).
- Roadmap: merges with Phase 3 (recipes and scheduling); the sizing service is the first consumer, so build a **cooker case study** as the reference test with hand-checked numbers.

Revised priority: 1a–1c DXF extraction → 1d round-trip edit → Phase 3 scheduling + sizing (cooker case) → calculators → CAD/costing.
