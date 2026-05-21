"""Streamlit 壳：布局、控件、`PipelineConfig` 组装与子进程 stdout 劫持。

Mongo、shell 编排、AI 推理均在 `pipeline_runner` / `webui_core`，本文不写业务分支。"""

import json
import logging
import os
import re
import sys
import time

import streamlit as st

# `pipeline_runner` import 之前必须把 ProcessCdata 塞进 sys.path，否则 Processor 模块解析失败。
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROCESS_DIR = os.path.join(_ROOT_DIR, "ProcessCdata")
if _PROCESS_DIR not in sys.path:
    sys.path.insert(0, _PROCESS_DIR)

from pipeline_runner import (
    DEFAULT_AI_PROMPT_BODY,
    DEFAULT_CHANNEL_WORDS,
    DEFAULT_CONTEXT_HINTS,
    DEFAULT_DRUG_WORDS,
    DEFAULT_EMOJI_WORD_MAP,
    DEFAULT_HOMOPHONE_MAP,
    DEMO_VERIFY_PLATFORMS,
    FIXED_OUTPUT_REQUIREMENTS,
    READ_OPTIONS,
    SENTINEL_API_FILE,
    STORAGE_OPTIONS,
    DASH_MERGE_OPTIONS,
    ROOT_DIR,
    DASHBOARD_DIR,
    check_db_source_health,
    ensure_sentinel_api_running,
    load_ai_prompt_for_ui,
    load_variant_lexicon_for_ui,
    normalize_platform_name,
    save_prompt_template,
    save_variant_lexicon_for_ui,
    PipelineConfig,
    PipelineRunner,
)

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

_PLATFORM_OPTIONS = ["xhs", "douyin", "kuaishou", "bili", "weibo", "zhihu", "tieba"]
# 与 tests/generate_demo_verify_dataset.py 中 PLATFORMS 对齐（侧边栏用 douyin，数据目录另有 dy 别名）
_DEMO_VERIFY_DEFAULT_PLATFORMS = ["bili", "xhs", "zhihu", "douyin", "tieba", "weibo"]

# 验证集模式：避免 Mongo 与真实中间数据混杂（与 STORAGE_OPTIONS / READ_OPTIONS / DASH_MERGE_OPTIONS 字面量一致）
_DEMO_VERIFY_STORE_LOCAL = STORAGE_OPTIONS[1]  # 只存入本地
_DEMO_VERIFY_READ_LOCAL = READ_OPTIONS[0]  # 从本地读
_DEMO_VERIFY_MERGE_LOCAL = DASH_MERGE_OPTIONS[2]  # 只存入本地


def _sync_demo_verify_stage_prefs(demo_on: bool) -> None:
    """勾选验证集时强制仅本地读写；取消勾选时恢复勾选前的 session 选项。"""
    ss = st.session_state
    defaults = [
        ("crawler_storage_mode", STORAGE_OPTIONS[2]),
        ("filter_storage_mode", STORAGE_OPTIONS[2]),
        ("filter_read_mode", READ_OPTIONS[0]),
        ("ai_storage_mode", STORAGE_OPTIONS[2]),
        ("ai_read_mode", READ_OPTIONS[0]),
        ("dash_merge_mode", DASH_MERGE_OPTIONS[0]),
    ]
    for key, val in defaults:
        if key not in ss:
            ss[key] = val

    prev = ss.get("_prev_demo_verify_cb", False)
    if demo_on and not prev:
        ss["_bk_crawler_storage"] = ss["crawler_storage_mode"]
        ss["_bk_filter_storage"] = ss["filter_storage_mode"]
        ss["_bk_filter_read"] = ss["filter_read_mode"]
        ss["_bk_ai_storage"] = ss["ai_storage_mode"]
        ss["_bk_ai_read"] = ss["ai_read_mode"]
        ss["_bk_dash_merge"] = ss["dash_merge_mode"]
    elif not demo_on and prev:
        ss["crawler_storage_mode"] = ss.get("_bk_crawler_storage", STORAGE_OPTIONS[2])
        ss["filter_storage_mode"] = ss.get("_bk_filter_storage", STORAGE_OPTIONS[2])
        ss["filter_read_mode"] = ss.get("_bk_filter_read", READ_OPTIONS[0])
        ss["ai_storage_mode"] = ss.get("_bk_ai_storage", STORAGE_OPTIONS[2])
        ss["ai_read_mode"] = ss.get("_bk_ai_read", READ_OPTIONS[0])
        ss["dash_merge_mode"] = ss.get("_bk_dash_merge", DASH_MERGE_OPTIONS[0])

    if demo_on:
        ss["crawler_storage_mode"] = _DEMO_VERIFY_STORE_LOCAL
        ss["filter_storage_mode"] = _DEMO_VERIFY_STORE_LOCAL
        ss["filter_read_mode"] = _DEMO_VERIFY_READ_LOCAL
        ss["ai_storage_mode"] = _DEMO_VERIFY_STORE_LOCAL
        ss["ai_read_mode"] = _DEMO_VERIFY_READ_LOCAL
        ss["dash_merge_mode"] = _DEMO_VERIFY_MERGE_LOCAL
        # 验证集管线：安装样本 → AI → 合并；不能与「仅合并」捷径并存
        ss["dash_only_cb"] = False

    ss["_prev_demo_verify_cb"] = demo_on


def _parse_kv(raw: str) -> dict[str, str]:
    """`k:v,k2:v2` 扁平串 → dict；冒号仅存一处拆分，防值内含冒号被截断。"""
    result: dict[str, str] = {}
    for pair in (p.strip() for p in raw.split(",") if p.strip()):
        if ":" in pair:
            k, v = pair.split(":", 1)
            k, v = k.strip(), v.strip()
            if k and v:
                result[k] = v
    return result

# ---------------------------------------------------------------------------
# 自动启动后台服务（每个 Streamlit 实例生命周期内只执行一次）
# ---------------------------------------------------------------------------
@st.cache_resource
def _auto_start_services() -> None:
    """单会话一次性：`ensure_sentinel_api_running`，避免每个 rerun 重复 spawn。"""
    ensure_sentinel_api_running(log_fn=logger.info)

_auto_start_services()

# ---------------------------------------------------------------------------
# 页面配置 + CSS
# ---------------------------------------------------------------------------
st.set_page_config(page_title="RxSentinel 监控调度中心", page_icon="🛰️", layout="wide")
st.markdown("""
<style>
    :root {
        --bg-main: #050a14;
        --bg-card: #0b1526;
        --border-neon: rgba(0, 242, 254, 0.28);
        --text-main: #e7f7ff;
        --text-sub: #8ea8bf;
        --accent: #00f2fe;
        --accent-2: #4facfe;
    }
    .stApp {
        background: radial-gradient(circle at 10% 0%, rgba(79, 172, 254, 0.12), transparent 35%),
                    radial-gradient(circle at 90% 10%, rgba(0, 242, 254, 0.10), transparent 30%),
                    var(--bg-main);
        color: var(--text-main);
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(11, 21, 38, 0.96), rgba(8, 16, 30, 0.96));
        border-right: 1px solid var(--border-neon);
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stSidebar"] label { color: #b8d9ee !important; }
    [data-testid="stSidebar"] .st-emotion-cache-16txtl3 { padding-top: 1.2rem; }
    .main-title {
        font-size: 2.3rem !important; font-weight: 800 !important;
        background: linear-gradient(45deg, var(--accent-2), var(--accent));
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin-bottom: 4px; letter-spacing: 0.4px;
    }
    .sub-title { color: var(--text-sub); font-size: 0.98rem; margin-bottom: 14px; }
    h3 { margin-top: 0.9rem !important; margin-bottom: 0.35rem !important;
         color: #dff6ff !important; letter-spacing: 0.2px; }
    [data-testid="stCaptionContainer"] { margin-bottom: -2rem; }
    [data-testid="stVerticalBlockBorderWrapper"] {
        border: 1px solid var(--border-neon) !important;
        border-radius: 12px !important;
        background: linear-gradient(180deg, rgba(11, 21, 38, 0.86), rgba(7, 14, 26, 0.86));
        box-shadow: 0 8px 26px rgba(0,0,0,0.28), inset 0 0 22px rgba(0,242,254,0.06);
        backdrop-filter: blur(4px);
    }
    [data-testid="stVerticalBlockBorderWrapper"] > div { padding-top: 0.35rem; padding-bottom: 0.2rem; }
    .stSelectbox > div > div,
    .stTextInput > div > div > input,
    .stTextArea textarea,
    .stNumberInput input,
    .stDateInput input {
        background: rgba(10, 24, 40, 0.85) !important;
        color: #dff5ff !important;
        border: 1px solid rgba(79, 172, 254, 0.35) !important;
        border-radius: 8px !important;
    }
    .stSelectbox > div > div:hover,
    .stTextInput > div > div > input:hover,
    .stNumberInput input:hover { border-color: rgba(0, 242, 254, 0.6) !important; }
    .stSelectbox > div > div:focus-within,
    .stTextInput > div > div > input:focus,
    .stTextArea textarea:focus,
    .stNumberInput input:focus {
        box-shadow: 0 0 0 0.18rem rgba(0, 242, 254, 0.18) !important;
        border-color: rgba(0, 242, 254, 0.9) !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #00c2ff, #00f2fe) !important;
        color: #041420 !important; border: none !important;
    }
    .stButton > button[kind="secondary"] {
        background: rgba(255, 95, 95, 0.13) !important;
        color: #ff9fa8 !important;
        border: 1px solid rgba(255, 95, 95, 0.45) !important;
    }
    .stButton > button {
        font-weight: bold; border-radius: 10px;
        padding: 0.5rem 0.85rem; transition: all 0.3s ease-in-out;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 18px rgba(0, 242, 254, 0.24);
    }
    [data-testid="stCodeBlock"] {
        border: 1px solid rgba(0, 242, 254, 0.24); border-radius: 10px;
    }
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #00b7ff, #00f2fe) !important;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 终端输出渲染器（Streamlit 专属）
# ---------------------------------------------------------------------------
class TerminalToStreamlit:
    """ANSI 剥壳 + `\r` 同行刷新模拟终端；环形缓冲防止占位 DOM 膨胀。"""
    def __init__(self, st_placeholder):
        self.placeholder = st_placeholder
        self.logs: list[str] = []
        self.max_lines = 25

    def write(self, data: str) -> None:
        clean = re.sub(r"\x1b\[.*?[@-~]", "", data)
        if not clean.strip():
            return
        if "\r" in clean:
            latest = clean.split("\r")[-1].strip()
            if self.logs:
                self.logs[-1] = latest
            else:
                self.logs.append(latest)
        else:
            self.logs.append(clean.strip())
        if len(self.logs) > self.max_lines:
            self.logs = self.logs[-self.max_lines:]
        self.placeholder.code("\n".join(self.logs), language="shell")

    def flush(self) -> None:
        pass


# ---------------------------------------------------------------------------
# 页面标题
# ---------------------------------------------------------------------------
st.markdown('<div class="main-title">🛰️ RxSentinel 灰产情报调度中心</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">全链路自动化管线：采集 ➔ 清洗 ➔ AI特征提取 ➔ 大屏实时推流</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 左侧边栏：全局参数
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 全局参数配置")
    demo_verify_dataset = st.checkbox(
        "使用内置验证测试数据集（跳过采集/清洗，安装后直接 AI → 大屏）",
        value=False,
        help=(
            "勾选后下方「目标平台」默认选中 bili / xhs / zhihu / douyin / tieba / weibo，可自行增删。"
            "启动时将安装合成 filtered_comments.jsonl；若各平台已有 ai_extracted_channels.jsonl，"
            "则跳过 AI、不重复消耗 API token（除非在「覆盖 AI 分析」中勾选重跑）。"
        ),
        key="demo_verify_dataset_cb",
    )
    demo_verify_backup_filtered = st.checkbox(
        "安装验证集前备份现有 filtered_comments.jsonl（.bak_demo_verify）",
        value=False,
        disabled=not demo_verify_dataset,
        key="demo_verify_backup_filtered_cb",
    )
    if demo_verify_dataset:
        platforms = st.multiselect(
            "🎯 目标平台选择",
            _PLATFORM_OPTIONS,
            default=_DEMO_VERIFY_DEFAULT_PLATFORMS,
            key="platforms_ms_demo_verify",
            help="验证集对上述六平台均含样本；另选平台若无 filtered 文件则 AI 阶段可能跳过。",
        )
    else:
        platforms = st.multiselect(
            "🎯 目标平台选择",
            _PLATFORM_OPTIONS,
            default=["bili"],
            key="platforms_ms_normal",
        )
    st.markdown("---")
    st.subheader("🛠️ 运行策略")
    st.markdown("**数据覆盖策略 (仅对已选平台生效)：**")
    overwrite_all = st.checkbox("🔄 一键强制全量覆盖 (推荐重跑时勾选)", value=False)

    if overwrite_all:
        overwrite_crawler_plats = platforms
        overwrite_filter_plats  = platforms
        overwrite_ai_plats      = platforms
    else:
        with st.expander("高级覆盖细则", expanded=False):
            overwrite_crawler_plats = st.multiselect("覆盖原始数据",  platforms, default=[])
            overwrite_filter_plats  = st.multiselect("覆盖清洗数据",  platforms, default=[])
            overwrite_ai_plats      = st.multiselect("覆盖AI分析",    platforms, default=[])

_sync_demo_verify_stage_prefs(demo_verify_dataset)

# ---------------------------------------------------------------------------
# 主体：模块一 — 数据采集
# ---------------------------------------------------------------------------
st.markdown("### 1️⃣ 数据侦听 (MediaCrawler)")
st.caption("采集参数与原始数据落地策略")
with st.container(border=True):
    col1, col2 = st.columns([1.1, 0.9], gap="large")
    with col1:
        start_date = st.date_input("采集起始日期")
        end_date   = st.date_input("采集结束日期")
    with col2:
        crawl_type = st.selectbox("核心抓取模式", ["search (关键词检索)", "detail (详情抓取)"])
        login_type = st.selectbox("账号鉴权方式", ["qrcode (扫码登录)", "cookie (免登录缓存)"])
    search_keyword = st.text_area(
        "定向搜索关键词（多词请用英文逗号分隔）",
        value=(
            "yn,xyn,药娘,药l娘,mtf,ts,男娘,伪娘,跨性别,跨拉,买糖,卖糖,出糖,收糖,拼糖,团糖,"
            "吃糖记录,怎么买糖,hrt购买,补佳乐,补jj,小补,诺坤复,诺坤,蓝片,白片,爱斯妥,凝胶,"
            "抹的,日特,欧特,倍美力,马尿,戊酸雌二醇,雌二醇,雌激素,小白瓶,色谱龙,色普龙,色色,"
            "cpa,醋酸环丙孕酮,抑安,螺内酯,吃螺,安体舒通,醛固酮,比卡鲁胺,比卡,康士得,"
            "非那雄胺,非那,保法止,抗雄,黄体酮,孕酮,琪宁"
        ),
        height=110,
        help="建议按主题分组维护，使用英文逗号分隔；支持多行编辑。",
    )
    crawler_storage_mode = st.selectbox(
        "爬虫阶段存储策略",
        STORAGE_OPTIONS,
        key="crawler_storage_mode",
        disabled=demo_verify_dataset,
    )

# ---------------------------------------------------------------------------
# 主体：模块二 — 提纯与 AI 研判
# ---------------------------------------------------------------------------
st.markdown("### 2️⃣ 提纯与 AI 研判 (ProcessCdata)")
st.caption("规则清洗 + 大模型提取，支持分阶段落库策略")

(
    lexicon_channels_default, lexicon_drugs_default,
    lexicon_homophones_default, lexicon_emoji_default, lexicon_context_hints_default,
) = load_variant_lexicon_for_ui()

channel_default_str      = ",".join(lexicon_channels_default)
drug_default_str         = ",".join(lexicon_drugs_default)
homophone_default_str    = ",".join([f"{k}:{v}" for k, v in lexicon_homophones_default.items()])
emoji_map_default_str    = ",".join([f"{k}:{v}" for k, v in lexicon_emoji_default.items()])
context_hints_default_str = ",".join(lexicon_context_hints_default)
ai_prompt_default_str    = load_ai_prompt_for_ui()

with st.container(border=True):
    st.markdown("#### 2.1 模型与规则")
    col4, col5 = st.columns([1.1, 0.9], gap="large")
    with col4:
        ai_platform = st.selectbox("🧠 AI 驱动引擎", ["DeepSeek (云端 API)", "Ollama (本地离线)"])
        if ai_platform == "DeepSeek (云端 API)":
            ds_model_display = st.selectbox("🤖 选择 DeepSeek 模型", [
                "deepseek-chat (V3 通用旗舰 - 快)",
                "deepseek-reasoner (R1 深度推理 - 强)",
            ])
            active_model_name = ds_model_display.split(" ")[0]
            ds_api_key = st.text_input("🔑 DeepSeek API Key (必填)", type="password",
                                        help="填写 sk-... 格式的密钥")
        else:
            active_model_name = st.text_input("🤖 输入 Ollama 模型名称", value="qwen3:8b",
                                               help="请确保该模型已在本地 Ollama 中 pull")
            ds_api_key = ""
        max_process = st.number_input("分析条数限额 (0为全量提取)", min_value=0, value=0, step=100)

    with col5:
        clean_strictness = st.select_slider("第一道清洗严格度",
                                             options=["宽松", "标准", "严苛"], value="标准")
        with st.expander("🔧 自定义黑话字典"):
            custom_channels_str = st.text_area("渠道黑话字典",  value=channel_default_str)
            custom_drugs_str    = st.text_area("药物黑话字典",  value=drug_default_str)
            emoji_map_str       = st.text_area(
                "Emoji 映射 (格式: emoji:标准词, 例如 🍬:糖,💊:药)",
                value=emoji_map_default_str,
            )
        with st.expander("🛡️ 对抗变体策略"):
            homophone_map_str  = st.text_area(
                "谐音映射 (格式: 变体:标准词, 例如 趟:糖,唐:糖,薇:微信)",
                value=homophone_default_str,
            )
            context_hints_str  = st.text_area(
                "语境提示词 (逗号分隔，命中后才触发谐音映射)",
                value=context_hints_default_str,
            )

            preview_homophone_map = _parse_kv(homophone_map_str)
            preview_emoji_map     = _parse_kv(emoji_map_str)
            preview_channels = [w.strip() for w in custom_channels_str.split(",") if w.strip()]
            preview_drugs    = [w.strip() for w in custom_drugs_str.split(",")    if w.strip()]
            preview_context  = [w.strip() for w in context_hints_str.split(",")  if w.strip()]

            tool_col1, tool_col2 = st.columns(2)
            with tool_col1:
                save_lexicon_btn = st.button("💾 保存当前策略到规则库", key="save_lexicon_btn")
            with tool_col2:
                st.download_button(
                    label="📤 导出规则库JSON",
                    data=json.dumps({
                        "strong_channel_words": preview_channels,
                        "drug_slang_words": preview_drugs,
                        "homophone_variants": preview_homophone_map,
                        "emoji_word_map": preview_emoji_map,
                        "context_hints": preview_context,
                    }, ensure_ascii=False, indent=2),
                    file_name="variant_lexicon.json",
                    mime="application/json",
                    key="export_lexicon_btn",
                )

        with st.expander("🧠 AI 提示词策略"):
            ai_prompt_str = st.text_area("AI 提示词策略正文", value=ai_prompt_default_str, height=260)
            st.markdown(
                "<div style='margin-top:2px;margin-bottom:0px;color:#8ea8bf;font-size:0.86rem;'>"
                "固定输出协议（JSON字段）已锁定，不允许在此处修改。</div>",
                unsafe_allow_html=True,
            )
            st.code(FIXED_OUTPUT_REQUIREMENTS.strip(), language="text")
            prompt_col1, prompt_col2 = st.columns(2)
            with prompt_col1:
                save_prompt_btn = st.button("💾 保存AI提示词到配置", key="save_prompt_btn")
            with prompt_col2:
                st.download_button(
                    label="📤 导出AI提示词JSON",
                    data=json.dumps(
                        {"prompt_body": ai_prompt_str}, ensure_ascii=False, indent=2
                    ),
                    file_name="ai_prompt_config.json",
                    mime="application/json",
                    key="export_prompt_btn",
                )

    # 即时保存按钮（独立于管道执行）
    if save_prompt_btn:
        save_prompt_template(ai_prompt_str.strip() or DEFAULT_AI_PROMPT_BODY)
        st.success("✅ AI 提示词已写入 ProcessCdata/config/ai_prompt_config.json")
    if save_lexicon_btn:
        save_variant_lexicon_for_ui(
            preview_channels, preview_drugs,
            preview_homophone_map, preview_emoji_map, preview_context,
        )
        st.success("✅ 对抗变体策略已写入 ProcessCdata/config/variant_lexicon.json")

    st.markdown("#### 2.2 阶段读写策略")
    if demo_verify_dataset:
        st.info(
            "验证集模式已启用：**爬虫 / 清洗 / AI 存储与读取**及**大屏合并**固定为「只存入本地 + 从本地读」，"
            "不向 Mongo 写入中间结果；取消勾选「使用内置验证测试数据集」后，下列选项会恢复为勾选前的配置。"
            "**再次启动**：若本地已有各平台 `ai_extracted_channels.jsonl`，将**跳过 AI、不要求 API Key**；"
            "仅重装样本并合并大屏。需要重跑 AI 时，在侧边栏「覆盖 AI 分析」勾选平台。"
        )
    s1, r1 = st.columns(2, gap="large")
    with s1:
        filter_storage_mode = st.selectbox(
            "清洗阶段存储策略",
            STORAGE_OPTIONS,
            key="filter_storage_mode",
            disabled=demo_verify_dataset,
        )
    with r1:
        filter_read_mode = st.selectbox(
            "清洗阶段读取策略",
            READ_OPTIONS,
            key="filter_read_mode",
            disabled=demo_verify_dataset,
        )
    s2, r2 = st.columns(2, gap="large")
    with s2:
        ai_storage_mode = st.selectbox(
            "AI分析阶段存储策略",
            STORAGE_OPTIONS,
            key="ai_storage_mode",
            disabled=demo_verify_dataset,
        )
    with r2:
        ai_read_mode = st.selectbox(
            "AI分析阶段读取策略",
            READ_OPTIONS,
            key="ai_read_mode",
            disabled=demo_verify_dataset,
        )

    st.markdown("#### 2.3 验证测试集（小规模 · 省 token）")
    st.caption(
        "在**左侧边栏**勾选「使用内置验证测试数据集」后，目标平台默认包含 "
        "bili / xhs / zhihu / douyin / tieba / weibo；对照清单见 "
        "`ProcessCdata/data/_demo_verify/demo_verify_expectations.json`。"
    )
    st.caption("内置样本涉及目录标识：" + ", ".join(sorted(DEMO_VERIFY_PLATFORMS)))

# ---------------------------------------------------------------------------
# 主体：模块三 — 大屏推流
# ---------------------------------------------------------------------------
st.markdown("### 3️⃣ 指挥中心推流 (SentinelDashboard)")
st.caption("合并策略 + 大屏服务端口")
with st.container(border=True):
    dash_only = st.checkbox(
        "仅合并并推流大屏（跳过采集、清洗、AI）",
        key="dash_only_cb",
        disabled=demo_verify_dataset,
        help=(
            "本地已有各平台 ai_extracted_channels.jsonl 时可用：直接进入阶段四并重新合并大屏，不要求 DeepSeek Key。"
            "（勾选侧边栏「内置验证测试数据集」时不可用：验证集必须先安装样本并跑 AI。）"
        ),
    )
    if demo_verify_dataset:
        st.caption(
            "验证集模式下已关闭「仅合并」捷径：启动后将安装样本 → 执行 AI → 再合并写入大屏。"
            "合并仅写本地 JSONL、**不入 Mongo**；大屏默认仍请求 API，若与文件不一致，请在 "
            "`SentinelDashboard/.env` 设置 `VITE_USE_JSONL_FIRST=true` 并重启 `npm run dev`，"
            "或取消验证集后改用合并「同时入库和存入本地」。"
        )
    dash_merge_mode = st.selectbox(
        "大屏合并输出策略",
        DASH_MERGE_OPTIONS,
        key="dash_merge_mode",
        disabled=demo_verify_dataset,
        help=(
            "「同时」写入 public/extracted_channels.jsonl（离线兜底）并 upsert Mongo sentinel_leads（API 数据源）；"
            "「只入库」仅更新数据库；「只存入本地」仅写 JSONL；「跳过」不执行合并与入库。"
            "（勾选验证集时固定为「只存入本地」，避免入库干扰正式数据。）"
        ),
    )
    col6, col7 = st.columns([1, 3])
    with col6:
        dash_port = st.number_input("大屏前端端口", value=5173, step=1)
    with col7:
        st.info("💡 提示：数据流转完成后，大屏 Node.js 服务将在后台自动静默启动。")

# ---------------------------------------------------------------------------
# 执行总控
# ---------------------------------------------------------------------------
st.markdown("---")
col_start, col_stop = st.columns([4, 1])

db_source_warnings = check_db_source_health(platforms, filter_read_mode, ai_read_mode)
for msg in db_source_warnings:
    st.warning(f'⚠️ {msg} 建议先运行上游阶段，或切回"从本地读"。')

with col_start:
    start_btn = st.button("🚀 启动全链路自动化管线", type="primary", use_container_width=True)
with col_stop:
    stop_btn = st.button("⏹ 紧急停止", type="secondary", use_container_width=True)

if stop_btn:
    st.warning("任务已被手动停止。")
    st.stop()

if start_btn:
    if not platforms:
        st.error("操作受阻：请在左侧边栏选择至少一个目标平台。")
        st.stop()
    if demo_verify_dataset and dash_only:
        st.error(
            "**验证集与「仅合并并推流大屏」不能同时使用。**\n\n"
            "- **跑内置验证集**：取消勾选「仅合并…」（验证集启动时会自动关掉该项），直接启动即可；管线会安装样本 → AI → 合并。\n"
            "- **只想重新合并大屏**（已有各平台 `ai_extracted_channels.jsonl`）：请在侧边栏**取消**「使用内置验证测试数据集」，再勾选「仅合并…」。"
        )
        st.stop()

    st.markdown("### 📡 指挥中心日志终端")
    progress_bar        = st.progress(0, text="初始化系统管线...")
    terminal_placeholder = st.empty()
    st_terminal          = TerminalToStreamlit(terminal_placeholder)

    # 解析词库 KV 字符串
    custom_homophone_map = _parse_kv(homophone_map_str)
    custom_emoji_map     = _parse_kv(emoji_map_str)
    custom_channels_list = [w.strip() for w in custom_channels_str.split(",") if w.strip()]
    custom_drugs_list    = [w.strip() for w in custom_drugs_str.split(",")    if w.strip()]
    custom_context_hints = [w.strip() for w in context_hints_str.split(",")  if w.strip()]

    # 构造管道配置
    config = PipelineConfig(
        platforms               = platforms,
        start_date              = str(start_date),
        end_date                = str(end_date),
        crawl_type              = crawl_type.split(" ")[0],
        login_type              = login_type.split(" ")[0],
        search_keyword          = search_keyword,
        crawler_storage_mode    = crawler_storage_mode,
        filter_storage_mode     = filter_storage_mode,
        ai_storage_mode         = ai_storage_mode,
        filter_read_mode        = filter_read_mode,
        ai_read_mode            = ai_read_mode,
        ai_platform             = ai_platform,
        active_model_name       = active_model_name,
        ds_api_key              = ds_api_key,
        max_process             = int(max_process),
        custom_ai_prompt        = ai_prompt_str.strip(),
        custom_channels_list    = custom_channels_list,
        custom_drugs_list       = custom_drugs_list,
        custom_homophone_map    = custom_homophone_map,
        custom_emoji_map        = custom_emoji_map,
        custom_context_hints    = custom_context_hints,
        overwrite_crawler_plats = list(overwrite_crawler_plats),
        overwrite_filter_plats  = list(overwrite_filter_plats),
        overwrite_ai_plats      = list(overwrite_ai_plats),
        dash_only               = dash_only,
        demo_verify_dataset     = demo_verify_dataset,
        demo_verify_backup_filtered = demo_verify_backup_filtered,
        dash_merge_mode         = dash_merge_mode,
        dash_port               = int(dash_port),
        clean_strictness        = clean_strictness,
    )

    runner = PipelineRunner(
        config      = config,
        log_fn      = st_terminal.write,
        toast_fn    = st.toast,
        progress_fn = lambda pct, text="": progress_bar.progress(pct, text=text),
    )

    original_stdout, original_stderr = sys.stdout, sys.stderr
    pipeline_error = None
    try:
        sys.stdout = st_terminal
        sys.stderr = st_terminal
        runner.run_full_pipeline()
    except Exception as exc:
        progress_bar.empty()
        st_terminal.write(f"\n🛑 任务中止: {exc}")
        st.warning("系统已停止当前任务。")
        pipeline_error = exc
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr

    if pipeline_error is None:
        st.toast("🎉 全链路任务大功告成！", icon="🎊")
        st.success("✅ **所有管线执行完毕！指挥大屏数据流已就绪。**")
        st.info(f"👉 **点击即刻访问可视化大屏：[http://localhost:{dash_port}](http://localhost:{dash_port})**")
        time.sleep(2)
        progress_bar.empty()
