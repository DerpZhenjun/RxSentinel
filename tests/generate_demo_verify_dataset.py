#!/usr/bin/env python3
"""生成 RxSentinel 验证用合成数据（测试夹具生成器，非 pytest 用例）。

目标：**同一批小规模清洗 JSONL** 既可喂 **真实 LLM**（省 token），又可对照 **大屏** 是否误展示。

清洗行 `_demo_bucket` 三类（人工定义的标准答案，用于你对照模型）：
  - `gold_positive`：线索清楚，理想情况下 **应判有效**、**应可进大屏**。
  - `gold_negative`：明显闲聊/无害，理想情况下 **应拒登大屏**。
  - `fuzzy_trap`：承接语、泛指平台、食品语境「糖」、孤立「私我/滴滴」等 —— **劣质模型易误判**，
    理想仍 **应拒登大屏**；若进了大屏即说明 AI 或后处理过宽。

产出：
  ProcessCdata/data/_demo_verify/demo_verify_expectations.json
    — 每条样本的 bucket + **期望是否应作为线索展示**（对照真实 AI 输出用）
  ProcessCdata/data/_demo_verify/<plat>/jsonl/filtered_comments.jsonl
    — 六平台各 30 条顶层评论 + 每平台 6 条楼中楼（负例 / 正例 / 模糊各一组父子评）

典型用法：
  1) python tests/generate_demo_verify_dataset.py --install-to-process-data
     → 合成数据直接写入流水线默认路径 ProcessCdata/data/<plat>/jsonl/filtered_comments.jsonl（省去手动拷贝）
  2) WebUI 跑阶段三 AI（从本地读）+ 阶段四合并 → public/extracted_channels.jsonl → 大屏
  3) 对照 demo_verify_expectations.json 核对误判

仓库根执行：
  python tests/generate_demo_verify_dataset.py
  python tests/generate_demo_verify_dataset.py --install-to-process-data
  python tests/generate_demo_verify_dataset.py --install-to-process-data --backup-existing-filtered
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO_BASE = ROOT / "ProcessCdata" / "data" / "_demo_verify"
PROCESS_DATA = ROOT / "ProcessCdata" / "data"

PLATFORMS = ["bili", "xhs", "zhihu", "dy", "tieba", "weibo"]

NOISE_TEMPLATES = [
    ("今天天气真好，出去骑车了", "周末摸鱼 vlog"),
    ("这段 BGM 是啥求安利", "数码好物分享"),
    ("哈哈哈笑死", "搞笑合集"),
    ("楼主说得对", "日常闲聊"),
    ("已三连支持", "动画混剪"),
    ("原神启动", "游戏实况"),
    ("？？？", "萌宠视频"),
    ("马克备用", "学习打卡"),
    ("前排承包空瓶", "追星剪辑"),
    ("纯路人，我觉得不行", "影评杂谈"),
]

GOLD_POSITIVE_TEMPLATES = [
    ("闲鱼搜「糖娘补给」暗号，店主叫糖舱", "跨性别用药交流"),
    ("海鲜市场 ID：糖纸仓库，拍前私聊改价", "HRT 经验分享"),
    ("电报群 t.me/demo_rx_placeholder 内有清单", "线下药娘互助"),
    ("vx：SugarLane2026，说是贴吧来的给批发价", "激素药物讨论"),
    ("拼多多店铺「激素补给站」搜色谱龙能出", "用药记录"),
    ("淘宝搜补佳乐走代购链接，店名避审查写了「卜佳勒」", "购药渠道"),
    ("微博同名店私信发货，只收支付宝口令红包", "社群爆料"),
    ("快手私信「蓝片」对接人工客服", "科普短视频"),
    ("贴吧精品帖里有方舟健客替代清单 Excel", "用药交流"),
    ("小红书笔记评论区置顶群，验证暗号「糖」", "生活方式"),
]

# 易诱导模型输出「有效贸易」或宽泛 merchant，但按业务红线理想应整体无效 / 不应进大屏。
FUZZY_TRAP_TEMPLATES = [
    ("私我拉群", "网红零食「猪油糖」试吃"),
    ("还有群吗加我一个", "动漫混剪 AMV"),
    ("某宝自己搜补佳乐一大堆不懂别问", "美妆教程合集"),
    ("tg 上好像有我不确定哪个频道", "手机开箱评测"),
    ("这糖真甜回购三次了", "农村手工红糖熬制全程"),
    ("滴滴", "HRT 用药科普"),
    ("谁有路子私我", "萌宠猫咪日常"),
    ("@演示用户 快来看看这个", "激素类药物讨论"),
    ("拼多多便宜你要会搜关键词", "生活方式 vlog"),
    ("同款链接私我哦", "田园治愈短视频"),
]


def make_filtered_row(plat: str, seq: int, bucket: str) -> dict:
    """单条清洗后形态（`_demo_bucket` 供你对照真实 AI；流水线应忽略该字段）。"""
    idx = seq % 10
    if bucket == "gold_negative":
        content, title = NOISE_TEMPLATES[idx]
    elif bucket == "fuzzy_trap":
        content, title = FUZZY_TRAP_TEMPLATES[idx]
    else:
        content, title = GOLD_POSITIVE_TEMPLATES[idx]

    cid = str(8000000 + seq)
    base = {
        "content": content,
        "injected_video_title": title,
        "nickname": f"{plat}_{bucket.split('_')[-1]}_{seq}",
        "user_id": str(1200000 + seq),
        "comment_id": cid,
        "parent_comment_id": "0",
        "_demo_bucket": bucket,
    }

    if plat == "bili":
        base["bvid"] = "BV1GJ411x7h7"
        base["video_id"] = "999888777"
        base["platform"] = "bili"
    elif plat == "xhs":
        base["note_id"] = "demoNoteXhsVerify01"
        base["platform"] = "xhs"
    elif plat == "zhihu":
        base["content_id"] = "1900000000000000999"
        base["content_type"] = "answer"
        base["platform"] = "zhihu"
    elif plat == "dy":
        base["aweme_id"] = "7123456789012345678"
        base["platform"] = "dy"
    elif plat == "tieba":
        base["note_id"] = "6111222333444555666"
        base["note_url"] = "https://tieba.baidu.com/p/6111222333444555666"
        base["platform"] = "tieba"
    elif plat == "weibo":
        base["note_id"] = "5001234567890123"
        base["platform"] = "weibo"
    else:
        raise ValueError(f"unknown demo platform: {plat}")

    return base


def _scope_fields_for_thread_demo(plat: str) -> dict:
    """与 make_filtered_row 同一稿件键，保证 thread_row_utils.thread_scope_key 一致。"""
    if plat == "bili":
        return {"bvid": "BV1GJ411x7h7", "video_id": "999888777", "platform": "bili"}
    if plat == "xhs":
        return {"note_id": "demoNoteXhsVerify01", "platform": "xhs"}
    if plat == "zhihu":
        return {"content_id": "1900000000000000999", "content_type": "answer", "platform": "zhihu"}
    if plat == "dy":
        return {"aweme_id": "7123456789012345678", "platform": "dy"}
    if plat == "tieba":
        return {
            "note_id": "6111222333444555666",
            "note_url": "https://tieba.baidu.com/p/6111222333444555666",
            "platform": "tieba",
        }
    if plat == "weibo":
        return {"note_id": "5001234567890123", "platform": "weibo"}
    raise ValueError(f"unknown plat: {plat}")


# 各平台文件内 comment_id 分区，避免与顶层 8000000+ 冲突
_THREAD_ID_BASE = {
    "bili": 9100000,
    "xhs": 9110000,
    "zhihu": 9120000,
    "dy": 9130000,
    "tieba": 9140000,
    "weibo": 9150000,
}


def append_platform_thread_demonstrations(rows: list[dict], plat: str) -> None:
    """每平台追加三组楼中楼（gold_negative / gold_positive / fuzzy_trap），文案与 B 站演示一致。"""
    base = _THREAD_ID_BASE[plat]
    scope = _scope_fields_for_thread_demo(plat)

    def pair(
        bucket: str,
        pid: str,
        cid: str,
        parent_body: str,
        child_body: str,
        title: str,
        nick_p: str,
        uid_p: str,
        nick_c: str,
        uid_c: str,
    ) -> None:
        rows.append({
            "content": parent_body,
            "injected_video_title": title,
            "nickname": nick_p,
            "user_id": uid_p,
            "comment_id": pid,
            "parent_comment_id": "0",
            "_demo_bucket": bucket,
            **scope,
        })
        rows.append({
            "content": child_body,
            "injected_video_title": title,
            "nickname": nick_c,
            "user_id": uid_c,
            "comment_id": cid,
            "parent_comment_id": pid,
            "_demo_bucket": bucket,
            **scope,
        })

    pair(
        "gold_negative",
        str(base + 1),
        str(base + 2),
        "这 boss 好难打啊求攻略",
        "回复 @层主A : 多看视频就行",
        "魂类游戏实况",
        f"{plat}_threadA",
        str(base + 1),
        f"{plat}_threadB",
        str(base + 2),
    )
    pair(
        "gold_positive",
        str(base + 11),
        str(base + 12),
        "色谱龙现在哪家现货稳定？求店铺名",
        "私你店铺链接了，搜「糖舱」也能找到",
        "HRT 经验分享",
        f"{plat}_buyer",
        str(base + 11),
        f"{plat}_seller",
        str(base + 12),
    )
    pair(
        "fuzzy_trap",
        str(base + 21),
        str(base + 22),
        "这期猫粮测评成分表挺详细的",
        "哈哈哈同意楼上",
        "铲屎官选粮指南",
        f"{plat}_cat",
        str(base + 21),
        f"{plat}_passer",
        str(base + 22),
    )


def write_filtered_per_platform() -> None:
    seq = 0
    for plat in PLATFORMS:
        rows: list[dict] = []
        for _ in range(10):
            rows.append(make_filtered_row(plat, seq, "gold_negative"))
            seq += 1
        for _ in range(10):
            rows.append(make_filtered_row(plat, seq, "gold_positive"))
            seq += 1
        for _ in range(10):
            rows.append(make_filtered_row(plat, seq, "fuzzy_trap"))
            seq += 1
        append_platform_thread_demonstrations(rows, plat)
        out_dir = DEMO_BASE / plat / "jsonl"
        out_dir.mkdir(parents=True, exist_ok=True)
        with (out_dir / "filtered_comments.jsonl").open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_expectations_manifest() -> None:
    """写入对照清单：真实 AI 跑完后逐条核对是否误登大屏。"""
    bucket_definitions = {
        "gold_positive": {
            "description": "含可检索店铺/暗号/外链等，理想应判有效并进入聚合",
            "ideal_valid_trade": True,
            "ideal_show_on_dashboard": True,
        },
        "gold_negative": {
            "description": "闲聊与主题无关内容，理想应拒登大屏",
            "ideal_valid_trade": False,
            "ideal_show_on_dashboard": False,
        },
        "fuzzy_trap": {
            "description": "泛指平台、孤立承接语、食品语境「糖」等；易误判，理想仍应拒登大屏",
            "ideal_valid_trade": False,
            "ideal_show_on_dashboard": False,
        },
    }
    entries: list[dict] = []
    for plat in PLATFORMS:
        fp = DEMO_BASE / plat / "jsonl" / "filtered_comments.jsonl"
        if not fp.is_file():
            continue
        with fp.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                b = str(row.get("_demo_bucket") or "")
                spec = bucket_definitions.get(b, {})
                entries.append({
                    "platform": plat,
                    "comment_id": row.get("comment_id"),
                    "parent_comment_id": row.get("parent_comment_id"),
                    "bucket": b,
                    "ideal_valid_trade": bool(spec.get("ideal_valid_trade")),
                    "ideal_show_on_dashboard": bool(spec.get("ideal_show_on_dashboard")),
                    "video_title": row.get("injected_video_title"),
                    "content": row.get("content"),
                })
    counts = Counter(e["bucket"] for e in entries)
    manifest = {
        "schema_version": "1",
        "purpose": (
            "人工标准答案：跑真实 AI + merge 后，核对每条是否出现在大屏。"
            "gold_negative / fuzzy_trap 若展示则为假阳性；gold_positive 长期缺失则可能是假阴性或合并键问题。"
        ),
        "bucket_definitions": bucket_definitions,
        "counts_by_bucket": dict(counts),
        "entries": entries,
    }
    out = DEMO_BASE / "demo_verify_expectations.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


# WebUI 选用 douyin 时目录名为 douyin，与生成器内 dy 同源；CLI 有时用 wb，与 weibo 同源。
_INSTALL_EXTRA_DIRS = {"dy": ["douyin"], "weibo": ["wb"]}


def install_demo_filtered_to_process_data(*, backup_existing: bool) -> None:
    """将 _demo_verify 各平台 filtered_comments.jsonl 拷入流水线默认目录（覆盖同名文件）。"""
    for plat in PLATFORMS:
        src = DEMO_BASE / plat / "jsonl" / "filtered_comments.jsonl"
        if not src.is_file():
            raise FileNotFoundError(f"缺少演示源文件（请先完整生成）: {src}")
        dest_keys = [plat] + _INSTALL_EXTRA_DIRS.get(plat, [])
        for key in dest_keys:
            dst_dir = PROCESS_DATA / key / "jsonl"
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / "filtered_comments.jsonl"
            if backup_existing and dst.is_file():
                bak = dst.with_suffix(dst.suffix + ".bak_demo_verify")
                shutil.copy2(dst, bak)
            shutil.copy2(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 RxSentinel 验证用合成 filtered JSONL")
    parser.add_argument(
        "--install-to-process-data",
        action="store_true",
        help="把 _demo_verify 下各平台 filtered_comments.jsonl 复制到 ProcessCdata/data/<plat>/jsonl/（流水线默认读盘路径）",
    )
    parser.add_argument(
        "--backup-existing-filtered",
        action="store_true",
        help="与 --install-to-process-data 合用：覆盖前将原有 filtered_comments.jsonl 备份为 .bak_demo_verify",
    )
    args = parser.parse_args()

    DEMO_BASE.mkdir(parents=True, exist_ok=True)
    write_filtered_per_platform()
    write_expectations_manifest()
    if args.install_to_process_data:
        install_demo_filtered_to_process_data(backup_existing=args.backup_existing_filtered)
    print("OK:")
    print(f"  {DEMO_BASE / 'demo_verify_expectations.json'}  ← 对照真实 AI / 大屏")
    print(f"  {DEMO_BASE}/*/jsonl/filtered_comments.jsonl")
    if args.install_to_process_data:
        print(f"  {PROCESS_DATA}/<plat>/jsonl/filtered_comments.jsonl  ← 已从 _demo_verify 安装（供真实 AI 读盘）")


if __name__ == "__main__":
    main()
