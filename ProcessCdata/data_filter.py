"""规则清洗：原始评论 → 命中渠道/药物词 → `filtered_comments.jsonl`。

支持本地 JSONL 按日期切片与 Mongo `raw_comments` 回放；严格度三元组控制放行门槛。"""

import json
import logging
import os
import datetime
import re
import unicodedata
import matplotlib.pyplot as plt
from collections import Counter
from dataclasses import dataclass, field
from pymongo import MongoClient

logger = logging.getLogger(__name__)

# Matplotlib 中文字形；缺字体会回退后续字体列表。
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

# 以下模块级容器：测试 patch 入口；CLI 路径由 `FilterConfig` 显式传入覆盖。
PLATFORMS = ["xhs", "douyin", "kuaishou", "bili", "weibo", "zhihu", "tieba"]

START_DATE = "2020-04-12"
END_DATE = "2026-04-12"
CLEAN_STRICTNESS = "标准"

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
BASE_INPUT_DIR = os.path.join(ROOT_DIR, "MediaCrawler", "data")
BASE_OUTPUT_DIR = os.path.join(CURRENT_DIR, "data")
VARIANT_LEXICON_FILE = os.path.join(CURRENT_DIR, "config", "variant_lexicon.json")
READ_SOURCE = "local"
MONGO_URI = "mongodb://127.0.0.1:27017"
MONGO_DB_NAME = "Oestrogen"

# 以下列表、字典：`normalize_for_detection` / `detect_keywords` 在未注入参数时的兜底。
STRONG_CHANNEL_WORDS: list = []
DRUG_SLANG_WORDS: list = []
EMOJI_WORD_MAP: dict = {}
HOMOPHONE_VARIANTS: dict = {}
TRADE_CONTEXT_HINTS: list = []

OBFUSCATION_REGEX_RULES = [
    (re.compile(r"t[\W_]*a[\W_]*n[\W_]*g", re.IGNORECASE), "糖"),
    (re.compile(r"v[\W_]*x", re.IGNORECASE), "vx"),
    (re.compile(r"t[\W_]*g", re.IGNORECASE), "tg"),
    (re.compile(r"q[\W_]*q", re.IGNORECASE), "qq"),
]


@dataclass
class FilterConfig:
    start_date: str
    end_date: str
    base_input_dir: str
    base_output_dir: str
    strictness: str = "标准"
    read_source: str = "local"
    mongo_uri: str = "mongodb://127.0.0.1:27017"
    mongo_db_name: str = "Oestrogen"
    strong_channel_words: list = field(default_factory=list)
    drug_slang_words: list = field(default_factory=list)
    emoji_word_map: dict = field(default_factory=dict)
    homophone_variants: dict = field(default_factory=dict)
    trade_context_hints: list = field(default_factory=list)



def load_variant_lexicon():
    """读 `variant_lexicon.json`；坏文件返回五元空结构，调用方自行兜底。"""
    if not os.path.exists(VARIANT_LEXICON_FILE):
        return [], [], {}, {}, []
    try:
        with open(VARIANT_LEXICON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        channel_words = data.get("strong_channel_words", [])
        drug_words = data.get("drug_slang_words", [])
        emoji_map = data.get("emoji_word_map", {})
        homophones = data.get("homophone_variants", {})
        context_hints = data.get("context_hints", [])
        if not isinstance(channel_words, list):
            channel_words = []
        if not isinstance(drug_words, list):
            drug_words = []
        if not isinstance(emoji_map, dict):
            emoji_map = {}
        if not isinstance(homophones, dict):
            homophones = {}
        if not isinstance(context_hints, list):
            context_hints = []
        return channel_words, drug_words, homophones, emoji_map, context_hints
    except Exception:
        return [], [], {}, {}, []


def normalize_for_detection(text, emoji_map=None, obfuscation_rules=None):
    """NFKC → emoji 替换 → 对抗正则展开 → 非中英数字剔除，拉高召回稳定性。"""
    if not text:
        return ""
    _emoji_map = emoji_map if emoji_map is not None else EMOJI_WORD_MAP
    _rules = obfuscation_rules if obfuscation_rules is not None else OBFUSCATION_REGEX_RULES

    normalized = unicodedata.normalize("NFKC", str(text)).lower()
    for emoji, token in _emoji_map.items():
        normalized = normalized.replace(emoji, token)
    for pattern, replacement in _rules:
        normalized = pattern.sub(replacement, normalized)
    normalized = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", normalized)
    return normalized


def build_normalized_keywords(words, emoji_map=None, obfuscation_rules=None):
    """词表逐项标准化，产出 (原文, 标准化形) 供子串包含匹配。"""
    pairs = []
    for w in words:
        nw = normalize_for_detection(w, emoji_map=emoji_map, obfuscation_rules=obfuscation_rules)
        if nw:
            pairs.append((w, nw))
    return pairs


def detect_keywords(content, normalized_channel_words, normalized_drug_words,
                    homophone_variants=None, context_hints=None):
    """渠道 / 药物直连命中；语境提示命中后才解禁谐音映射，降低误触。"""
    _hv = homophone_variants if homophone_variants is not None else HOMOPHONE_VARIANTS
    _hints = context_hints if context_hints is not None else TRADE_CONTEXT_HINTS

    cleaned = normalize_for_detection(content)
    matched_channels = [origin for origin, nw in normalized_channel_words if nw in cleaned]
    matched_drugs = [origin for origin, nw in normalized_drug_words if nw in cleaned]

    context_hit = any(normalize_for_detection(hint) in cleaned for hint in _hints)
    if context_hit:
        for variant, canonical in _hv.items():
            v = normalize_for_detection(variant)
            if v and v in cleaned:
                if canonical in [w for w, _ in normalized_drug_words]:
                    if canonical not in matched_drugs:
                        matched_drugs.append(canonical)
                if canonical in [w for w, _ in normalized_channel_words]:
                    if canonical not in matched_channels:
                        matched_channels.append(canonical)

    return matched_channels, matched_drugs


def generate_charts(channel_counter, drug_counter, chart_output_file, platform_name):
    logger.info("[%s] 正在生成数据分析图表...", platform_name.upper())
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

    top_channels = channel_counter.most_common(10)
    if top_channels:
        labels, values = zip(*top_channels)
        bars = ax1.bar(labels, values, color='#4C72B0')
        ax1.set_title(f'[{platform_name.upper()}] 提及最多的渠道 TOP 10', fontsize=14, fontweight='bold')
        ax1.set_ylabel('提及次数')
        ax1.tick_params(axis='x', rotation=45)
        for bar in bars:
            yval = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width() / 2.0, yval, int(yval), va='bottom', ha='center')
    else:
        ax1.text(0.5, 0.5, "未匹配到渠道词", ha='center')

    top_drugs = drug_counter.most_common(10)
    if top_drugs:
        labels_d, values_d = zip(*top_drugs)
        bars_d = ax2.bar(labels_d, values_d, color='#55A868')
        ax2.set_title(f'[{platform_name.upper()}] 讨论最多的药物/黑话 TOP 10', fontsize=14, fontweight='bold')
        ax2.set_ylabel('提及次数')
        ax2.tick_params(axis='x', rotation=45)
        for bar in bars_d:
            yval = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width() / 2.0, yval, int(yval), va='bottom', ha='center')
    else:
        ax2.text(0.5, 0.5, "未匹配到药物词", ha='center')

    plt.tight_layout()
    plt.savefig(chart_output_file, dpi=300)
    plt.close()
    logger.info("图表已保存: %s", chart_output_file)


def platform_aliases(platform):
    alias_map = {
        "douyin": ["douyin", "dy"],
        "kuaishou": ["kuaishou", "ks"],
        "weibo": ["weibo", "wb"],
    }
    return alias_map.get(platform, [platform])


def _merge_one_contents_obj_into_map(c_data: dict, title_map: dict) -> None:
    """单条 search_contents 行解析，与本地按日分支逻辑一致。"""
    item_id = (c_data.get("note_id") or c_data.get("aweme_id")
               or c_data.get("bvid") or c_data.get("video_id")
               or c_data.get("photo_id") or c_data.get("mid")
               or c_data.get("content_id") or c_data.get("id"))
    item_title = (c_data.get("title") or c_data.get("note_title")
                  or c_data.get("desc") or "")
    if item_id:
        title_map[str(item_id)] = item_title
    numeric_id = c_data.get("id") or c_data.get("aid")
    if numeric_id and str(numeric_id) != str(item_id):
        title_map[str(numeric_id)] = item_title
    bvid_val = c_data.get("bvid")
    vid_val = c_data.get("video_id")
    if bvid_val and vid_val and str(bvid_val) != str(vid_val):
        title_map[str(bvid_val)] = item_title
        title_map[str(vid_val)] = item_title


def build_global_contents_title_map(platform_input_dir: str) -> dict[str, str]:
    """扫描 `search_contents_*.jsonl`，合并 id→标题。供「从数据库读」回放时补齐 injected_video_title。

    不限制日期：评论在 Mongo 里可能跨日，需与历史上全部内容索引对齐。
    """
    title_map: dict[str, str] = {}
    if not os.path.isdir(platform_input_dir):
        return title_map
    for fn in sorted(os.listdir(platform_input_dir)):
        if not (fn.startswith("search_contents_") and fn.endswith(".jsonl")):
            continue
        path = os.path.join(platform_input_dir, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        _merge_one_contents_obj_into_map(json.loads(line), title_map)
                    except json.JSONDecodeError:
                        pass
        except OSError as exc:
            logger.warning("读取内容索引失败 %s: %s", path, exc)
    return title_map


def inject_comment_title_from_map(data: dict, title_map: dict) -> None:
    """用评论主键 / B 站 oid 查映射，写入 injected_video_title（与本地分支一致）。"""
    c_item_id = (data.get("note_id") or data.get("aweme_id")
                 or data.get("bvid") or data.get("video_id")
                 or data.get("photo_id") or data.get("mid")
                 or data.get("content_id") or data.get("id"))
    _title = title_map.get(str(c_item_id), "") if c_item_id else ""
    if not _title:
        _oid = data.get("oid")
        if _oid:
            _title = title_map.get(str(_oid), "")
    if _title:
        data["injected_video_title"] = _title


# MongoClient 按 URI 进程级单例。

_mongo_pool: dict[str, MongoClient] = {}


def _get_mongo_client(uri: str) -> MongoClient:
    """同一 URI 只构造一次 Client。"""
    if uri not in _mongo_pool:
        _mongo_pool[uri] = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return _mongo_pool[uri]


def load_comments_from_db(platform, mongo_uri, mongo_db_name):
    client = _get_mongo_client(mongo_uri)
    col = client[mongo_db_name]["raw_comments"]
    docs = list(col.find(
        {"stage": "crawler", "platform": {"$in": platform_aliases(platform)}},
        {"payload": 1},
    ))
    return [d["payload"] for d in docs if isinstance(d.get("payload"), dict)]


def _apply_strictness(strictness, matched_channels, matched_drugs):
    if strictness == "宽松":
        return True
    if strictness == "严苛":
        return bool(matched_channels and matched_drugs)
    return bool(matched_drugs or matched_channels)


def run_filter_for_platform(platform, cfg: FilterConfig):
    """单平台入口：cfg 包住路径 / 词库 / 读写源；不写全局可变状态。"""
    platform_input_dir = os.path.join(cfg.base_input_dir, platform, "jsonl")
    output_file = os.path.join(cfg.base_output_dir, platform, "jsonl", "filtered_comments.jsonl")
    chart_output_file = os.path.join(cfg.base_output_dir, platform, "jsonl", "analysis_report.png")
    log_file = os.path.join(cfg.base_output_dir, platform, "jsonl", "filter_log.txt")

    logger.info(
        "[%s] 开始过滤 | 范围: %s ~ %s | 策略: %s",
        platform.upper(), cfg.start_date, cfg.end_date, cfg.strictness,
    )
    print(f"🔍 [{platform.upper()}] 开始清洗 | 日期: {cfg.start_date} ~ {cfg.end_date} | 严格度: {cfg.strictness}", flush=True)

    limit_ts = int(datetime.datetime.strptime(cfg.start_date, "%Y-%m-%d").timestamp())
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    norm_channels = build_normalized_keywords(cfg.strong_channel_words, emoji_map=cfg.emoji_word_map)
    norm_drugs = build_normalized_keywords(cfg.drug_slang_words, emoji_map=cfg.emoji_word_map)

    # Mongo：一次性拉齐 payload，时间戳门槛在内存过滤。
    if cfg.read_source == "db":
        comments = load_comments_from_db(platform, cfg.mongo_uri, cfg.mongo_db_name)
        with open(log_file, 'a', encoding='utf-8') as f_log:
            f_log.write(f"\n{'='*50}\n"
                        f"执行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"处理平台: [{platform.upper()}] | 数据源: MongoDB\n"
                        f"{'-'*50}\n")

            if not comments:
                msg = f"MongoDB 未检索到 [{platform.upper()}] 原始评论"
                logger.warning(msg)
                f_log.write(msg + "\n")
                open(output_file, 'w', encoding='utf-8').close()
                return

            contents_title_map = build_global_contents_title_map(platform_input_dir)
            logger.info(
                "[%s] Mongo 回放：search_contents 标题映射键 %d 个（目录 %s）",
                platform.upper(),
                len(contents_title_map),
                platform_input_dir,
            )

            total_lines = len(comments)
            kept = 0
            skipped_time = 0
            channel_counter = Counter()
            drug_counter = Counter()

            with open(output_file, 'w', encoding='utf-8') as f_out:
                for data in comments:
                    ct = data.get("create_time") or data.get("publish_time") or 0
                    if ct and ct > 9999999999:
                        ct = ct / 1000
                    if ct and ct < limit_ts:
                        skipped_time += 1
                        continue
                    content = data.get("content", "")
                    if not content:
                        continue
                    if not data.get("injected_video_title"):
                        data["injected_video_title"] = data.get("video_title", "")
                    if not str(data.get("injected_video_title") or "").strip():
                        inject_comment_title_from_map(data, contents_title_map)

                    matched_ch, matched_dr = detect_keywords(
                        content, norm_channels, norm_drugs,
                        homophone_variants=cfg.homophone_variants,
                        context_hints=cfg.trade_context_hints,
                    )
                    if _apply_strictness(cfg.strictness, matched_ch, matched_dr):
                        f_out.write(json.dumps(data, ensure_ascii=False) + "\n")
                        kept += 1
                        for w in matched_ch:
                            channel_counter[w] += 1
                        for w in matched_dr:
                            drug_counter[w] += 1

            reduction = (1 - kept / total_lines) * 100 if total_lines > 0 else 0
            summary = (
                f"\n{'-'*15} 最终汇总报告 {'-'*15}\n"
                f"清洗严格度: 【{cfg.strictness}】\n"
                f"总计读取评论: {total_lines} 条\n"
                f"历史剔除总计: {skipped_time} 条 (早于 {cfg.start_date})\n"
                f"无特征剔除: {total_lines - kept - skipped_time} 条\n"
                f"最终筛选保留: {kept} 条\n"
                f"数据极致压缩率: {reduction:.2f}%\n"
                f"{'='*50}\n\n"
            )
            logger.info(summary.strip())
            f_log.write(summary)
            if kept > 0:
                generate_charts(channel_counter, drug_counter, chart_output_file, platform)
        return

    # 本地：按文件名日期窗口串联 `search_comments_*.jsonl`，并用当日 `search_contents_*` 回填标题。
    valid_dates = []
    if os.path.exists(platform_input_dir):
        for filename in os.listdir(platform_input_dir):
            if filename.startswith("search_comments_") and filename.endswith(".jsonl"):
                date_str = filename.replace("search_comments_", "").replace(".jsonl", "")
                if cfg.start_date <= date_str <= cfg.end_date:
                    valid_dates.append(date_str)
    valid_dates.sort()

    with open(log_file, 'a', encoding='utf-8') as f_log:
        f_log.write(f"\n{'='*50}\n"
                    f"执行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"处理平台: [{platform.upper()}] | 严格度: {cfg.strictness}\n"
                    f"目标区间: {cfg.start_date} 到 {cfg.end_date}\n"
                    f"{'-'*50}\n")

        if not valid_dates:
            msg = f"[{platform.upper()}] 日期区间内未找到爬虫文件"
            logger.warning(msg)
            f_log.write(msg + "\n")
            open(output_file, 'w', encoding='utf-8').close()
            return

        total_lines = 0
        for date_str in valid_dates:
            cf = os.path.join(platform_input_dir, f"search_comments_{date_str}.jsonl")
            if os.path.exists(cf):
                with open(cf, 'r', encoding='utf-8') as f:
                    total_lines += sum(1 for _ in f)

        if total_lines == 0:
            msg = f"[{platform.upper()}] 匹配到的文件全为空"
            logger.warning(msg)
            f_log.write(msg + "\n")
            open(output_file, 'w', encoding='utf-8').close()
            return

        logger.info("[%s] 匹配到 %d 天数据文件，总计 %d 条，开始特征提取",
                    platform.upper(), len(valid_dates), total_lines)
        print(f"📂 [{platform.upper()}] 找到 {len(valid_dates)} 个日期文件，共 {total_lines} 条原始评论，开始过滤...", flush=True)

        kept = 0
        skipped_time = 0
        channel_counter = Counter()
        drug_counter = Counter()

        try:
            with open(output_file, 'w', encoding='utf-8') as f_out:
                for date_str in valid_dates:
                    contents_file = os.path.join(platform_input_dir, f"search_contents_{date_str}.jsonl")
                    comments_file = os.path.join(platform_input_dir, f"search_comments_{date_str}.jsonl")

                    daily_title_map = {}
                    if os.path.exists(contents_file):
                        with open(contents_file, 'r', encoding='utf-8') as f_cont:
                            for line in f_cont:
                                try:
                                    raw = line.strip()
                                    if not raw:
                                        continue
                                    _merge_one_contents_obj_into_map(json.loads(raw), daily_title_map)
                                except json.JSONDecodeError:
                                    pass

                    daily_read = 0
                    daily_kept = 0
                    if os.path.exists(comments_file):
                        with open(comments_file, 'r', encoding='utf-8') as f_in:
                            for line in f_in:
                                daily_read += 1
                                if daily_read % 500 == 0:
                                    logger.debug("[%s] %s 已扫描 %d 条，暂获 %d 条",
                                                 platform.upper(), date_str, daily_read, daily_kept)
                                try:
                                    data = json.loads(line.strip())
                                    ct = data.get("create_time") or data.get("publish_time") or 0
                                    if ct > 9999999999:
                                        ct = ct / 1000
                                    if ct < limit_ts:
                                        skipped_time += 1
                                        continue

                                    content = data.get("content", "")
                                    if not content:
                                        continue

                                    c_item_id = (data.get("note_id") or data.get("aweme_id")
                                                 or data.get("bvid") or data.get("video_id")
                                                 or data.get("photo_id") or data.get("mid")
                                                 or data.get("content_id") or data.get("id"))
                                    _title = daily_title_map.get(str(c_item_id), "") if c_item_id else ""
                                    # 哔哩哔哩评论：oid 常为 avid；主键查不到标题时再走 oid。
                                    if not _title:
                                        _oid = data.get("oid")
                                        if _oid:
                                            _title = daily_title_map.get(str(_oid), "")
                                    data["injected_video_title"] = _title

                                    matched_ch, matched_dr = detect_keywords(
                                        content, norm_channels, norm_drugs,
                                        homophone_variants=cfg.homophone_variants,
                                        context_hints=cfg.trade_context_hints,
                                    )
                                    if _apply_strictness(cfg.strictness, matched_ch, matched_dr):
                                        f_out.write(json.dumps(data, ensure_ascii=False) + "\n")
                                        daily_kept += 1
                                        kept += 1
                                        for w in matched_ch:
                                            channel_counter[w] += 1
                                        for w in matched_dr:
                                            drug_counter[w] += 1
                                except json.JSONDecodeError:
                                    pass

                    if daily_read > 0:
                        log_line = f"日期: {date_str} | 读取: {daily_read} -> 保留: {daily_kept}\n"
                        logger.info(log_line.strip())
                        f_log.write(log_line)
                        print(f"  📅 {date_str}：读取 {daily_read} 条 → 保留 {daily_kept} 条", flush=True)

            reduction = (1 - kept / total_lines) * 100 if total_lines > 0 else 0
            summary = (
                f"\n{'-'*15} 最终汇总报告 {'-'*15}\n"
                f"清洗严格度: 【{cfg.strictness}】\n"
                f"总计读取评论: {total_lines} 条\n"
                f"历史剔除总计: {skipped_time} 条 (早于 {cfg.start_date})\n"
                f"无特征剔除: {total_lines - kept - skipped_time} 条\n"
                f"最终筛选保留: {kept} 条\n"
                f"数据极致压缩率: {reduction:.2f}%\n"
                f"{'='*50}\n\n"
            )
            logger.info(summary.strip())
            f_log.write(summary)
            print(
                f"✅ [{platform.upper()}] 清洗完成：{total_lines} 条 → 保留 {kept} 条"
                f"（压缩率 {(1 - kept / total_lines) * 100:.1f}%）",
                flush=True,
            )
            if kept > 0:
                generate_charts(channel_counter, drug_counter, chart_output_file, platform)
            else:
                logger.warning("[%s] 无符合条件的有效数据，未生成图表", platform.upper())
                print(f"⚠️  [{platform.upper()}] 无符合条件的数据，跳过图表生成", flush=True)

        except Exception as e:
            msg = f"[{platform.upper()}] 处理时发生严重错误: {e}"
            logger.error(msg, exc_info=True)
            f_log.write(msg + "\n")


def run_filter_pipeline(start_date, end_date, platforms, base_dir,
                        strictness="标准",
                        custom_channels=None, custom_drugs=None,
                        read_source="local",
                        mongo_uri=None, mongo_db=None,
                        custom_homophone_map=None,
                        custom_context_hints=None,
                        custom_emoji_map=None):
    # 词库文件热读：避免 WebUI 保存后仍跑内存陈旧快照。
    lex_channels, lex_drugs, lex_homophones, lex_emoji, lex_hints = load_variant_lexicon()

    cfg = FilterConfig(
        start_date=start_date,
        end_date=end_date,
        base_input_dir=os.path.join(base_dir, "MediaCrawler", "data"),
        base_output_dir=os.path.join(base_dir, "ProcessCdata", "data"),
        strictness=strictness,
        read_source=read_source,
        mongo_uri=mongo_uri or MONGO_URI,
        mongo_db_name=mongo_db or MONGO_DB_NAME,
        strong_channel_words=custom_channels if custom_channels else list(lex_channels),
        drug_slang_words=custom_drugs if custom_drugs else list(lex_drugs),
        emoji_word_map=custom_emoji_map if isinstance(custom_emoji_map, dict) else dict(lex_emoji),
        homophone_variants=custom_homophone_map if isinstance(custom_homophone_map, dict) else dict(lex_homophones),
        trade_context_hints=custom_context_hints if isinstance(custom_context_hints, list) else list(lex_hints),
    )

    for plat in platforms:
        run_filter_for_platform(plat, cfg)

    return "✅ 初筛清洗任务完成！"


if __name__ == "__main__":
    import argparse as _ap

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _p = _ap.ArgumentParser(description="数据清洗流水线（供 WebUI 以子进程方式调用）")
    _p.add_argument("--root-dir",    default=ROOT_DIR,        help="项目根目录")
    _p.add_argument("--platforms",   nargs="+", default=PLATFORMS, help="要处理的平台列表")
    _p.add_argument("--start-date",  default=START_DATE)
    _p.add_argument("--end-date",    default=END_DATE)
    _p.add_argument("--strictness",  default=CLEAN_STRICTNESS, choices=["宽松", "标准", "严苛"])
    _p.add_argument("--read-source", default=READ_SOURCE,      choices=["local", "db"])
    _p.add_argument("--mongo-uri",   default=MONGO_URI)
    _p.add_argument("--mongo-db",    default=MONGO_DB_NAME)
    _args = _p.parse_args()

    _channels, _drugs, _homophones, _emoji, _hints = load_variant_lexicon()
    _cfg = FilterConfig(
        start_date=_args.start_date,
        end_date=_args.end_date,
        base_input_dir=os.path.join(_args.root_dir, "MediaCrawler", "data"),
        base_output_dir=os.path.join(_args.root_dir, "ProcessCdata", "data"),
        strictness=_args.strictness,
        read_source=_args.read_source,
        mongo_uri=_args.mongo_uri,
        mongo_db_name=_args.mongo_db,
        strong_channel_words=_channels,
        drug_slang_words=_drugs,
        emoji_word_map=_emoji,
        homophone_variants=_homophones,
        trade_context_hints=_hints,
    )
    for plat in _args.platforms:
        run_filter_for_platform(plat, _cfg)
    print(f"✅ 数据清洗完成，平台: {_args.platforms}，严格度: {_args.strictness}")
