# RxSentinel

**[English](README_EN.md)** · 处方类灰产情报：采集 → 清洗 → LLM 抽取 → 契约落库 → 大屏只读消费

---

## Logo

![RxSentinel Logo](docs/assets/logo-placeholder.png) <!-- 占位：替换为实际 Logo URL 或相对路径 -->

**AI 绘图提示词（Logo，可贴 DALL-E / Midjourney）**

> Minimalist flat vector logo, name "RxSentinel", dark navy background, thin cyan grid lines, shield or radar glyph merged with medical cross hint, high contrast, no decorative text, square 1024×1024, GitHub README friendly.  
> 中文补充：科技感指挥中心、冷静配色（深蓝 / 青色霓虹）、扁平、留白足、禁止写实照片风格。

<!-- 若尚无 docs/assets/ 目录，请自建并放入 Logo，或改用外链图床 -->

---

## 简介

RxSentinel 把 **爬虫原始评论 → 词典与语境规则过滤 → 大模型结构化抽取 → MongoDB 幂等写入 → Vue 大屏展示** 串成一条可重复的链路。后端通过 **Pydantic 契约（sentinel_leads v2）** 统一入库与读路径；调度侧用 **Streamlit** 配参、跑子进程；展示侧用 **Pinia + DataV + ECharts** 分页拉取 API，离线时可读聚合 JSONL。

---

## 核心特性

- **四阶段编排**：采集（MediaCrawler）/ 清洗（`data_filter.py`）/ AI（DeepSeek 云端或 Ollama 本地）/ 合并写库与推大屏（`pipeline_runner`）。
- **契约与指纹**：URL 归一、平台别名收口、`fingerprint` 确定性生成；读路径可对遗留文档做回填升级。
- **API**：`/api/sentinel/leads`、`/stats`、`check_url`（外链探活）；可选 Bearer 鉴权；slowapi 限流。
- **大屏**：虚拟列表、触底分页、`check_url` 状态缓存；API 异常时降级静态 JSONL。
- **统一启动**：`python start.py` 拉起 FastAPI、（可选）Vite、`streamlit run webui`。

---

## 技术架构

| 层级 | 目录 / 说明 |
|------|-------------|
| 宿主 API | `RxServer/sentinel_api.py`，路由 `RxServer/routers/` |
| 契约 | `RxServer/sentinel_contract.py` |
| 管线内核 | `RxServer/pipeline_runner.py`、`RxServer/webui_core.py` |
| 调度 UI | `RxServer/webui.py`（Streamlit） |
| 清洗 / AI | `ProcessCdata/`（含词库与提示词配置 JSON） |
| 可视化 | `SentinelDashboard/`（Vite + Vue 3） |
| 采集 | `MediaCrawler/`（独立依赖，见该目录 `requirements.txt`） |

![系统架构](docs/assets/architecture.png) <!-- 类型：架构图 · 建议内容：RxServer / ProcessCdata / Mongo / SentinelDashboard / MediaCrawler 数据流 -->

![管线流程](docs/assets/pipeline-flow.png) <!-- 类型：流程图 · 建议内容：四阶段与 Mongo、public JSONL 分支 -->

---

## 快速上手

### 环境

- Python **3.10+**（仓库内可见 3.12 运行痕迹；按本机为准）
- **Node.js** + npm（大屏）
- **MongoDB**（完整链路）
- 若跑爬虫：**单独安装** `MediaCrawler/requirements.txt`

### 安装（后端 / 管线）

```bash
pip install -r requirements.txt
pip install -r MediaCrawler/requirements.txt   # 仅当需要爬虫阶段时
pip install -r requirements-test.txt        # 仅跑 pytest 时可替代精简安装，见该文件说明
```

### 配置

1. 复制根目录 `.env.example` → `.env`，按需填写 `MONGODB_*`、`API_SECRET_KEY`。  
2. 复制 `SentinelDashboard/.env.example` → `SentinelDashboard/.env`，`VITE_API_BASE_URL` 与 `VITE_API_SECRET` 与后端对齐（密钥为空则开发与后端一致为「免鉴权」）。

### 运行

**一键（推荐本地联调）**

```bash
python start.py
```

- API：`http://127.0.0.1:8000`  
- Streamlit：`http://localhost:8501`  
- 大屏 dev：`http://localhost:5173`  

其他模式：`python start.py --help`（`--api-only`、`--no-frontend` 等）。

**仅 API**

```bash
python RxServer/sentinel_api.py --host 127.0.0.1 --port 8000
```

**仅大屏（需后端已reachable）**

```bash
cd SentinelDashboard && npm install && npm run dev
```

日志：`start.py` 会将 API 子进程 stdout/stderr 写入仓库根目录 `sentinel_api.log`（若使用该启动路径）。

---

## 视觉展示

![大屏演示](docs/assets/dashboard-demo.gif) <!-- 类型：演示 GIF · 建议：大屏三栏 + 刷新数据 -->

![调度 WebUI](docs/assets/streamlit-webui.png) <!-- 类型：截图 · Streamlit 管线参数页 -->

<!-- 暂无素材时保留占位；勿使用虚假业绩数据配图 -->

---

## 路线图

- [ ] 根目录补充统一 **开源许可证**（当前仅 `MediaCrawler/` 自带许可文件）  
- [ ] 可选：**Docker Compose** 编排 Mongo / API / 前端构建产物（仓库内 **尚未提供** Dockerfile）  
- [ ] CI：pytest + Vitest 门禁（已有测试目录，可按需接入流水线）  

---

## 贡献

1. Fork → 分支 → PR，改动聚焦单一主题。  
2.  Python：`pytest tests/unit tests/e2e`；集成测试需 Mongo：`pytest tests/integration -m integration`。  
3. 前端：`cd SentinelDashboard && npm test`。  

---

## 许可证

仓库 **根目录当前未包含** `LICENSE` 文件；使用捆绑的 **`MediaCrawler/`** 时请遵守该子目录许可声明。对外开源前建议在根目录添加与组织策略一致的许可证文本。
