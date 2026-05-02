# RxSentinel

**[中文版 README](README.md)** · Pipeline for sourcing → rule-based filtering → LLM extraction → contract-backed Mongo writes → read-only dashboard

---

## Logo

![RxSentinel Logo](docs/assets/logo-placeholder.png) <!-- Placeholder: replace with real asset URL/path -->

**Image-gen prompt (logo, DALL·E / Midjourney)**

> Minimalist flat vector logo, name "RxSentinel", dark navy background, thin cyan grid lines, shield or radar glyph merged with a subtle medical-cross hint, high contrast, no decorative text, square 1024×1024, GitHub README friendly.

---

## Overview

RxSentinel wires **raw crawler comments → lexicon/context filtering → LLM structuring → idempotent Mongo upserts → Vue dashboard**. The backend uses a **Pydantic contract (`sentinel_leads` v2)** for ingest and read paths; **Streamlit** drives subprocess orchestration; the dashboard uses **Pinia + DataV + ECharts**, paging the API with a **static JSONL fallback** when the gateway fails.

---

## Highlights

- **Four-stage pipeline**: crawl (`MediaCrawler`) → filter (`data_filter.py`) → AI (`deepseek_processor.py` / `ollama_processor.py`) → merge + publish (`pipeline_runner`).
- **Contract + fingerprints**: URL normalization, platform aliases, deterministic `fingerprint`; read path can upgrade legacy documents.
- **HTTP API**: `/api/sentinel/leads`, `/stats`, `check_url`; optional Bearer auth; slowapi rate limits.
- **Dashboard**: virtualized list, incremental paging, URL aliveness cache.
- **Launcher**: `python start.py` brings up FastAPI, optional Vite dev server, and Streamlit web UI.

---

## Architecture

| Layer | Path / notes |
|------|----------------|
| API host | `RxServer/sentinel_api.py`, routers under `RxServer/routers/` |
| Contract | `RxServer/sentinel_contract.py` |
| Pipeline core | `RxServer/pipeline_runner.py`, `RxServer/webui_core.py` |
| Ops UI | `RxServer/webui.py` (Streamlit) |
| Filter / AI | `ProcessCdata/` (lexicon + prompt JSON configs) |
| Dashboard | `SentinelDashboard/` (Vite + Vue 3) |
| Crawler | `MediaCrawler/` (**separate** `requirements.txt`) |

![Architecture](docs/assets/architecture.png) <!-- Type: diagram · RxServer / ProcessCdata / Mongo / Dashboard / MediaCrawler -->

![Pipeline flow](docs/assets/pipeline-flow.png) <!-- Type: flowchart · four stages + Mongo / JSONL branches -->

---

## Quick start

### Prerequisites

- Python **3.10+**
- **Node.js** + npm (dashboard)
- **MongoDB** (full stack)
- Crawling: additionally `pip install -r MediaCrawler/requirements.txt`

### Install

```bash
pip install -r requirements.txt
pip install -r MediaCrawler/requirements.txt   # only if you need the crawl stage
pip install -r requirements-test.txt        # lighter stack for pytest only; see file header
```

### Configuration

1. Copy `.env.example` → `.env` at repo root (`MONGODB_*`, `API_SECRET_KEY`).  
2. Copy `SentinelDashboard/.env.example` → `SentinelDashboard/.env`; align `VITE_API_BASE_URL` and `VITE_API_SECRET` with the backend (empty secret = dev no-auth on both sides).

### Run

**All-in-one launcher**

```bash
python start.py
```

- API: `http://127.0.0.1:8000`  
- Streamlit: `http://localhost:8501`  
- Dashboard dev: `http://localhost:5173`  

See `python start.py --help` for `--api-only`, `--no-frontend`, etc.

**API only**

```bash
python RxServer/sentinel_api.py --host 127.0.0.1 --port 8000
```

**Dashboard only** (backend must be reachable)

```bash
cd SentinelDashboard && npm install && npm run dev
```

API logs (when spawned via `start.py`): `sentinel_api.log` at repo root.

---

## Screenshots / demo

![Dashboard GIF](docs/assets/dashboard-demo.gif) <!-- Demo GIF -->

![Streamlit UI](docs/assets/streamlit-webui.png) <!-- Screenshot -->

---

## Roadmap

- [ ] Add a root **`LICENSE`** (today only `MediaCrawler/` ships its own license file).  
- [ ] Optional **Docker Compose** for Mongo + API + built frontend (**no Dockerfile in repo yet**).  
- [ ] Wire **pytest + Vitest** into CI if desired.

---

## Contributing

1. Fork → branch → focused PR.  
2. Python: `pytest tests/unit tests/e2e`; integration needs Mongo: `pytest tests/integration -m integration`.  
3. Frontend: `cd SentinelDashboard && npm test`.

---

## License

There is **no top-level `LICENSE` file** in this repository yet; follow the license bundled under **`MediaCrawler/`** when using that subtree. Add an explicit root license before publishing as OSS.
