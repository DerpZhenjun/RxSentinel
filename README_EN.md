# 🔭 RxSentinel — Prescription gray-market intelligence pipeline

<div align="center">

**[中文版 / README.md](README.md)** · **`sentinel_leads` v2 contract**

Sourcing → rule-based scrubbing → LLM extraction → contract-backed Mongo upserts → read-only Vue dashboard

</div>

---

> **⚠️ Disclaimer (summary)**
>
> This repository is intended for **technical study and compliant security / OSINT-style analysis**. Crawling via the bundled **`MediaCrawler/`** submodule may interact with third-party platforms—follow applicable laws and site terms.**No illegal use.** You are solely responsible for data handling and publication. Full disclaimer [below](#disclaimer).

---

## 📖 Overview

RxSentinel turns **raw comments or imports** into **structured leads** via **lexicon/context filtering**, **LLM structuring**, and **Pydantic-validated ingest (`sentinel_leads` v2)** into **MongoDB** with **fingerprint-based idempotency**. A **Vue** dashboard consumes paginated HTTP APIs; **Streamlit** can configure and spawn subprocess stages.

### 🔧 Figure / asset guide

Use these **names / types** when adding visuals under **`docs/assets/`**:

| Suggested filename | Type | What to depict |
|--------------------|------|----------------|
| `docs/assets/logo-rxsentinel.png` | Logo / brand mark | Ops-center look, navy + cyan accent, flat vector; see prompt at bottom |
| `docs/assets/architecture.png` | **System architecture diagram** | RxServer, ProcessCdata, MongoDB, SentinelDashboard; `MediaCrawler/` as optional ingest |
| `docs/assets/pipeline-flow.png` | **Flowchart** | Crawl → `data_filter` → DeepSeek/Ollama → `pipeline_runner` (Mongo / JSONL) |
| `docs/assets/dashboard-demo.gif` | **Demo GIF** | Virtualized dashboard, paging, KPIs—no fabricated business metrics |
| `docs/assets/streamlit-webui.png` | **Screenshot** | Streamlit pipeline / subprocess UI |

Fallback: `docs/assets/logo-placeholder.png`.

---

## ✨ What this repo actually provides

Capabilities below describe **RxSentinel** itself. Detailed **multi-platform crawler feature matrices** belong to **`MediaCrawler/README*.md`** (upstream project).

| Area | Notes |
|------|--------|
| Pipeline | Optional crawl (`MediaCrawler/`) → filter (`ProcessCdata/data_filter.py`) → AI (`deepseek_processor.py`, `ollama_processor.py`) → merge / publish (`RxServer/pipeline_runner.py`) |
| Contract | `RxServer/sentinel_contract.py`: v2 shapes, URL/platform normalization, deterministic **`fingerprint`**, legacy doc upgrades on read |
| HTTP API | `RxServer/sentinel_api.py`: leads, `/stats`, `check_url`; optional Bearer; **slowapi** limits |
| Ops UI | `RxServer/webui.py`, `RxServer/webui_core.py` (Streamlit) |
| Dashboard | `SentinelDashboard/`: Vite + Vue 3, Pinia, DataV, ECharts; **static JSONL fallback** |
| Launcher | Root `start.py`: FastAPI + Streamlit + optional Vite dev |

**Optional table extension** · **Table name**: capability vs dependency columns · **Type**: Markdown · **Suggestion**: columns for minimal versions / required vs optional (Python, Node, Mongo, DeepSeek key, Ollama, Playwright/CDP).

---

## 🗂️ Repository layout (core paths)

**Table name**: Directory responsibilities · **Type**: Markdown table

| Path | Role |
|------|------|
| `RxServer/sentinel_api.py` | FastAPI host |
| `RxServer/routers/` | HTTP routes |
| `RxServer/sentinel_contract.py` | Contract & normalization |
| `RxServer/pipeline_runner.py` | Pipeline orchestration toward Mongo/export |
| `RxServer/webui.py` · `webui_core.py` | Streamlit operator UI |
| `ProcessCdata/` | Filters, shared AI helpers, processors, JSON configs |
| `SentinelDashboard/` | Dashboard SPA (npm) |
| `MediaCrawler/` | Stand-alone crawler subtree (**its own** `requirements.txt`; may use **uv** per that README) |
| `tests/` | `unit` / `e2e` / `integration` (Mongo for integration) |
| `start.py` | Local all-in-one launcher |

---

## 🚀 Quick start

### Prerequisites

- **Python 3.10+** (3.12 also observed; use what matches your env)
- **Node.js + npm** (dashboard)
- **MongoDB** (full read/write loop)

If you **only** run the crawler, follow **`MediaCrawler/README.md`** for browsers, Playwright or CDP, etc.

### Install

```bash
pip install -r requirements.txt
pip install -r MediaCrawler/requirements.txt   # only if you need the crawl stage
pip install -r requirements-test.txt         # pytest-oriented subset; see file header
```

### Configuration

1. Root: copy `.env.example` → `.env`; set **`MONGODB_*`**, **`API_SECRET_KEY`** (empty = dev no-auth—set in production). See inline comments in `.env.example`.  
2. Dashboard: `SentinelDashboard/.env.example` → `SentinelDashboard/.env`; align **`VITE_API_BASE_URL`** & **`VITE_API_SECRET`**.

### Run (recommended)

```bash
python start.py
```

- API: `http://127.0.0.1:8000`  
- Streamlit: `http://localhost:8501`  
- Dashboard dev: `http://localhost:5173`  

`python start.py --help` (`--api-only`, `--no-frontend`, …).

**API only**

```bash
python RxServer/sentinel_api.py --host 127.0.0.1 --port 8000
```

**Dashboard only** (backend must be reachable)

```bash
cd SentinelDashboard && npm install && npm run dev
```

When the API child is spawned by `start.py`, logs go to **`sentinel_api.log`** at repo root.

<details>
<summary>📎 <strong>Running MediaCrawler standalone</strong></summary>

Commands such as **`uv sync`**, `main.py` flags, or `uvicorn api.main:app` are documented **inside `MediaCrawler/`**. RxSentinel’s root **`pip`** requirements do **not** replace the crawler subtree’s dependency story.

</details>

---

## 🔐 Contract & idempotency (short)

**Contract**: enforced shapes before Mongo writes (**`LeadContract`** / helpers in `sentinel_contract.py`). **Idempotency**: **`fingerprint`** keys upserts so replays dedupe logically identical leads.

---

## 🧪 Tests & contributing

1. Fork → branch → focused PRs.  
2. Python: `pytest tests/unit tests/e2e`; integration: **`pytest tests/integration -m integration`** (Mongo).  
3. Frontend: `cd SentinelDashboard && npm test`.

---

## 🗺️ Roadmap

- [ ] Add root **`LICENSE`** (today only **`MediaCrawler/`** ships one).  
- [ ] Optional **Docker Compose** (no Dockerfile in repo yet).  
- [ ] Wire **pytest + Vitest** into CI as needed.

---

## License

There is **no top-level LICENSE** yet. Follow **`MediaCrawler/`**’s bundled license when using that subtree; add an explicit root license before publishing broadly.

---

## Logo generation prompt (optional)

Target asset: **`logo-rxsentinel.png`**, **type**: flat brand logo.

> Minimalist flat vector logo, name "RxSentinel", dark navy background, thin cyan grid lines, shield or radar glyph merged with a subtle medical-cross hint, high contrast, no decorative text, square 1024×1024, GitHub README friendly.

---

## Disclaimer

### 1. Purpose

RxSentinel is provided for **technical education and research** on data pipelines—not for circumventing laws or terms of service.

### 2. Compliance

You must comply with applicable regulations and platform agreements. Liability for scraping, storage, or display rests with the operator.

### 3. MediaCrawler submodule

`MediaCrawler/` carries its own disclaimer and documentation. Evaluate legality independently before operational use.

### 4. General

Authors do not warrant fitness for production or accept liability for damages arising from use or misuse.

---

**Figure checklist**: `logo-rxsentinel.png` (logo), `architecture.png` (architecture), `pipeline-flow.png` (flowchart), `dashboard-demo.gif` (GIF), `streamlit-webui.png` (screenshot) → place under **`docs/assets/`**.
