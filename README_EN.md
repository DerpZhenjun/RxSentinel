# 🔭 RxSentinel — Prescription gray-market intelligence pipeline

<div align="center">

**[中文版 / README.md](README.md)**

</div>

---

Thanks to the open-source project **[MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)**: the **`MediaCrawler/`** subtree bundled here comes from it. **Please read and follow that repository’s disclaimer and usage terms** (including crawl and compliance notes) before you run anything crawler-related—treat upstream docs as the source of truth.

---

## Logo

![RxSentinel Logo](docs/assets/logo-placeholder.png)

**Suggested asset**: `docs/assets/logo-rxsentinel.png` · **Type**: logo / flat vector mark · navy + cyan, ops-console style works well. Place assets under **`docs/assets/`**.

---

## 📖 Overview

**RxSentinel** is a **complete prescription gray-market intelligence pipeline system**. It starts from comment text collected via multi-platform crawlers or manual import, passes through **rule-based filtering** and **LLM-powered structured extraction**, writes results to MongoDB with automatic **deduplication** via `fingerprint`, and finally visualizes everything on a **Vue data dashboard**—all orchestrated by an interactive **Streamlit UI**.

### 🎯 Core Value Proposition

- **Intelligent collection**: Multi-platform crawlers (Bilibili, TikTok, Kuaishou, Weibo, Xiaohongshu, Zhihu, Tieba, etc.); also supports manual data import  
- **Automatic deduplication**: `fingerprint` + MongoDB unique index ensures same-source records update-once, not duplicate  
- **Structured processing**: AI transforms unstructured comments into standard fields (product, merchant, platform, sentiment, etc.)  
- **Multi-channel queries**: HTTP API, Streamlit UI, Vue dashboard—three ways to explore the data  
- **Flexible storage**: Support MongoDB-only, local-only, or dual-storage modes  
- **Real-time monitoring**: Stream pipeline logs and progress in Streamlit during execution

---

## � Core Pipeline (Four Stages)

```
┌────────────────────────────────────────────────────────────────────┐
│                     RxSentinel Data Pipeline                         │
├────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  [1] Collect       [2] Clean       [3] AI Process     [4] Store    │
│  ───────────────────────────────────────────────────────────   │
│                                                                       │
│  MediaCrawler  →  data_filter.py  →  DeepSeek/  →  MongoDB     │
│  or import data      rule filtering     Ollama        + FastAPI     │
│                      ✓ dedupe            ✓ structure   + Vue board    │
│                      ✓ normalize        ✓ standard    + Streamlit    │
│                      ✓ clean errors     ✓ biz logic   + stats        │
│                                                                       │
│  Stages run via subprocess.Popen streams; Streamlit shows real-time  │
│                                                                       │
└────────────────────────────────────────────────────────────────────┘
```

### 📍 Stage Details

| Stage | Module | Function |
|-------|--------|----------|
| **1️⃣ Collect** | `MediaCrawler/` | Multi-platform crawler (Bilibili, TikTok, Kuaishou, Weibo, Xiaohongshu, Zhihu, Tieba); or import via API |
| **2️⃣ Clean** | `ProcessCdata/data_filter.py` | Rule/dict filtering, deduplication, format normalization |
| **3️⃣ AI Process** | `deepseek_processor.py` / `ollama_processor.py` | LLM extraction into standard fields via `ai_processor_common.py` |
| **4️⃣ Store & View** | `pipeline_runner.py` + API + Vue | Dedupe via `fingerprint`, write to MongoDB; query via HTTP/UI/dashboard |

---

## 🔧 Technical Architecture

- **API & Middleware**: **FastAPI** + **Uvicorn** (`RxServer/sentinel_api.py`)  
  - **Index Strategy on startup** via **`lifespan`** with **PyMongo**:  
    - **Unique index** on `fingerprint` (prevents duplicates)  
    - **Compound indexes** on `(ingested_at, platform, merchant, source_platform)` (accelerates dashboard queries)  
  - **Route organization** under **`RxServer/routers/`** (e.g., `health`, `leads`, `stats`)  
  - **Authentication**: If **`API_SECRET_KEY`** is set, checks byte-exact **`Authorization: Bearer …`** header; empty = dev mode (no auth)  
  - **Rate limiting**: **slowapi** limits by client IP to prevent abuse  
  - **CORS policy**: **CORSMiddleware** whitelists common local **Vite** origins for front-end dev

- **Read API & URL Verification**: **`routers/leads.py`** provides three services  
  - **Paged queries**: Filter, sort, and paginate results; aggregate by platform, merchant, date range  
  - **Aggregated stats** (`/stats` endpoint): Summary data (platform distribution, merchant rankings, temporal trends)  
  - **Link verification** (`check_url`): Server-side HTTP proxy with **TTL in-memory cache** (avoids CORS in browser, detects soft 404s via HTML sniffing)  
  - **Legacy doc upgrade**: On list reads, can trigger **`upgrade_existing_doc`** to back-fill missing fields in old docs and write them back (unordered bulk operation)  
  - **Type-safe responses**: All list/paginate structures use **Pydantic** models for schema safety

- **Write Path & Deduplication**: **`sentinel_contract.py`** normalizes data for MongoDB writes  
  - **Field validation**: **Pydantic `LeadContract`** ensures required fields, enforces data types  
  - **URL normalization**: Maps Bilibili BV/av/dynamics, generic URLs, etc. to a standard format  
  - **Platform aliasing**: Unifies platform display names to canonical identifiers  
  - **Fingerprint generation**: Builds stable `fingerprint` from `(source_url, platform, merchant)` to uniquely identify logical leads  
  - **Dedupe on write**: **`pipeline_runner.py`** calls **`to_contract_doc`** for normalization, then **PyMongo `UpdateOne`** combined with **unique index** ensures: **same-source records update one row**, not pile duplicates

- **Pipeline Orchestration Engine**: **`pipeline_runner.py`** unifies four stages  
  - **Stage chaining**: Collect → Clean → AI Process → Write/Export  
  - **Stream log capture**: Each stage runs as **`subprocess.Popen`**, **`pipeline_runner.py`** real-time fetches and buffers stdout/stderr, relays to Streamlit for live progress  
  - **Unified AI interface**: **`ai_processor_common.py`** provides  
    - **Shared prompt templates** for LLM structuring  
    - Support for **DeepSeek** (OpenAI-compatible API)  
    - Support for **Ollama** (local model inference)  
  - **Optional visualization**: Can generate charts with **matplotlib** and save them  
  - **Storage strategy** via **`STORAGE_OPTIONS`** / **`READ_OPTIONS`**:  
    - MongoDB only  
    - Local JSON/JSONL only  
    - Both simultaneously

- **Ops UI (Streamlit)**: **`RxServer/webui.py`** + **`webui_core.py`** work together  
  - **Config panel**: Streamlit forms for user to set crawler params, filter rules, AI model settings; assembles into **`PipelineConfig`**  
  - **Real-time monitoring**: Logs, progress bars, error alerts injected into **`PipelineRunner.run_full_pipeline()`** execution  
  - **Helper utilities**: **`webui_core.py`** encapsulates subprocess management, MongoDB sync, config validation, etc.

- **Vue Dashboard (Frontend)**: **Vue 3 + Vite + Pinia + @kjgl77/datav-vue3 + ECharts + axios** (see `SentinelDashboard/package.json`)  
  - **High-fidelity ops board**: DataV component library creates TV-screen-style dashboards; ECharts renders live charts  
  - **State management**: Pinia centralizes app state for real-time reactivity  
  - **Link liveness**: Calls backend **check_url** to verify external URLs; avoids browser CORS pain  
  - **Graceful fallback**: If API is down, auto-reads local bundled **JSONL** for basic dashboard display

- **Unified Launcher**: Root **`python start.py`** brings up the full stack  
  - **Background subprocess**: Spawns **FastAPI** (`sentinel_api.py`) in subprocess  
  - **Optional frontend**: Can optionally spawn **`npm run dev`** for Vite dev server  
  - **Blocking UI**: Starts **Streamlit** (`webui.py`) in foreground (blocks terminal)  
  - **API logs**: Captured to **`sentinel_api.log`** at repo root  
  - **Custom startup modes**: Supports `--api-only`, `--no-frontend` flags (see `--help`)

**Optional assets** in **`docs/assets/`**: **`architecture.png`**, **`pipeline-flow.png`**, **`dashboard-demo.gif`**, **`streamlit-webui.png`**.

---

## ✨ What this repo provides

RxSentinel features below—**not** MediaCrawler’s full platform matrix—see **`MediaCrawler/README.md`** for crawler details.

| Area | Notes |
|------|--------|
| Pipeline | Optional `MediaCrawler/` → `data_filter.py` → DeepSeek / Ollama processors → `pipeline_runner.py` |
| Field checks & dedupe | `sentinel_contract.py` validates/normalizes payloads; **`fingerprint`** Mongo key avoids duplicate docs; reads can retrofit older rows to the latest layout |
| HTTP API | Leads listing, `/stats`, `check_url`, optional Bearer, slowapi |
| Ops UI | `webui.py` + `webui_core.py` (Streamlit) |
| Dashboard | DataV / ECharts; JSONL fallback |
| Launcher | `start.py` |

---

## 🗂️ Repository layout (core paths)

| Path | Role |
|------|------|
| `RxServer/sentinel_api.py` | FastAPI host |
| `RxServer/routers/` | HTTP routes |
| `RxServer/sentinel_contract.py` | Field validation, URL/platform normalization, `fingerprint` |
| `RxServer/pipeline_runner.py` | Pipeline orchestration toward Mongo/export |
| `RxServer/webui.py` · `webui_core.py` | Streamlit UI + subprocess helpers |
| `ProcessCdata/` | Filters, DeepSeek/Ollama processors, JSON configs |
| `SentinelDashboard/` | Dashboard SPA (npm) |
| `MediaCrawler/` | Crawler subtree (own `requirements.txt`; uv supported per README) |
| `tests/` | Unit / e2e / integration tests |
| `start.py` | One-shot local launcher |

---

## 🚀 Quick start

### Prerequisites

- **Python 3.10+**  
- **Node.js + npm** (dashboard)  
- **MongoDB** (full stack)  

Browser / Playwright / CDP setup for crawling lives in **`MediaCrawler/`** — follow **[MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)** upstream docs.

### Install

```bash
pip install -r requirements.txt
pip install -r MediaCrawler/requirements.txt   # only if you need the crawl stage
pip install -r requirements-test.txt         # pytest-focused subset; see file header
```

### Configuration

1. Root `.env.example` → `.env` with **`MONGODB_*`** and **`API_SECRET_KEY`** (empty = dev no-auth).  
2. `SentinelDashboard/.env.example` → `SentinelDashboard/.env`: **`VITE_API_BASE_URL`**, **`VITE_API_SECRET`**.

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

**Dashboard only** (reachable backend)

```bash
cd SentinelDashboard && npm install && npm run dev
```

API stdout/stderr from `start.py`: **`sentinel_api.log`** at repo root.

<details>
<summary>📎 <strong>Running MediaCrawler alone</strong></summary>

Commands like `uv sync`, `main.py` flags, or `uvicorn api.main:app` are documented under **`MediaCrawler/`**. Root **`pip`** deps do **not** replace crawler deps.

</details>

---

## 🗺️ Roadmap

- [ ] Add root **`LICENSE`** (only **`MediaCrawler/`** ships one today).  
- [ ] Optional **Docker Compose** (no Dockerfile yet).  
- [ ] Hook **pytest + Vitest** into CI as needed.

---

## License

No top-level `LICENSE` yet. Using **`MediaCrawler/`** must follow **[the upstream repo](https://github.com/NanmiCoder/MediaCrawler)** licensing and disclaimers bundled there.

---

## Logo prompt (optional)

> Minimalist flat vector logo, name "RxSentinel", dark navy background, thin cyan grid lines, shield or radar glyph merged with a subtle medical-cross hint, high contrast, no decorative text, square 1024×1024, GitHub README friendly.

---

## Disclaimer

For study and collaboration only—obey laws and platform terms around crawling and data use. RxSentinel embeds subtree code from **[NanmiCoder / MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)**; **thank you again to the original authors**. **For crawler-related legal notices, disclaimers, and IP terms, follow the official MediaCrawler repository—you remain responsible for how you deploy it.**
