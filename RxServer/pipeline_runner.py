"""四阶段编排内核（无 Streamlit）：采集 → 清洗 → AI 抽取 → 合并推大屏。

日志 / Toast / 进度条 / 子进程外壳一律回调注入，便于单测替桩与 CLI 复用。
WebUI 仅组装 `PipelineConfig`（含 `dash_merge_mode` 阶段四策略）并调用 `PipelineRunner.run_full_pipeline()`。"""

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Callable

import requests
from pymongo import MongoClient, UpdateOne

logger = logging.getLogger(__name__)

# 路径锚点：pipeline_runner → RxServer → 仓库根
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(_MODULE_DIR)
CRAWLER_DIR = os.path.join(ROOT_DIR, "MediaCrawler")
PROCESS_DIR = os.path.join(ROOT_DIR, "ProcessCdata")
DASHBOARD_DIR = os.path.join(ROOT_DIR, "SentinelDashboard")

if PROCESS_DIR not in sys.path:
    sys.path.insert(0, PROCESS_DIR)
from lead_noise_gate import is_obvious_noise_lead  # noqa: E402
SENTINEL_API_FILE = os.path.join(_MODULE_DIR, "sentinel_api.py")
VARIANT_LEXICON_FILE = os.path.join(PROCESS_DIR, "config", "variant_lexicon.json")

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
MONGO_DB_NAME = "Oestrogen"
MONGO_COLLECTION = "sentinel_leads"

STORAGE_OPTIONS = ["只入库", "只存入本地", "同时入库和存入本地"]
READ_OPTIONS    = ["从本地读", "从数据库读"]

# 阶段四：合并 AI 产出 → 大屏 JSONL / Mongo sentinel_leads
DASH_MERGE_SKIP = "跳过（不入库、不写本地）"
DASH_MERGE_OPTIONS = ["同时入库和存入本地", "只入库", "只存入本地", DASH_MERGE_SKIP]

# 内置验证集（tests/generate_demo_verify_dataset.py）所覆盖的平台目录名
DEMO_VERIFY_PLATFORMS = frozenset({"bili", "xhs", "zhihu", "dy", "douyin", "tieba", "weibo", "wb"})

from pipeline_defaults import (  # noqa: E402
    DEFAULT_CHANNEL_WORDS,
    DEFAULT_CONTEXT_HINTS,
    DEFAULT_DRUG_WORDS,
    DEFAULT_EMOJI_WORD_MAP,
    DEFAULT_HOMOPHONE_MAP,
)

# ProcessCdata 由入口注入 sys.path；此处不强改全局路径。
# 导入失败则桩化：无 AI 模板亦可跑采集 / 清洗冒烟。
try:
    from ai_processor_common import (
        DEFAULT_AI_PROMPT_BODY,
        FIXED_OUTPUT_REQUIREMENTS,
        load_prompt_body,
        save_prompt_template,
    )
except ImportError:
    DEFAULT_AI_PROMPT_BODY = ""
    FIXED_OUTPUT_REQUIREMENTS = ""
    load_prompt_body = lambda default="": default
    save_prompt_template = lambda body: None

try:
    from sentinel_contract import to_contract_doc
    from webui_core import sync_stage_files_to_mongo as _sync_core
except ImportError:
    to_contract_doc = None
    _sync_core = None


def run_shell_command(cmd: str, cwd: str, log_fn: Callable) -> int:
    """子进程 `shell=True` 串流 stdout/stderr 合一管道 → `log_fn`（终端/HTML 由上层决定）。"""
    logger.info("Running shell command: %s (cwd=%s)", cmd, cwd)
    _env = os.environ.copy()
    _env["PYTHONIOENCODING"] = "utf-8"
    process = subprocess.Popen(
        cmd, cwd=cwd, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        env=_env,
    )
    try:
        for line in process.stdout:
            log_fn(line)
        process.wait()
    except Exception as exc:
        process.terminate()
        logger.error("Shell command failed: %s — %s", cmd, exc)
        raise
    finally:
        if process.poll() is None:
            process.terminate()
    logger.info("Shell command finished returncode=%d: %s", process.returncode, cmd)
    return process.returncode


def _default_spawn(cmd: str, cwd: str) -> None:
    """静默后台拉起 API / `npm run dev`；stdout/stderr 丢弃以免阻塞 Streamlit。"""
    subprocess.Popen(
        cmd, shell=True, cwd=cwd,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def ensure_sentinel_api_running(
    log_fn: Callable,
    api_port: int = 8000,
    spawn_fn: Callable[[str, str], None] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> None:
    """`/api/health` 探活短路；离线则拉起 `sentinel_api.py`。`spawn_fn`/`sleep_fn` 单测可 noop。"""
    _spawn = spawn_fn or _default_spawn
    _sleep = sleep_fn or time.sleep

    health_url = f"http://127.0.0.1:{api_port}/api/health"
    try:
        resp = requests.get(health_url, timeout=1.5)
        if resp.ok:
            log_fn(f"🛰️ Sentinel API 已在线: {health_url}")
            return
    except Exception:
        pass

    if not os.path.exists(SENTINEL_API_FILE):
        log_fn(f"⚠️ 未找到 Sentinel API 文件: {SENTINEL_API_FILE}")
        return

    log_fn(f"🛰️ 正在启动 Sentinel API 服务 (端口: {api_port}) ...")
    logger.info("Spawning Sentinel API: %s --port %d", SENTINEL_API_FILE, api_port)
    _spawn(f'python "{SENTINEL_API_FILE}" --port {api_port}', ROOT_DIR)
    _sleep(1.5)


def normalize_platform_name(platform_value: str) -> str:
    raw = str(platform_value or "").strip().lower()
    if raw in {"推", "推特", "twitter", "x"}:
        return "推特"
    if raw in {"tg", "telegram", "电报", "纸飞机"}:
        return "Telegram"
    if raw in {"微信", "绿泡", "绿泡泡", "vx", "v"}:
        return "微信"
    return str(platform_value or "无").strip() or "无"


def platform_aliases(platform: str) -> list[str]:
    alias_map = {
        "douyin":   ["douyin", "dy"],
        "dy":       ["dy", "douyin"],
        "kuaishou": ["kuaishou", "ks"],
        "ks":       ["ks", "kuaishou"],
        "weibo":    ["weibo", "wb"],
        "wb":       ["wb", "weibo"],
    }
    return alias_map.get(platform, [platform])


def get_stage_files(stage: str, platform: str) -> list[str]:
    files: list[str] = []
    for p in platform_aliases(platform):
        if stage == "crawler":
            base_dir = os.path.join(CRAWLER_DIR, "data", p)
            if os.path.exists(base_dir):
                for root, _, names in os.walk(base_dir):
                    for n in names:
                        if n.endswith(".jsonl") or n.endswith(".csv"):
                            files.append(os.path.join(root, n))
        elif stage == "filter":
            fp = os.path.join(PROCESS_DIR, "data", p, "jsonl", "filtered_comments.jsonl")
            if os.path.exists(fp):
                files.append(fp)
        elif stage == "ai":
            fp = os.path.join(PROCESS_DIR, "data", p, "jsonl", "ai_extracted_channels.jsonl")
            if os.path.exists(fp):
                files.append(fp)
    return files


def has_raw_data(platform: str) -> bool:
    target_dir = os.path.join(CRAWLER_DIR, "data", platform)
    if not os.path.exists(target_dir):
        return False
    for _, _, files in os.walk(target_dir):
        if any(f.endswith(".jsonl") or f.endswith(".csv") for f in files):
            return True
    return False


def _jsonl_nonempty(path: str) -> bool:
    """空文件/仅换行视为「无数据」，避免误跳过后续阶段重跑。"""
    try:
        return os.path.exists(path) and os.path.getsize(path) > 0
    except OSError:
        return False


def has_filtered_data(platform: str) -> bool:
    return _jsonl_nonempty(
        os.path.join(PROCESS_DIR, "data", platform, "jsonl", "filtered_comments.jsonl")
    )


def has_ai_data(platform: str) -> bool:
    return _jsonl_nonempty(
        os.path.join(PROCESS_DIR, "data", platform, "jsonl", "ai_extracted_channels.jsonl")
    )


def cleanup_stage_local_files(stage: str, platform: str, log_fn: Callable) -> None:
    files = get_stage_files(stage, platform)
    removed = sum(1 for fp in files if _try_remove(fp))
    if removed:
        log_fn(f"🧹 [{stage.upper()}] 已清理本地文件 {removed} 个（只入库模式）。")


def _try_remove(path: str) -> bool:
    try:
        os.remove(path)
        return True
    except Exception:
        return False


def load_variant_lexicon_for_ui():
    """词库 JSON 缺失则用 `pipeline_defaults` 种子写盘再返回，避免 UI 读到空规则。"""
    if not os.path.exists(VARIANT_LEXICON_FILE):
        save_variant_lexicon_for_ui(
            DEFAULT_CHANNEL_WORDS, DEFAULT_DRUG_WORDS,
            DEFAULT_HOMOPHONE_MAP, DEFAULT_EMOJI_WORD_MAP, DEFAULT_CONTEXT_HINTS,
        )
        return (
            list(DEFAULT_CHANNEL_WORDS), list(DEFAULT_DRUG_WORDS),
            dict(DEFAULT_HOMOPHONE_MAP), dict(DEFAULT_EMOJI_WORD_MAP),
            list(DEFAULT_CONTEXT_HINTS),
        )
    try:
        with open(VARIANT_LEXICON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (
            data.get("strong_channel_words", []) or [],
            data.get("drug_slang_words", []) or [],
            data.get("homophone_variants", {}) or {},
            data.get("emoji_word_map", {}) or {},
            data.get("context_hints", []) or [],
        )
    except Exception:
        return (
            list(DEFAULT_CHANNEL_WORDS), list(DEFAULT_DRUG_WORDS),
            dict(DEFAULT_HOMOPHONE_MAP), dict(DEFAULT_EMOJI_WORD_MAP),
            list(DEFAULT_CONTEXT_HINTS),
        )


def save_variant_lexicon_for_ui(
    channel_words, drug_words, homophone_map, emoji_word_map, context_hints
) -> None:
    os.makedirs(os.path.dirname(VARIANT_LEXICON_FILE), exist_ok=True)
    payload = {
        "strong_channel_words": channel_words,
        "drug_slang_words": drug_words,
        "homophone_variants": homophone_map,
        "emoji_word_map": emoji_word_map,
        "context_hints": context_hints,
    }
    with open(VARIANT_LEXICON_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_ai_prompt_for_ui() -> str:
    try:
        return load_prompt_body(DEFAULT_AI_PROMPT_BODY)
    except Exception:
        return DEFAULT_AI_PROMPT_BODY


def check_db_source_health(
    platforms: list[str], filter_read_mode: str, ai_read_mode: str
) -> list[str]:
    """清洗/AI 若走「从数据库读」，预先粗查各集合文档计数；零命中返回告警文案列表。"""
    if filter_read_mode != "从数据库读" and ai_read_mode != "从数据库读":
        return []

    warnings: list[str] = []
    expected_platforms: set[str] = set()
    for p in platforms:
        expected_platforms.update(platform_aliases(p))

    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        db = client[MONGO_DB_NAME]

        if filter_read_mode == "从数据库读":
            cnt = db["raw_comments"].count_documents(
                {"stage": "crawler", "platform": {"$in": list(expected_platforms)}}
            )
            if cnt == 0:
                warnings.append('清洗阶段选择了"从数据库读"，但 raw_comments 中未检索到所选平台原始数据。')

        if ai_read_mode == "从数据库读":
            cnt = db["filtered_comments"].count_documents(
                {"stage": "filter", "platform": {"$in": list(expected_platforms)}}
            )
            if cnt == 0:
                warnings.append('AI阶段选择了"从数据库读"，但 filtered_comments 中未检索到所选平台清洗数据。')

        client.close()
    except Exception as exc:
        warnings.append(f"数据库读取策略检测失败：{exc}")

    return warnings


@dataclass
class PipelineConfig:
    platforms: list[str]

    start_date: str
    end_date: str
    crawl_type: str  # MediaCrawler：`search` | `detail`
    login_type: str  # `qrcode` | `cookie`
    search_keyword: str

    crawler_storage_mode: str
    filter_storage_mode: str
    ai_storage_mode: str
    filter_read_mode: str  # UI 字面量「从本地读」/「从数据库读」
    ai_read_mode: str

    ai_platform: str  # UI 选项串：云端 DeepSeek vs 本地 Ollama
    active_model_name: str
    ds_api_key: str
    max_process: int
    custom_ai_prompt: str

    custom_channels_list: list[str] = field(default_factory=list)
    custom_drugs_list: list[str]     = field(default_factory=list)
    custom_homophone_map: dict       = field(default_factory=dict)
    custom_emoji_map: dict           = field(default_factory=dict)
    custom_context_hints: list[str] = field(default_factory=list)

    overwrite_crawler_plats: list[str] = field(default_factory=list)
    overwrite_filter_plats: list[str]  = field(default_factory=list)
    overwrite_ai_plats: list[str]      = field(default_factory=list)
    # True：仅阶段四合并 + 启动服务，跳过采集 / 清洗 / AI（无需 API Key）
    dash_only: bool = False
    # True：执行 tests/generate_demo_verify_dataset.py --install-to-process-data，跳过采集/清洗，直接 AI→合并
    demo_verify_dataset: bool = False
    demo_verify_backup_filtered: bool = False

    dash_merge_mode: str = "同时入库和存入本地"
    dash_port: int = 5173

    clean_strictness: str = "标准"


class PipelineRunner:
    """串联四阶段；`_deferred_cleanup` 在全链路收尾后批量删本地中间文件，防阶段间断档。"""

    def __init__(
        self,
        config: PipelineConfig,
        log_fn: Callable[[str], None] = print,
        toast_fn: Callable[[str], None] | None = None,
        progress_fn: Callable[[int, str], None] | None = None,
        shell_fn: Callable[[str, str], int] | None = None,
        spawn_fn: Callable[[str, str], None] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ):
        self.config = config
        self.log = log_fn
        self.toast = toast_fn or (lambda msg, **_: None)
        self._set_progress = progress_fn or (lambda pct, text="": None)
        self._shell_fn = shell_fn or (lambda cmd, cwd: run_shell_command(cmd, cwd, self.log))
        self._spawn_fn = spawn_fn or _default_spawn
        self._sleep = sleep_fn or time.sleep
        # `(stage, platform)`：`只入库` 模式延后删盘，避免下游阶段仍读本地时被清空。
        self._deferred_cleanup: list[tuple[str, str]] = []

    def _progress(self, pct: int, text: str = "") -> None:
        self._set_progress(pct, text)

    def _sync(self, stage: str, platform: str) -> None:
        """阶段产物路径聚合 → `webui_core.sync_stage_files_to_mongo`，日志透传 `self.log`。"""
        files = get_stage_files(stage, platform)
        if not files or _sync_core is None:
            if _sync_core is None:
                self.log("⚠️ webui_core 未加载，跳过 MongoDB 同步。")
            return
        count, logs = _sync_core(stage, platform, list(files), MONGO_URI, MONGO_DB_NAME)
        for msg in logs:
            self.log(msg)

    def _shell(self, cmd: str, cwd: str) -> int:
        return self._shell_fn(cmd, cwd)

    def _spawn(self, cmd: str, cwd: str) -> None:
        self._spawn_fn(cmd, cwd)

    def run_crawl_stage(self) -> None:
        cfg = self.config
        self._progress(10, "[阶段一] 正在执行多平台并发采集...")
        self.log("============== [阶段一] 开始数据采集 ==============")

        for plat in cfg.platforms:
            if has_raw_data(plat) and plat not in cfg.overwrite_crawler_plats:
                self.log(f"⏭️ [跳过] {plat.upper()} 平台原始数据已存在。")
                continue
            self.log(f"📥 [采集] 正在执行 {plat.upper()} 爬虫任务...")
            cmd_plat = "dy" if plat == "douyin" else plat
            cmd = (
                f"python main.py --platform {cmd_plat}"
                f" --lt {cfg.login_type} --type {cfg.crawl_type}"
            )
            if cfg.crawl_type == "search" and cfg.search_keyword.strip():
                cmd += f' --keywords "{cfg.search_keyword.strip()}"'
            self._shell(cmd, CRAWLER_DIR)

        if cfg.crawler_storage_mode in ("只入库", "同时入库和存入本地"):
            for plat in cfg.platforms:
                self._sync("crawler", plat)
        if cfg.crawler_storage_mode == "只入库":
            for plat in cfg.platforms:
                self._deferred_cleanup.append(("crawler", plat))

        self.toast("✅ 第一阶段：数据采集完毕！")

    def run_filter_stage(self) -> None:
        cfg = self.config
        self._progress(40, "[阶段二] 正在执行字典匹配与噪音过滤...")
        self.log("\n============== [阶段二] 开始数据清洗 ==============")

        # 子进程读 `variant_lexicon.json`，须先于 `_shell` 落盘。
        save_variant_lexicon_for_ui(
            cfg.custom_channels_list, cfg.custom_drugs_list,
            cfg.custom_homophone_map, cfg.custom_emoji_map, cfg.custom_context_hints,
        )
        _filter_script = os.path.join(PROCESS_DIR, "data_filter.py")
        read_src = "db" if cfg.filter_read_mode == "从数据库读" else "local"

        for plat in cfg.platforms:
            if has_filtered_data(plat) and plat not in cfg.overwrite_filter_plats:
                self.log(f"⏭️ [跳过] {plat.upper()} 平台已清洗数据已存在。")
                continue
            self.log(f"🧹 [清洗] 正在执行 {plat.upper()} 数据过滤 (规则: {cfg.clean_strictness})...")
            cmd = (
                f'"{sys.executable}" -u "{_filter_script}"'
                f' --root-dir "{ROOT_DIR}"'
                f' --platforms {plat}'
                f' --start-date {cfg.start_date}'
                f' --end-date {cfg.end_date}'
                f' --strictness {cfg.clean_strictness}'
                f' --read-source {read_src}'
                f' --mongo-uri "{MONGO_URI}"'
                f' --mongo-db {MONGO_DB_NAME}'
            )
            self._shell(cmd, PROCESS_DIR)

        if cfg.filter_storage_mode in ("只入库", "同时入库和存入本地"):
            for plat in cfg.platforms:
                self._sync("filter", plat)
        if cfg.filter_storage_mode == "只入库":
            for plat in cfg.platforms:
                self._deferred_cleanup.append(("filter", plat))

        self.toast("✅ 第二阶段：噪音清洗完毕！")

    def run_ai_stage(self) -> None:
        cfg = self.config
        self._progress(70, "[阶段三] 大模型深度特征提取中...")
        self.log("\n============== [阶段三] 开始 AI 深度分析 ==============")

        read_src = "db" if cfg.ai_read_mode == "从数据库读" else "local"

        need_ai_plats = [
            p for p in cfg.platforms
            if not (has_ai_data(p) and p not in cfg.overwrite_ai_plats)
        ]
        if (
            cfg.ai_platform == "DeepSeek (云端 API)"
            and need_ai_plats
            and not cfg.ds_api_key.strip()
        ):
            names = ", ".join(p.upper() for p in need_ai_plats)
            self.log(
                "❌ 致命错误：未填写 DeepSeek API Key！以下平台仍缺少本地 AI 结果或处于覆盖重跑："
                f"{names}。任务中止。"
            )
            raise ValueError("Missing API Key")

        for plat in cfg.platforms:
            if has_ai_data(plat) and plat not in cfg.overwrite_ai_plats:
                self.log(f"⏭️ [跳过] {plat.upper()} 平台 AI 提取结果已存在。")
                continue

            if cfg.custom_ai_prompt.strip():
                save_prompt_template(cfg.custom_ai_prompt)

            if cfg.ai_platform == "DeepSeek (云端 API)":
                self.log(f"🧠 [AI分析] 正在调用 DeepSeek ({cfg.active_model_name}) 提取 {plat.upper()} 交易线索...")
                script = os.path.join(PROCESS_DIR, "deepseek_processor.py")
                cmd = (
                    f'"{sys.executable}" -u "{script}"'
                    f' --root-dir "{ROOT_DIR}"'
                    f' --platforms {plat}'
                    f' --model "{cfg.active_model_name}"'
                    f' --max-count {cfg.max_process}'
                    f' --api-key "{cfg.ds_api_key.strip()}"'
                    f' --read-source {read_src}'
                    f' --mongo-uri "{MONGO_URI}"'
                    f' --mongo-db {MONGO_DB_NAME}'
                )
            else:
                if not cfg.active_model_name.strip():
                    self.log("❌ 致命错误：未填写 Ollama 模型名称！任务中止。")
                    raise ValueError("Missing Ollama Model Name")
                self.log(f"🧠 [AI分析] 正在调用本地模型 ({cfg.active_model_name}) 提取 {plat.upper()} 交易线索...")
                script = os.path.join(PROCESS_DIR, "ollama_processor.py")
                cmd = (
                    f'"{sys.executable}" -u "{script}"'
                    f' --root-dir "{ROOT_DIR}"'
                    f' --platforms {plat}'
                    f' --model "{cfg.active_model_name}"'
                    f' --max-count {cfg.max_process}'
                    f' --read-source {read_src}'
                    f' --mongo-uri "{MONGO_URI}"'
                    f' --mongo-db {MONGO_DB_NAME}'
                )
            self._shell(cmd, PROCESS_DIR)

        if cfg.ai_storage_mode in ("只入库", "同时入库和存入本地"):
            for plat in cfg.platforms:
                self._sync("ai", plat)
        if cfg.ai_storage_mode == "只入库":
            for plat in cfg.platforms:
                self._deferred_cleanup.append(("ai", plat))

        self.toast("✅ 第三阶段：大模型侦听完毕！")

    def _prepare_demo_verify_dataset(self) -> None:
        """调用仓库内生成器，将 _demo_verify 样本安装到 ProcessCdata/data/<plat>/jsonl/。"""
        cfg = self.config
        script = os.path.join(ROOT_DIR, "tests", "generate_demo_verify_dataset.py")
        if not os.path.isfile(script):
            raise FileNotFoundError(f"未找到验证集脚本: {script}")
        parts = [f'"{sys.executable}"', "-u", f'"{script}"', "--install-to-process-data"]
        if cfg.demo_verify_backup_filtered:
            parts.append("--backup-existing-filtered")
        cmd = " ".join(parts)
        self.log("\n============== [验证集] 生成并安装小规模 filtered_comments.jsonl ==============")
        rc = self._shell_fn(cmd, ROOT_DIR)
        if rc != 0:
            raise RuntimeError(f"验证集脚本退出码 {rc}，请查看上方日志")

    def _ensure_demo_verify_ai_overwrite(self) -> None:
        """验证集：仅对缺少本地 AI 产物的平台执行阶段三；已有结果则跳过（省 token）。

        若需对某平台强制重跑，请在 WebUI「覆盖 AI 分析」中勾选该平台，或勾选「一键强制全量覆盖」。
        """
        cfg = self.config
        extra = [p for p in cfg.platforms if p in DEMO_VERIFY_PLATFORMS]
        if not extra:
            self.log(
                "⚠️ [验证集] 所选平台无可内置样本（需 bili / xhs / zhihu / dy / douyin / tieba）；"
                "AI 阶段仍按常规则执行。"
            )
            return

        will_run = [
            p for p in extra
            if p in cfg.overwrite_ai_plats or not has_ai_data(p)
        ]
        will_skip = [p for p in extra if p not in will_run]

        if will_skip:
            self.log(
                "🧪 [验证集] 以下平台已有 ai_extracted_channels.jsonl，跳过 AI（不消耗 API token）："
                + ", ".join(p.upper() for p in will_skip)
                + "。如需重跑请在「覆盖 AI 分析」中勾选对应平台。"
            )
        if will_run:
            self.log(
                "🧪 [验证集] 以下平台将执行 AI："
                + ", ".join(p.upper() for p in will_run)
            )

    def _merge_platform_ai_jsonl(
        self,
        write_path: str | None,
        *,
        collect_mongo: bool,
    ) -> list[dict]:
        """多平台 AI 指纹去重；可按需写 `extracted_channels.jsonl` / 组装 Mongo upsert 行。"""
        mongo_records: list[dict] = []
        merged_count = 0
        seen: set[str] = set()

        if write_path and collect_mongo:
            label = "打包至前端并写入线索库"
        elif write_path:
            label = "打包至前端（仅本地 JSONL）"
        elif collect_mongo:
            label = "写入线索库（不写本地大屏文件）"
        else:
            label = "聚合"
        self.log(f"🔄 [聚合] 正在执行无损跨平台去重，{label}...")

        outfile = open(write_path, "w", encoding="utf-8") if write_path else None
        try:
            for plat in self.config.platforms:
                src = os.path.join(PROCESS_DIR, "data", plat, "jsonl", "ai_extracted_channels.jsonl")
                if not os.path.exists(src):
                    continue
                with open(src, "r", encoding="utf-8") as infile:
                    for line in infile:
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        fp = f"{plat}_{data.get('source_url','')}_{data.get('original_content','')}"
                        if fp in seen:
                            continue
                        oc = str(data.get("original_content") or "")
                        tpc = str(data.get("thread_parent_content") or "")
                        if is_obvious_noise_lead(oc, tpc):
                            logger.debug(
                                "merge skip noise line platform=%s orig=%s…",
                                plat,
                                oc[:24],
                            )
                            continue
                        seen.add(fp)
                        data["source_platform"] = plat.upper()
                        data["platform"] = normalize_platform_name(data.get("platform", "无"))
                        if outfile is not None:
                            outfile.write(json.dumps(data, ensure_ascii=False) + "\n")
                        if collect_mongo and to_contract_doc:
                            mongo_records.append(to_contract_doc({
                                "source_platform": plat.upper(),
                                "video_title":     data.get("video_title", ""),
                                "source_url":      data.get("source_url", ""),
                                "original_content": data.get("original_content", ""),
                                "thread_parent_content": data.get("thread_parent_content", ""),
                                "platform":        normalize_platform_name(data.get("platform", "无")),
                                "merchant":        data.get("merchant", "未指明"),
                                "AI_analysis":     data.get("AI_analysis", "暂无研判"),
                                "ingested_at":     int(time.time()),
                            }))
                        merged_count += 1
        finally:
            if outfile is not None:
                outfile.close()

        self.log(f"✅ 精准提纯流转完毕：成功整合 {merged_count} 条跨平台独立线索。")
        return mongo_records

    def _persist_leads_to_mongo(self, mongo_records: list[dict]) -> None:
        """按 `source_platform` 整批删旧再 bulk upsert：`fingerprint` 幂等合并增量。"""
        self.log("🗄️ [持久化] 正在写入 MongoDB (Oestrogen)...")
        logger.info("Persisting %d AI leads to MongoDB collection=%s", len(mongo_records), MONGO_COLLECTION)
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        col = client[MONGO_DB_NAME][MONGO_COLLECTION]
        col.create_index("fingerprint", unique=True)
        col.create_index("ingested_at")
        col.create_index("platform")
        col.create_index("merchant")

        for plat in self.config.platforms:
            stale = col.delete_many({"source_platform": plat.upper()}).deleted_count
            if stale:
                logger.info("Cleared %d stale sentinel_leads for source_platform=%s", stale, plat.upper())
                self.log(f"🧹 已清除 {stale} 条平台 [{plat.upper()}] 的旧线索记录，开始写入新数据。")

        ops = [
            UpdateOne({"fingerprint": doc["fingerprint"]}, {"$set": doc}, upsert=True)
            for doc in mongo_records
        ]
        if ops:
            col.bulk_write(ops, ordered=False)
        client.close()
        self.log(f"✅ MongoDB 持久化完成：upsert {len(mongo_records)} 条。")

    def run_merge_stage(self) -> None:
        cfg = self.config
        if cfg.dash_merge_mode == DASH_MERGE_SKIP:
            return

        mongo_wanted = cfg.dash_merge_mode in ("同时入库和存入本地", "只入库")
        local_wanted = cfg.dash_merge_mode in ("同时入库和存入本地", "只存入本地")

        self._progress(90, "[阶段四] 跨平台去重与前端推流中...")
        self.log("\n============== [阶段四] 可视化数据流转 ==============")

        public_dir = os.path.join(DASHBOARD_DIR, "public")
        os.makedirs(public_dir, exist_ok=True)
        merged_file = os.path.join(public_dir, "extracted_channels.jsonl")

        write_path = merged_file if local_wanted else None
        mongo_records = self._merge_platform_ai_jsonl(
            write_path,
            collect_mongo=mongo_wanted,
        )
        if mongo_wanted and mongo_records:
            self._persist_leads_to_mongo(mongo_records)

    def run_full_pipeline(self) -> None:
        """跑满四阶段 → 延后清理本地中间件 → 拉起 FastAPI + Vite。"""
        self._deferred_cleanup = []

        if self.config.dash_only:
            self.log(
                "⚡ [捷径模式] 已跳过采集 / 清洗 / AI；仅执行大屏合并（若未选跳过）并启动服务。"
            )
            self._progress(85, "[阶段四] 大屏合并（捷径模式）...")
            self.run_merge_stage()
            self._progress(100, "系统部署完成！大屏就绪。")
        elif self.config.demo_verify_dataset:
            self.log(
                "🧪 [验证集模式] 跳过采集与清洗；写入内置样本后执行 AI 与大屏合并。"
            )
            self._progress(12, "[验证集] 生成并安装测试样本...")
            self._prepare_demo_verify_dataset()
            self._ensure_demo_verify_ai_overwrite()
            self._progress(55, "[阶段三] 大模型深度特征提取中...")
            self.run_ai_stage()
            self.run_merge_stage()
            self._progress(100, "系统部署完成！大屏就绪。")
        else:
            self.run_crawl_stage()
            self.run_filter_stage()
            self.run_ai_stage()
            self.run_merge_stage()

            self._progress(100, "系统部署完成！大屏就绪。")

        for stage_name, plat_name in self._deferred_cleanup:
            cleanup_stage_local_files(stage_name, plat_name, self.log)

        ensure_sentinel_api_running(
            self.log, api_port=8000,
            spawn_fn=self._spawn_fn,
            sleep_fn=self._sleep,
        )

        cfg = self.config
        self.log(f"🌐 正在后台挂载 Node.js 前端服务 (端口: {cfg.dash_port})...")
        logger.info("Spawning frontend dev server on port %d (cwd=%s)", cfg.dash_port, DASHBOARD_DIR)
        self._spawn(f"npm run dev -- --port {cfg.dash_port}", DASHBOARD_DIR)
        self._sleep(2)
