# 🔭 RxSentinel — 处方类灰产情报管线

<div align="center">
  <img src="SentinelDashboard/public/logo-rxsentinel.png" width="240" alt="RxSentinel Logo">

  # RxSentinel — 处方类灰产情报管线

  **[English](README_EN.md) / [中文](README.md)**
</div>

感谢 **[MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)** 开源项目：`RxSentinel` 内置的 **`MediaCrawler/`** 爬虫子模块来源于此。**请务必同时阅读并遵守该仓库自带的免责声明与用户义务**，使用前以原项目文档为准。



## 📖 项目简介

**RxSentinel** 是一套完整的**处方类灰产情报管线系统**。它从多平台爬虫采集或手动导入的社媒评论文本出发，经过规则过滤和**大模型结构化处理**后写入 MongoDB，再用 **Vue 数据大屏**展示，可通过 **Streamlit 调度 UI** 配参并实时监控各阶段执行。

### 🎯 核心价值

- **智能采集**：集成 MediaCrawler 多平台爬虫（B站、抖音、快手、微博、小红书、知乎、贴吧等），也支持手动导入
- **自动去重**：通过 `fingerprint` + MongoDB 唯一索引，同源线索反复处理只更新不重复
- **结构化处理**：AI 将非结构化评论转换为标准字段（商品、商家、平台、情感等）
- **即时查询**：HTTP API、Streamlit UI、Vue 可视化大屏三端支持
- **灵活存储**：支持仅入库、仅本地、同时存储等多种模式
- **实时监控**：Streamlit 中流式展示管线执行日志和进度


## � 核心流程（四阶段管线）

```
┌─────────────────────────────────────────────────────────────────────┐
│                     RxSentinel 完整数据流程                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  [1] 采集          [2] 清洗        [3] AI处理        [4] 存储展示    │
│  ────────────────────────────────────────────────────────────────   │
│                                                                       │
│  MediaCrawler  →  data_filter.py  →  DeepSeek/  →  MongoDB 写库    │
│  或导入数据           规则过滤        Ollama处理    + FastAPI查询    │
│                   ✓ 去重              ✓ 字段结构化  + Vue 大屏      │
│                   ✓ 格式整理          ✓ 标准提示词  + Streamlit UI  │
│                   ✓ 清洗异常          ✓ 业务逻辑    + 聚合统计      │
│                                                                       │
│  阶段间通过 subprocess.Popen 流式拉取日志，Streamlit 实时展示       │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### 📍 各阶段详解

| 阶段 | 模块 | 功能说明 |
|------|------|----------|
| **1️⃣ 采集** | `MediaCrawler/` | 多平台爬虫采集社媒评论、用户信息；或通过 API 手动导入数据 |
| **2️⃣ 清洗** | `ProcessCdata/data_filter.py` | 基于词库、规则过滤无效数据，去重，格式规范化 |
| **3️⃣ AI处理** | `deepseek_processor.py` / `ollama_processor.py` | 使用 DeepSeek/Ollama 对文本进行结构化提取，生成标准字段 |
| **4️⃣ 存储展示** | `pipeline_runner.py` + API + Vue | 通过 `fingerprint` 去重写入 MongoDB，HTTP API 查询，大屏可视化 |

---

## �🔧 技术要点

- **API 与中间件**：**FastAPI** + **Uvicorn**（`RxServer/sentinel_api.py`）
  - 启动时 **`lifespan`** 中用 **PyMongo** 对 `sentinel_leads` 集合建立：
    - **唯一索引**：`fingerprint`（避免重复插入）
    - **组合索引**：`(ingested_at, platform, merchant, source_platform)` 等（加速大屏排序筛选）
  - 路由统一管理在 **`RxServer/routers/`**（如 `health`、`leads`、`stats`）
  - **认证**：`API_SECRET_KEY` 非空则校验 `Authorization: Bearer …` 完整字符串；空值则本机开发默认放行
  - **限流**：**slowapi** 按访问 IP 限流，防止单点滥用
  - **跨域**：**CORSMiddleware** 放行常见本地 **Vite** 端口，便于前后端分离调试

- **读接口与探链**：**`routers/leads.py`** 提供三类服务
  - **分页查询**：支持过滤、排序、分页；可按平台、商家、日期范围聚合
  - **聚合统计**：**`/stats`** 端点返回汇总数据（平台分布、商家排名、时间趋势等）
  - **链接验证**：**`check_url`** 代理端做 HTTP 请求（绕开浏览器 CORS），带 **TTL 内存缓存**；对 B 站等用短读 HTML 片段识别「软 404」
  - **字段补全**：读库列表时可触发 **`upgrade_existing_doc`**，把旧文档缺失字段补成当前版本后写回（无序 bulk 操作）
  - **响应格式**：所有列表与分页结构用 **Pydantic** 模型描述，确保类型安全

- **写路径与去重**：**`sentinel_contract.py`** 实现核心数据规范化
  - **字段校验**：**Pydantic `LeadContract`** 确保入库数据格式统一、必填字段完整
  - **URL 归一化**：将 B 站 BV/av/动态链接、通用 HTTP 等多种形式统一为标准格式
  - **平台别名处理**：映射各平台显示名到规范标识符
  - **指纹生成**：根据 `source_url`、`platform`、`merchant` 等字段生成稳定的 **`fingerprint`**
  - **去重写入**：**`pipeline_runner.py`** 调用 **`to_contract_doc`** 转换后，**PyMongo `UpdateOne`** 结合集合上 **唯一索引**保证：同源记录反复跑管线时 **仅更新一行**，而不会堆积重复文档

- **管线编排引擎**：**`pipeline_runner.py`** 统一调度四个阶段
  - **阶段链接**：采集 → 清洗 → AI处理 → 写库/导出
  - **日志流式采集**：各阶段以 **`subprocess.Popen`** 并发运行，**`pipeline_runner.py`** 实时拉取和缓冲子进程的 stdout/stderr，通过 Streamlit 展示进度
  - **统一 AI 接口**：**`ai_processor_common.py`** 提供统一的提示词构建和请求封装
    - 支持 **DeepSeek** (OpenAI 兼容 API)
    - 支持 **Ollama** (本地大模型)
  - **可视化输出**：可选使用 **matplotlib** 生成图表并保存
  - **灵活存储策略**：通过 **`STORAGE_OPTIONS`** / **`READ_OPTIONS`** 配置
    - 仅入库 MongoDB
    - 仅保存本地 JSON/JSONL
    - 同时存储

- **调度 UI（Streamlit）**：**`RxServer/webui.py`** 与 **`webui_core.py`** 联动
  - **配置编辑**：Streamlit 表单让用户设置爬虫参数、清洗规则、AI 模型参数等，组装为 **`PipelineConfig`**
  - **实时监控**：日志、进度条、错误提示等注入到 **`PipelineRunner.run_full_pipeline()`** 的执行过程
  - **辅助工具**：**`webui_core.py`** 封装子进程管理、MongoDB 同步、配置验证等逻辑

- **大屏前端**：**Vue 3 + Vite + Pinia + @kjgl77/datav-vue3 + ECharts + axios**（见 `SentinelDashboard/package.json`）
  - **高性能仪表板**：基于 DataV 组件搭建电子屏展示风格，使用 ECharts 渲染动态图表
  - **状态管理**：Pinia 集中管理应用状态，支持实时响应
  - **链接验证**：外链存活状态调用后端 **check_url** 接口，避免浏览器差异与跨域困扰
  - **容错降级**：API 不可用时自动降级读本地聚合 **JSONL** 文件，保证可用性

- **一键启动**：根目录 **`python start.py`** 统一拉起全栈
  - 后台子进程启动 **FastAPI** (`sentinel_api.py`)
  - 可选启动前端 dev 服务 **`npm run dev`**
  - 前台阻塞启动 **Streamlit** (`webui.py`)
  - API 日志默认写入 **`sentinel_api.log`**（根目录）
  - 支持 `--api-only`、`--no-frontend` 等参数定制启动模式

**可选配图**（按需放入 **`docs/assets/`**）：**`architecture.png`**（系统架构图）、**`pipeline-flow.png`**（流程图）、**`dashboard-demo.gif`**（演示 GIF）、**`streamlit-webui.png`**（Streamlit 截图）。

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

## 🗺️ 路线图

- [ ] 根目录补充 **`LICENSE`**（当前仅 **`MediaCrawler/`** 自带许可文件）。  
- [ ] 可选：**Docker Compose**（Mongo / API / 前端产物；仓库内暂无 Dockerfile）。  
- [ ] 按需接入 **pytest + Vitest** CI。

---

## 许可证

仓库 **根目录当前未包含** `LICENSE`。使用 **`MediaCrawler/`** 时请遵守该子目录许可与 **[原项目说明](https://github.com/NanmiCoder/MediaCrawler)**。

---

## Logo 绘图提示词（可选）

> Minimalist flat vector logo, name "RxSentinel", dark navy background, thin cyan grid lines, shield or radar glyph merged with medical cross hint, high contrast, no decorative text, square 1024×1024, GitHub README friendly.  
> 科技感指挥中心、深蓝 / 青色、扁平矢量、留白足、不要写实照片。

---

## 免责声明

本项目仅供学习与交流；爬虫与数据处理须遵守法律法规及平台协议。RxSentinel 使用了 **[NanmiCoder / MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)** 的实现思路与代码 subtree，**再次感谢原作者的开源贡献**；**关于爬虫、版权声明与免责声明的完整内容，请以 MediaCrawler 官方仓库文档为准并由使用者自行承担相应责任**。
