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

Raw comments or imported text pass through **dictionary and context filtering**, then an **LLM turns them into structured leads**. The backend checks fields against a fixed layout and writes to **MongoDB**; **`fingerprint`** identifies “the same logical lead” so re-running the pipeline updates one row instead of piling duplicates. A **Vue** dashboard pages the HTTP API for read-only viewing; **Streamlit** lets you tweak parameters and launch pipeline stages.

---

## 🔧 Technical notes

- **API**: FastAPI (`RxServer/sentinel_api.py`), routes under `RxServer/routers/`, optional token auth plus slowapi rate limits.  
- **Writes**: Pydantic checks field shapes; URLs and platform labels get normalized rules in **`RxServer/sentinel_contract.py`**, plus **`fingerprint`** for deduping inserts.  
- **Pipeline**: optional **`MediaCrawler/`** crawl → `ProcessCdata/data_filter.py` → `deepseek_processor.py` / `ollama_processor.py` → `RxServer/pipeline_runner.py` to MongoDB or JSONL export.  
- **Ops UI**: Streamlit (`RxServer/webui.py`) with `webui_core.py` spawning subprocesses.  
- **Dashboard**: `SentinelDashboard/` (Vite + Vue 3, Pinia, DataV, ECharts); falls back to static **JSONL** if the API is down.  
- **Local launcher**: **`python start.py`** for API + Streamlit + optional Vite dev.

**Optional figures** under **`docs/assets/`**: **`architecture.png`** (system diagram), **`pipeline-flow.png`** (flowchart), **`dashboard-demo.gif`** (GIF demo), **`streamlit-webui.png`** (Streamlit screenshot).

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
