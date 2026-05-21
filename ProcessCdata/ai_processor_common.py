"""DeepSeek / Ollama 共用子系统：提示词拼装、Mongo 拉清洗结果、逐行 LLM 推理与图表。

依赖调用方（WebUI / pipeline_runner）事先把 `ProcessCdata` 加入 `sys.path`。"""

import datetime
import json
import logging
import os
import time
from collections import Counter
from typing import Callable

logger = logging.getLogger(__name__)

import matplotlib.pyplot as plt
from pymongo import MongoClient

from lead_noise_gate import should_suppress_lead
from thread_row_utils import (
    build_source_url,
    enrich_rows_with_parent_comments,
    extract_item_id,
    first_landing_url_from_row,
    resolve_source_url,
    thread_scope_key,
)

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
AI_PROMPT_CONFIG_FILE = os.path.join(CURRENT_DIR, "config", "ai_prompt_config.json")

DEFAULT_AI_PROMPT_BODY = """
你是一名具备刑侦反欺诈与网络情报分析能力的高级数据专家。你的任务是从社交媒体的极短评论中，精准提取处方药/HRT药物的灰色地下交易网络数据。

【专属黑话知识库（升级版）】
1. 药物与代称（示例，不限于此）：糖、补佳乐/补jj/小补、诺坤复/蓝片/白片、小白瓶、凝胶、雌二醇、色谱龙、螺内酯、比卡鲁胺、黄体酮等。
2. 渠道与平台映射（示例，不限于此）：
   - 电商类：咸鱼/海鲜市场/某鱼 -> 闲鱼；pdd/拼夕夕 -> 拼多多；tb/某宝 -> 淘宝；方舟/健客 -> 方舟健客。
   - 社交类：tg/纸飞机 -> Telegram；推/推上/小蓝鸟 -> 推特；vx/微x/卫星 -> 微信；企鹅/扣扣 -> qq。
3. 反混淆信号：谐音词、错别字、emoji、符号分隔写法、字母变体（如 t4ng、t.a.n.g）都可能指向交易暗号。
4. 结合最新规则库：优先参考当前系统词库（variant_lexicon）中的同义词、上下文提示词与 emoji 映射。

【提取铁律与红线】（违反任何一条，判定为无效）
1. 必须是真实的“买卖/供给/引流”动作。求助、吃瓜、纯用药记录均判定为无效。
2. 🎯【实体提取严格限制】：merchant 必须有「可落地的卖方或检索线索」。泛指平台而无店铺/暗号时 merchant 填“无”。⚠️ 孤立的一句「私我」「拉我」「进群」「还有群吗」「拉我进群」「加我」「滴滴」等**不算**有效引流：除非父评或本条另有具体药物、店铺名、搜索暗号、外链或明确的代购/供货描述，否则整条 **is_valid_trade 必须为 false**，禁止输出「【个人引流】…」糊弄过关。
3. 🛑【结合语境防误杀（极度重要）】：必须严格结合《所属视频/帖子标题》进行交叉验证！
   - ❌ 如果视频标题是关于真正的食品/零食（如“猪油糖”、“手工制作”、“农村生活”等），评论中的“糖”就是字面意思的糖果，绝对不是激素处方药！直接判定为无效！
   - ❌ 只有视频主题与跨性别、医药、边缘亚文化相关，或者上下文明示了买药行为时，才可将“糖”认定为黑产。
4. 🛑【无上下文的 @ 拒绝提取（极度重要）】：如果评论仅仅是“@某人”（例如：“@威”、“@じ★ve絕戀”、“@张三 看这个”），且没有附带任何明确的买卖、引流或求药暗号文字，一律判定为无效（is_valid_trade: false）。绝不能仅仅因为 @ 了某个人就认定为引流！
5. 🛑【楼中楼必须读父评（极度重要）】：若提供了「被回复的评论」，必须把父评与本条一起看；仅当父评+本条共同指向药物/HRT 灰产交易或引流时才可判有效。若本条只是“私信”“某宝捏”等承接语而父评仅为闲聊、聊色、游戏、梗图，则一律无效。
6. 🛑【无 actionable 线索 = 无效】：评论（含父评）必须能回答「具体怎么找到卖药的/在哪下单/搜什么暗号」至少一项。若仅为泛泛语气（如「某宝有」「PDD 买仿制药」「切药器」）、纯病友闲聊、情绪附和、或只剩平台大类而无店铺/暗号/确定性卖家，**一律 is_valid_trade: false**。正规 OTC 经验分享、显而易见可自行网购的路径，不是你要抓的灰产情报。
7. 🛑【问号索取无下文】：仅「哪家店」「怎么买」「求链接」且对方未在本条或父评给出可检索线索的，若本条仍无补充，判无效。
8. 🛑【楼中楼双空话】：父评为「私我/滴滴/进群」等承接语，本条仅为「拉我/我也想进群/还有群吗」及 emoji，**双方均无**店铺名、链接、暗号、检索词的 → **必须 false**；不得拆成两条「有效」糊弄。
9. 🛑【私信上下文未完成】：仅「私信你了」「回复我」「推链接好」「给个微信」而无具体卖方、商品检索路径的 → **false**。「私信截图」「又给吞了」等闲聊 → **false**。
10. 🛑【处方药 OTC 病友指路】：仅讨论保法止/非那/切药器/仿制药在哪买、拼多多某宝泛指，**无**具体灰产卖家或引流暗号的 → **false**（正规渠道自救经验不是情报）。
11. 🛑【生物黑客/加群邀约】：「来我微信群」「主页得出」「看下我主页」等泛邀约且无药物交易线索 → **false**。
"""

FIXED_CONTEXT_BLOCK = """
【上下文数据】
所属视频/帖子标题："{video_title}"
评论者昵称："{author}"
被回复的评论（楼中楼时为上一层用户评论全文；顶层评论则无此项）："{parent_comment}"
本条评论原文："{comment_text}"
"""

FIXED_OUTPUT_REQUIREMENTS = """
【输出要求】
必须且只能输出合法的 JSON 对象，严禁输出任何 Markdown 标记（不要出现 ```json ）。请按照以下字段进行推导和提取：

{{
  "original_content": "在此处原封不动地填入评论原文",
  "reasoning_step": "简短思考：结合视频标题，这是真正的买药还是聊普通的食物？如果是纯粹的@好友吃瓜，直接判定无效。",
  "is_valid_trade": true,
  "platform": "标准平台名称（如闲鱼、本站私信。无则填'无'）",
  "merchant": "具体的店铺名或暗号。仅在满足铁律第2条（非空话承接、有可落地线索）时，方可输出「【个人引流】{author}」。否则整条应判无效而非勉强填 merchant。无则填'无'",
  "AI_analysis": "一句话提炼具体的购买手段或引流方式",
  "confidence_score": 9
}}
"""


def compose_prompt_template(prompt_body: str) -> str:
    body = (prompt_body or "").strip()
    if not body:
        body = DEFAULT_AI_PROMPT_BODY.strip()
    return f"{body}\n\n{FIXED_CONTEXT_BLOCK.strip()}\n\n{FIXED_OUTPUT_REQUIREMENTS.strip()}\n"


def load_prompt_body(default_body: str = DEFAULT_AI_PROMPT_BODY) -> str:
    if not os.path.exists(AI_PROMPT_CONFIG_FILE):
        save_prompt_template(default_body)
        return default_body
    try:
        with open(AI_PROMPT_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        prompt_body = data.get("prompt_body", "")
        if isinstance(prompt_body, str) and prompt_body.strip():
            return prompt_body
        legacy_full_prompt = data.get("prompt_template", "")
        if isinstance(legacy_full_prompt, str) and legacy_full_prompt.strip():
            # 旧版整包提示词：截断「上下文数据」固定段之前的主体，避免重复拼装。
            return legacy_full_prompt.split("【上下文数据】")[0].strip()
    except Exception:
        pass
    return default_body


def load_prompt_template(default_prompt_body: str = DEFAULT_AI_PROMPT_BODY) -> str:
    return compose_prompt_template(load_prompt_body(default_prompt_body))


def save_prompt_template(prompt_body: str):
    os.makedirs(os.path.dirname(AI_PROMPT_CONFIG_FILE), exist_ok=True)
    payload = {"prompt_body": prompt_body}
    with open(AI_PROMPT_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def platform_aliases(platform):
    alias_map = {
        "douyin": ["douyin", "dy"],
        "dy": ["dy", "douyin"],
        "kuaishou": ["kuaishou", "ks"],
        "ks": ["ks", "kuaishou"],
        "weibo": ["weibo", "wb"],
        "wb": ["wb", "weibo"],
    }
    return alias_map.get(platform, [platform])


# MongoClient 按 URI 进程级单例；驱动内部自带连接池。

_mongo_pool: dict[str, MongoClient] = {}


def _get_mongo_client(uri: str) -> MongoClient:
    """同一 URI 只构造一次 Client。"""
    if uri not in _mongo_pool:
        _mongo_pool[uri] = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return _mongo_pool[uri]


def load_filtered_rows(platform: str, mongo_uri: str, mongo_db_name: str):
    client = _get_mongo_client(mongo_uri)
    col = client[mongo_db_name]["filtered_comments"]
    docs = list(col.find(
        {"stage": "filter", "platform": {"$in": platform_aliases(platform)}},
        {"payload": 1},
    ))
    return [d.get("payload") for d in docs if isinstance(d.get("payload"), dict)]


def build_author_name(data: dict) -> str:
    nick = data.get("nickname") or data.get("author") or "未知昵称"
    uid = str(data.get("user_id") or data.get("mid") or data.get("uid") or data.get("id") or "未知ID").strip()
    return f"{nick} (ID:{uid})"


def rows_to_json_lines(rows):
    return [json.dumps(r, ensure_ascii=False) for r in rows]


# 两条 Processor 共用的推理外壳（日志 / tqdm / 图表）。

def generate_chart(platform_counter: Counter, chart_output_file: str, platform_name: str, engine: str = "AI") -> None:
    """渠道分布柱状图；零命中不写盘。"""
    logger.info("[%s] 正在生成 %s 提取图表...", platform_name.upper(), engine)
    if not platform_counter:
        logger.warning("[%s] %s 未提取到有效渠道数据，跳过图表生成", platform_name.upper(), engine)
        return

    top_platforms = platform_counter.most_common(10)
    labels, values = zip(*top_platforms)

    plt.figure(figsize=(10, 6))
    bars = plt.bar(labels, values, color='#D65F5F')
    plt.title(f'[{platform_name.upper()}] {engine} 提取：处方药地下交易渠道分布', fontsize=15, fontweight='bold')
    plt.xlabel('平台/渠道类型', fontsize=12)
    plt.ylabel('评论提及频次', fontsize=12)
    plt.xticks(rotation=45)
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width() / 2.0, yval, int(yval), va='bottom', ha='center')
    plt.tight_layout()
    plt.savefig(chart_output_file, dpi=300)
    plt.close()
    logger.info("图表已保存: %s", chart_output_file)


def load_input_lines(
    platform: str,
    input_file: str,
    read_source: str,
    mongo_uri: str,
    mongo_db_name: str,
    max_count: int | None,
) -> list[str] | None:
    """「db」→ 拉 Mongo 清洗集合；否则读本地 JSONL。空则 None，上层整平台跳过。"""
    if read_source == "db":
        rows = load_filtered_rows(platform, mongo_uri, mongo_db_name)
        if not rows:
            logger.warning("[%s] MongoDB 中找不到 filtered_comments 数据，跳过", platform.upper())
            return None
        lines = rows_to_json_lines(rows)
    else:
        if not os.path.exists(input_file):
            logger.warning("[%s] 找不到 filtered_comments.jsonl，跳过", platform.upper())
            return None
        with open(input_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

    if not lines:
        logger.warning("[%s] 无符合条件的清洗数据，跳过", platform.upper())
        return None

    if max_count is not None and max_count < len(lines):
        logger.info("[%s] 小样本模式：仅处理前 %d 条数据", platform.upper(), max_count)
        lines = lines[:max_count]

    return lines


def write_log_header(f_log, platform: str, engine: str, model_name: str) -> None:
    f_log.write(
        f"\n{'='*50}\n"
        f"执行时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"分析引擎: {engine} ({model_name})\n"
        f"目标平台: [{platform.upper()}]\n"
        f"{'-'*50}\n"
    )


def write_summary(f_log, processed: int, extracted: int, errors: int, engine: str) -> None:
    hit_rate = (extracted / processed * 100) if processed > 0 else 0
    summary = (
        f"\n{'-'*15} {engine} 分析报告 {'-'*15}\n"
        f"送审清洗数据: {processed} 条\n"
        f"成功挖掘渠道: {extracted} 条\n"
        f"请求/解析报错: {errors} 次\n"
        f"有效挖掘率: {hit_rate:.2f}%\n"
        f"{'='*50}\n\n"
    )
    logger.info("[%s] 处理完成 | 送审: %d | 命中: %d | 错误: %d | 命中率: %.2f%%",
                engine, processed, extracted, errors, hit_rate)
    f_log.write(summary)


def run_platform_pipeline(
    platform: str,
    input_lines: list,
    output_file: str,
    chart_output_file: str,
    log_file: str,
    prompt_template: str,
    engine: str,
    model_name: str,
    call_llm: Callable[[str], dict],
    delay: float = 0.05,
) -> None:
    """云端 / 本地推理共用：`call_llm` 注入具体厂商；单行异常只抬升 error 计数，不短路全批。"""
    from tqdm import tqdm  # 延迟 import，规避与 tqdm 的 import 环

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    extracted_count = 0
    error_count = 0
    platform_counter = Counter()
    pbar = None

    parsed_rows: list[dict] = []
    for line in input_lines:
        line = line.strip()
        if not line:
            continue
        try:
            parsed_rows.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("[%s] 跳过非法 JSON 行", platform.upper())
    # 全平台统一：同一批内按 parent_comment_id 填充 thread_parent_content（见 thread_row_utils）
    enrich_rows_with_parent_comments(parsed_rows, platform)
    total_lines = len(parsed_rows)

    with open(log_file, 'a', encoding='utf-8') as f_log:
        write_log_header(f_log, platform, engine, model_name)
        try:
            open(output_file, 'w', encoding='utf-8').close()
            with open(output_file, 'a', encoding='utf-8') as outfile:
                pbar = tqdm(total=total_lines, desc=f"[{platform.upper()}] {engine}分析", unit="条")
                processed_lines = 0

                for data in parsed_rows:
                    processed_lines += 1
                    try:
                        comment_text = data.get("content", data.get("original_content", ""))
                        # 不能写 get("injected_video_title", "未提供标题")：键存在且为 "" 时不会用默认，导致写库 video_title 为空。
                        picked = ""
                        for _k in ("injected_video_title", "video_title", "title", "desc"):
                            _v = data.get(_k)
                            if _v is not None and str(_v).strip():
                                picked = str(_v).strip()
                                break
                        prompt_title = picked or "未提供标题"
                        author_name = build_author_name(data)

                        if not comment_text:
                            pbar.update(1)
                            continue

                        pbar.set_postfix_str(f"{comment_text[:20].replace(chr(10), ' ')}...", refresh=False)
                        parent_raw = str(data.get("thread_parent_content") or "").strip()
                        parent_for_prompt = (
                            parent_raw if parent_raw else "（无：顶层评论，或父评未收录于本批数据）"
                        )
                        formatted_prompt = prompt_template.format(
                            video_title=prompt_title,
                            author=author_name,
                            parent_comment=parent_for_prompt,
                            comment_text=comment_text,
                        )
                        ai_result = call_llm(formatted_prompt)
                        platform_name = ai_result.get("platform", "无").strip()
                        is_valid = ai_result.get("is_valid_trade", False)

                        if is_valid and platform_name not in ["无", "未知", ""]:
                            if should_suppress_lead(data, ai_result):
                                tqdm.write(
                                    "⚪ [硬闸丢弃] 空话/无双承接/OTC 泛指等，未写入输出（避免大屏噪声）"
                                )
                                pbar.update(1)
                                if delay > 0:
                                    time.sleep(delay)
                                continue
                            extracted_count += 1
                            merchant_name = ai_result.get("merchant", "无")
                            analysis_detail = ai_result.get("AI_analysis", "无")
                            original_content = ai_result.get("original_content", comment_text)
                            platform_counter[platform_name] += 1

                            source_url = resolve_source_url(platform, data)

                            final_record = {
                                "source_platform": platform,
                                "video_title": picked,
                                "source_url": source_url,
                                "original_content": original_content,
                                "thread_parent_content": str(data.get("thread_parent_content") or "").strip(),
                                "platform": platform_name,
                                "merchant": merchant_name,
                                "AI_analysis": analysis_detail,
                            }
                            outfile.write(json.dumps(final_record, ensure_ascii=False) + "\n")
                            tqdm.write(f"🟢 [命中] 平台:{platform_name} | 商家:{merchant_name} | 分析:{analysis_detail}")

                    except Exception as e:
                        tqdm.write(f"🔴 [{engine}] 解析或请求出错: {e}")
                        error_count += 1

                    pbar.update(1)
                    if delay > 0:
                        time.sleep(delay)

                pbar.close()
                pbar = None

            write_summary(f_log, processed_lines, extracted_count, error_count, engine)
            if extracted_count > 0:
                generate_chart(platform_counter, chart_output_file, platform, engine=engine)

        except KeyboardInterrupt:
            if pbar:
                try:
                    pbar.close()
                except Exception:
                    pass
            msg = f"[{platform.upper()}] {engine} 分析被手动中止"
            logger.warning(msg)
            f_log.write(msg + "\n")
        except Exception as e:
            if pbar:
                try:
                    pbar.close()
                except Exception:
                    pass
            msg = f"[{platform.upper()}] 发生严重错误，跳过平台: {e}"
            logger.error(msg, exc_info=True)
            f_log.write(msg + "\n")
