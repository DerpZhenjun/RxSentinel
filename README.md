# 🔭 RxSentinel — 处方类灰产情报管线

<div align="center">
  <img src="SentinelDashboard/public/logo-rxsentinel.png" width="240" alt="RxSentinel Logo">

  # RxSentinel — 处方类灰产情报管线

  **[English](README_EN.md) / [中文](README.md)**
</div>

感谢 **[MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)** 开源项目：`RxSentinel` 内置的 **`MediaCrawler/`** 爬虫子模块来源于此。**请务必同时阅读并遵守该仓库自带的免责声明与用户义务**，使用前以原项目文档为准。

---

## 📖 项目简介

**RxSentinel** 是一套从爬虫或导入的评论文本出发，经规则过滤和**大模型结构化**后写入 MongoDB、再用 **Vue 数据大屏**展示的一体化管线，可通过 Streamlit 配参并联调各阶段。


## 🔧 技术要点

- **后端**：FastAPI（`RxServer/sentinel_api.py`）、路由在 `RxServer/routers/`，可选用 Token 保护与 slowapi 限流。  
- **数据入库**：通过 Pydantic 检查字段是否符合约定；链接、平台写法会统一格式化； **`RxServer/sentinel_contract.py`** 负责这一套规则与 **`fingerprint`**。  
- **管线**：可选爬取 **`MediaCrawler/`** → `ProcessCdata/data_filter.py` 清洗 → `deepseek_processor.py` / `ollama_processor.py` 用大模型抽取 → `RxServer/pipeline_runner.py` 合并写库或导出 JSONL。  
- **调度**：Streamlit（`RxServer/webui.py`）配合 `webui_core.py` 起子进程。  
- **大屏**：`SentinelDashboard/`（Vite + Vue 3、Pinia、DataV、ECharts）；接口不可用时可读离线 **JSONL**。  
- **本地一键**：根目录 **`python start.py`** 可同时起 API、Streamlit、可选前端 dev。
🔧 技术原理（RxSentinel，简版）

核心业务路径：爬虫或导入的评论与文本，经本地词库与语境过滤后，由大模型整理为固定字段的结构化线索写入 MongoDB；以 fingerprint 关联同一条线索，管线可多次执行并在库内表现为更新而非追加重复记录。

大屏与后端一体：Vue 指挥中心仅通过后端分页接口读取数据；外链是否有效由服务端 check_url 检测。读服务不可用时，可使用预置的聚合 JSONL 作为静态数据源维持展示。

优势特点：采集、清洗、模型抽取、入库与可视化在同一仓库内串联为可重复执行的流水线，由 Streamlit 配置参数并通过子进程调度各阶段，减少多脚本分散维护的成本。


## 🏗️ 系统架构 (System Architecture)

<div align="center">
  <img src="SentinelDashboard/public/System_Architecture_Diagram.png" width="400" alt="RxSentinel System Architecture">
  <p><em>RxSentinel 全栈情报处理管线架构图</em></p>
</div>

---

## 🖥️ 演示与交互 (Demo & Interface)

<div align="center">
  <table border="0">
    <tr>
      <td align="center" width="50%">
        <strong>Vue3 数据大屏演示</strong><br>
        <img src="docs/assets/dashboard-demo.gif" width="100%" alt="Dashboard Demo GIF">
        <br><em>(实时情报分页聚合展示)</em>
      </td>
      <td align="center" width="50%">
        <strong>Streamlit 控制台</strong><br>
        <img src="docs/assets/streamlit-webui.png" width="100%" alt="Streamlit WebUI">
        <br><em>(管线参数配置与脚本调度)</em>
      </td>
    </tr>
  </table>
</div>

---

## ✨ 能力一览（本项目实际）

以下描述 **RxSentinel 仓库内已实现或接入的部分**；多平台爬虫的详细能力与命令行请以 **`MediaCrawler/README.md`** 为准。

| 能力域 | 说明 |
|--------|------|
| 管线编排 | 可选 `MediaCrawler/` → `data_filter.py` → DeepSeek / Ollama 处理器 → `pipeline_runner.py` 写库或导出 |
| 入库字段与去重 | `sentinel_contract.py`：字段校验与格式整理、 **`fingerprint`** 作为 MongoDB 写入主键以避免重复条目；读旧库时可把缺字段的记录补全到当前格式 |
| HTTP API | 线索列表、`/stats`、`check_url` 等；可选用 Bearer Token；slowapi 限流 |
| 运维 UI | `webui.py` + `webui_core.py`（Streamlit） |
| 可视化大屏 | Pinia + DataV + ECharts；失败时降级静态 JSONL |
| 统一启动 | `start.py`：FastAPI + Streamlit + 可选 `npm run dev` |

---

## 🗂️ 仓库结构（核心路径）

| 路径 | 职责 |
|------|------|
| `RxServer/sentinel_api.py` | FastAPI 宿主 |
| `RxServer/routers/` | 路由（健康检查、线索、统计等） |
| `RxServer/sentinel_contract.py` | 入库字段校验、链接/平台名归一、`fingerprint` |
| `RxServer/pipeline_runner.py` | 管线内核与写库侧编排 |
| `RxServer/webui.py` · `webui_core.py` | Streamlit 调度与子进程封装 |
| `ProcessCdata/` | 过滤、DeepSeek/Ollama 处理器、JSON 配置（词库、提示词等） |
| `SentinelDashboard/` | 大屏前端（独立 npm 依赖） |
| `MediaCrawler/` | 多平台爬虫子工程（独立 `requirements.txt`；可选用 uv，见该目录 README） |
| `tests/` | 单元 / 端到端 / 集成测试目录 |
| `start.py` | 本地一键拉起 API / Streamlit / 前端 dev |

---

## 🚀 快速开始

### 前置依赖

- **Python 3.10+**（以本机为准）  
- **Node.js + npm**（大屏）  
- **MongoDB**（完整读写链路）  

仅跑爬虫阶段时，请在 **`MediaCrawler/`** 内按 **[MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)** 文档安装浏览器、Playwright 或 CDP 等。

### 安装

```bash
pip install -r requirements.txt
pip install -r MediaCrawler/requirements.txt   # 仅当需要爬虫阶段时
pip install -r requirements-test.txt         # 仅跑 pytest 时可用轻量依赖，见文件头注释
```

### 配置

1. 根目录：`cp .env.example .env`（Windows：`copy .env.example .env`），填写 **`MONGODB_*`**、`API_SECRET_KEY`（生产务必设置；留空为开发免鉴权）。详见 `.env.example`。  
2. 大屏：`SentinelDashboard/.env.example` → `SentinelDashboard/.env`，**`VITE_API_BASE_URL`** 与 **`VITE_API_SECRET`** 与后端一致。

### 运行（推荐）

```bash
python start.py
```

- API：`http://127.0.0.1:8000`  
- Streamlit：`http://localhost:8501`  
- 大屏 dev：`http://localhost:5173`  

其它：`python start.py --help`（如 `--api-only`、`--no-frontend`）。

**仅 API**

```bash
python RxServer/sentinel_api.py --host 127.0.0.1 --port 8000
```

**仅大屏**（后端需可达）

```bash
cd SentinelDashboard && npm install && npm run dev
```

通过 `start.py` 拉起 API 时，日志默认写入仓库根目录 **`sentinel_api.log`**。

<details>
<summary>📎 <strong>单独运行 MediaCrawler</strong></summary>

`uv sync`、`main.py` 参数、`uvicorn api.main:app` 等均以 **`MediaCrawler/README.md`** 为准；根目录 **`pip`** 依赖与爬虫子工程的依赖互不替代。

</details>

---

## 免责声明

本项目仅供学习与交流；爬虫与数据处理须遵守法律法规及平台协议。RxSentinel 使用了 **[NanmiCoder / MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)** 的实现思路与代码 subtree，**再次感谢原作者的开源贡献**；**关于爬虫、版权声明与免责声明的完整内容，请以 MediaCrawler 官方仓库文档为准并由使用者自行承担相应责任**。
