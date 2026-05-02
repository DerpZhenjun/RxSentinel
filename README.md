# 🔭 RxSentinel — 处方类灰产情报管线

<div align="center">

**[English / README_EN.md](README_EN.md)** · **`sentinel_leads` v2 契约**

采集 → 规则清洗 → LLM 结构化抽取 → MongoDB 幂等写入 → Vue 大屏只读消费

</div>

---

> **⚠️ 免责声明（摘要）**
>
> 本仓库用于**技术研究、安全与合规舆情分析**学习与实验。内含或对接的爬虫子模块（`MediaCrawler/`）可能涉及第三方平台数据采集，请务必遵守所在地法律法规及平台用户协议；**禁止用于违法违规行为**。数据使用与出镜责任由使用者自担。下文「免责声明」附有完整条目。

[跳转到完整免责声明](#免责声明)

---

## 📖 项目简介

RxSentinel 将 **爬虫/导入的原始评论与文本**，经 **词库与语境规则过滤**，再由 **大模型抽取为结构化线索**，按 **Pydantic 契约（`sentinel_leads` v2）** 写入 **MongoDB**（指纹幂等），最终由 **Vue 大屏**分页调用 HTTP API 展示；调度侧可通过 **Streamlit** 配置参数并驱动子进程跑通管线。

### 🔧 技术要点

| 图名（建议文件名） | 类型 | 建议内容概要 |
|-------------------|------|----------------|
| `docs/assets/logo-rxsentinel.png` | Logo / 品牌标识 | 指挥中心风格、深蓝 + 青色、扁平矢量；可参考 README 内 Logo 绘图提示词 |
| `docs/assets/architecture.png` | **系统架构图** | RxServer、ProcessCdata、MongoDB、SentinelDashboard、`MediaCrawler/` 采集子模块间的数据与控制流 |
| `docs/assets/pipeline-flow.png` | **流程图（泳道或顺序图）** | 四阶段：采集 → `data_filter` → DeepSeek/Ollama → `pipeline_runner` 写库 / 导出 JSONL |
| `docs/assets/dashboard-demo.gif` | **演示 GIF** | 大屏虚拟列表、分页、指标区；不含虚假业务数据 |
| `docs/assets/streamlit-webui.png` | **界面截图** | Streamlit 管线参数与子进程编排页 |

可选用占位图：`docs/assets/logo-placeholder.png`（若尚未准备正式 Logo）。

---

## ✨ 能力一览（本项目实际）

以下为 **RxSentinel 仓库内已实现或集成的能力**（与上游 `MediaCrawler` 独立文档中的「多平台爬虫功能矩阵」不同；爬虫细节以 **`MediaCrawler/README.md`** 为准）。

| 能力域 | 说明 |
|--------|------|
| 管线编排 | 采集（可选，`MediaCrawler/`）→ 清洗（`ProcessCdata/data_filter.py`）→ AI（`deepseek_processor.py` / `ollama_processor.py`）→ 合并写库 / 导出（`RxServer/pipeline_runner.py`） |
| 数据契约 | `RxServer/sentinel_contract.py`：`sentinel_leads` v2、URL / 平台归一、确定性 **`fingerprint`**、读路径可升级遗留文档 |
| HTTP API | `RxServer/sentinel_api.py`：线索列表、`/stats`、`check_url`；可选 Bearer；**slowapi** 限流 |
| 运维 UI | `RxServer/webui.py`（Streamlit）与 `RxServer/webui_core.py` |
| 可视化大屏 | `SentinelDashboard/`：Vite + Vue 3、Pinia、DataV、ECharts；接口失败时可读静态 **JSONL** |
| 统一启动 | 根目录 `start.py`：FastAPI、`streamlit`、`npm run dev`（可选） |

**【表占位 · 可选】**  
**表名**：能力与外部依赖对照 · **类型**：扩展 Markdown 表 · **建议**：增列「最低版本 / 是否必选」（Python、Node、Mongo、DeepSeek API Key、Ollama、Playwright/CDP）。

---

## 🗂️ 仓库结构（核心路径）

**表名：核心目录职责** · **类型：Markdown 表**

| 路径 | 职责 |
|------|------|
| `RxServer/sentinel_api.py` | FastAPI 宿主 |
| `RxServer/routers/` | 路由（健康检查、线索、统计等） |
| `RxServer/sentinel_contract.py` | 契约与规范化 / 指纹 |
| `RxServer/pipeline_runner.py` | 管线内核与写库侧编排 |
| `RxServer/webui.py` · `webui_core.py` | Streamlit 调度与子进程封装 |
| `ProcessCdata/` | 过滤、通用 AI 逻辑、DeepSeek/Ollama 处理器、JSON 配置（词库、提示词） |
| `SentinelDashboard/` | 大屏前端（独立 `npm` 依赖） |
| `MediaCrawler/` | 多平台爬虫子工程（**独立** `requirements.txt`；可选用 **uv**，见该目录 README） |
| `tests/` | `unit` / `e2e` / `integration`（集成测试依赖 Mongo） |
| `start.py` | 本地一键拉起 API / Streamlit / 前端 dev |

---

## 🚀 快速开始

### 前置依赖

- **Python 3.10+**（本仓库可在 3.12 等版本下运行；以本机为准）
- **Node.js + npm**（大屏）
- **MongoDB**（完整读写链路）

若仅运行 **爬虫阶段**：需在 `MediaCrawler/` 内按该项目说明安装浏览器/Playwright/CDP（详见 **`MediaCrawler/README.md`**）。

### 安装

```bash
pip install -r requirements.txt
pip install -r MediaCrawler/requirements.txt   # 仅当需要爬虫阶段时
pip install -r requirements-test.txt         # 仅跑 pytest 时可用轻量依赖，见文件头注释
```

### 配置

1. 根目录：`cp .env.example .env`（Windows：`copy .env.example .env`），填写 **`MONGODB_*`**、`API_SECRET_KEY`（生产务必设置；留空为开发免鉴权）。详见 `.env.example` 注释。  
2. 大屏：`SentinelDashboard/.env.example` → `SentinelDashboard/.env`，**`VITE_API_BASE_URL`** 与 **`VITE_API_SECRET`** 与后端一致。

### 运行（推荐）

```bash
python start.py
```

- API：`http://127.0.0.1:8000`  
- Streamlit：`http://localhost:8501`  
- 大屏 dev：`http://localhost:5173`  

其它模式：`python start.py --help`（如 `--api-only`、`--no-frontend`）。

**仅 API**

```bash
python RxServer/sentinel_api.py --host 127.0.0.1 --port 8000
```

**仅大屏**（后端需可达）

```bash
cd SentinelDashboard && npm install && npm run dev
```

通过 `start.py` 启动 API 时，日志默认写入仓库根目录 **`sentinel_api.log`**。

<details>
<summary>📎 <strong>关于 MediaCrawler 子模块单独运行</strong></summary>

爬虫命令、**uv sync**、`main.py` 参数与 WebUI（`uvicorn api.main:app`）等，均以 **`MediaCrawler/README.md`** 为准；RxSentinel 根目录 **`pip`** 路径与爬虫子工程的 **独立依赖集**并行存在，互不替代。

</details>

---

## 🔐 数据契约与幂等（简要）

**契约**：`LeadContract` 等模型规定入库字段形状；`to_contract_doc` 将宽松 dict 归一并通过校验。**幂等**：`fingerprint` 作为 Mongo upsert 键，同源重复管线重放不倍增记录。详情见源码 `RxServer/sentinel_contract.py`。

---

## 🧪 测试与贡献

1. Fork → 分支 → 聚焦单一主题的 PR。  
2. Python：`pytest tests/unit tests/e2e`；集成：**`pytest tests/integration -m integration`**（需 Mongo）。  
3. 前端：`cd SentinelDashboard && npm test`。

---

## 🗺️ 路线图

- [ ] 根目录补充 **`LICENSE`**（当前仅 **`MediaCrawler/`** 自带许可文件）。  
- [ ] 可选：**Docker Compose**（Mongo / API / 前端构建产物；仓库内暂无 Dockerfile）。  
- [ ] CI：按需接入 **pytest + Vitest**。

---

## 许可证

仓库 **根目录当前未包含** `LICENSE`。使用 **`MediaCrawler/`** 时请遵守该子目录许可证；对外分发前建议在根目录增加与组织策略一致的许可证文本。

---

## Logo 绘图提示词（可选）

适用于 DALL·E / Midjourney 等生成 **Logo（图名：`logo-rxsentinel`，类型：品牌矢量图）**：

> Minimalist flat vector logo, name "RxSentinel", dark navy background, thin cyan grid lines, shield or radar glyph merged with medical cross hint, high contrast, no decorative text, square 1024×1024, GitHub README friendly.  
> 中文：科技感指挥中心、深蓝 / 青色霓虹、扁平、留白足、禁止写实照片风格。

---

# 免责声明

## 1. 项目性质

RxSentinel 作为**数据采集、清洗与展示链路**的学习与技术研究之用，侧重于合规场景下的结构与工程实践。**不得将本仓库用于任何违法或侵犯第三方权益的活动。**

## 2. 合规与责任

使用者须遵守适用法律、监管机构要求及各平台协议。因爬虫、数据处理或展示而产生的法律责任由使用者自行承担。

## 3. 子模块 MediaCrawler

`MediaCrawler/` 的来源项目包含独立免责声明；其爬取能力与风控要求以该目录文档为准。**商业或大规模使用前请单独评估合法性。**

## 4. 一般免责

作者在能力范围内力求仓库说明准确，不就因使用或无法使用本仓库导致的直接或间接损失承担责任。

---

**【图占位汇总】**：`logo-rxsentinel.png`（Logo）、`architecture.png`（架构图）、`pipeline-flow.png`（流程图）、`dashboard-demo.gif`（GIF）、`streamlit-webui.png`（截图）；均应放入 **`docs/assets/`**（可自行建目录）。
