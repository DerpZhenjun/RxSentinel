"""LLM 之后与合并阶段的硬闸：空话引流、楼中楼双承接等 — 宁可漏杀也不进大屏。

合并写入 `extracted_channels.jsonl` 前会再次调用 `is_obvious_noise_lead`，拦截历史/误判入库的垃圾行。"""

from __future__ import annotations

import re
from typing import Any

_ACTIONABLE = re.compile(
    r"(店铺|店名|搜「|搜\s*[「\"]|暗号|关键词|http|https|\.com|闲鱼|淘宝|拼多多"
    r"|t\.me|telegram|电报|二维码|链接[:：]|BV[0-9a-zA-Z]{8,}|订单号|ID[:：]|SugarLane|demo_rx)",
    re.I,
)

_OTC_POINTER = re.compile(
    r"(切药器|仿制药|国产仿制|保法止|非那雄胺|外用非那|米诺|滇虹|昆药|多多上买|拼多多买|pdd)"
    r".{0,96}(试试|可以|就行|不贵|便宜|切成)",
    re.I,
)

# 仅当「整句很短」且去掉噪声字符后 **完全等于** 下列之一才视为纯 ping（不误伤「想买药私我详聊」）
_SOLO_EXACT_PING_CORE = frozenset(
    ("私我", "私信", "私信我", "私聊", "滴滴", "拉拉"),
)

# 较长、语义明确的承接空话短语 —— 可按子串匹配（仍受长度上限约束）
_SOLO_VAGUE_MARKERS = (
    "拉我进群",
    "拉我，",
    "拉我 ",
    "我想进群",
    "我也想进群",
    "还有群吗",
    "还有群",
    "进群吗",
    "求拉",
    "带带我",
    "加我",
    "推链接好",
    "推链接",
    "私信你了",
    "私聊你了",
    "私信你",
    "给个微信",
    "所以说给个微信",
    "你看一下我的主页",
    "看下主页",
    "私信截图吧",
    "又给吞了",
    "老师可以来我的生物黑客微信群",
)

# 承接 / 拉群侧（不含裸「进群」，避免误伤「怎么进群官网买」类）
_INVITE_FLUFF = re.compile(
    r"(拉我进群|拉我[,，]|拉我\s+|我也想进群|我想进群|还有群吗|还有群|进群吗|求拉|拉群|带我)",
    re.I,
)
_PING_FLUFF = re.compile(r"(私我|私信|私聊|滴滴)", re.I)

# 父评「私我」等短 ping 后，本条仅为「已私你了」式确认、无实质线索
_DM_ACK_FLUFF = re.compile(
    r"(私聊你了|私信你了|已私信你|私你了|回你了|发你了|给你发了|私过去了)",
    re.I,
)


def _thread_is_invite_ping_noise(parent: str, text: str, combo: str) -> bool:
    """楼中楼：一侧拉群承接、一侧私我/滴滴类 ping，或双侧都是拉群空话。"""
    if _ACTIONABLE.search(combo):
        return False
    inv = _INVITE_FLUFF
    ping = _PING_FLUFF
    return bool(
        (inv.search(text) and ping.search(parent))
        or (inv.search(parent) and ping.search(text))
        or (inv.search(text) and inv.search(parent))
    )

_BAN_SUBSTRINGS = (
    "推链接好",
    "私信截图吧",
    "又给吞了",
    "私信你了回复我",
    "老师可以来我的生物黑客微信群",
    "所以说给个微信",
    "你看一下我的主页",
)


def _strip_noise_chars(s: str) -> str:
    return re.sub(
        r'[\s\u200b\ufeff😭😢💦🥺😖😿❗️!?？!，。、…～·・「」【】\[\]（）［］：:]+|'
        r'\[大哭\]|\[图片\]|大图',
        "",
        s,
        flags=re.I,
    )


def _weak_merchant(merchant: str) -> bool:
    m = str(merchant or "").strip()
    ml = m.lower()
    return (
        not m
        or m == "无"
        or m == "未知"
        or "个人引流" in m
        or ml in ("none", "n/a")
    )


def is_obvious_noise_lead(original_content: str, thread_parent_content: str) -> bool:
    """
    仅看本条 + 父评（忽略模型填的 merchant）：典型「私我 / 拉我进群」双空话、承接 emoji 等。
    合并阶段与 AI 硬闸共用，避免历史 jsonl / hallucinated merchant 漏网。
    """
    text = str(original_content or "").strip()
    parent = str(thread_parent_content or "").strip()
    if not text:
        return True
    if _ACTIONABLE.search(text) or _ACTIONABLE.search(parent):
        return False

    combo = f"{parent}\n{text}"

    if parent:
        pc = _strip_noise_chars(parent)
        if len(pc) <= 10:
            if re.match(r"^(私我|私信|滴滴|拉拉|私聊)$", parent.strip()) or parent.strip() in (
                "私我",
                "私信",
                "滴滴",
            ):
                if _INVITE_FLUFF.search(text):
                    return True
                # 父：私我 / 滴滴 —— 子：私聊你了（非拉群，但也是空话承接）
                core_reply = _strip_noise_chars(text)
                if len(core_reply) <= 22 and _DM_ACK_FLUFF.search(text):
                    return True
        if _thread_is_invite_ping_noise(parent, text, combo):
            return True

    core = _strip_noise_chars(text)
    if len(core) <= 38:
        if len(core) <= 12 and core in _SOLO_EXACT_PING_CORE:
            return True
        if any(k in text for k in _SOLO_VAGUE_MARKERS):
            return True
        if re.search(r"(我也想进群|还有群吗|拉我进群)", text):
            return True

    if any(b in text for b in _BAN_SUBSTRINGS):
        return True

    return False


def should_suppress_lead(row: dict[str, Any], ai: dict[str, Any]) -> bool:
    """
    Returns True → 本条不应写入 ai_extracted_channels。
    仅在 ai[is_valid_trade] 已为 True 时调用。
    """
    text = str(ai.get("original_content") or row.get("content") or "").strip()
    parent = str(row.get("thread_parent_content") or "").strip()

    if not ai.get("is_valid_trade"):
        return False

    if is_obvious_noise_lead(text, parent):
        return True

    merchant = str(ai.get("merchant") or "").strip()
    analysis = str(ai.get("AI_analysis") or "").strip()

    if not text:
        return True

    weak = _weak_merchant(merchant)
    core = _strip_noise_chars(text)
    parent_core = _strip_noise_chars(parent)

    if _ACTIONABLE.search(text):
        return False

    if weak and any(b in text for b in _BAN_SUBSTRINGS):
        return True

    if weak and len(core) <= 36:
        if len(core) <= 12 and core in _SOLO_EXACT_PING_CORE:
            return True
        if any(k in text for k in _SOLO_VAGUE_MARKERS):
            return True

    if parent and weak:
        combo = text + "\n" + parent
        if _thread_is_invite_ping_noise(parent, text, combo):
            return True
        if len(parent_core) <= 8 and re.match(r"^(私我|私信|滴滴)$", parent.strip()):
            if _INVITE_FLUFF.search(text) and not _ACTIONABLE.search(text):
                return True

    if weak and _OTC_POINTER.search(text) and not _ACTIONABLE.search(text):
        return True

    if weak and len(text) < 72:
        if re.search(r"私信联系|私聊获取|详见私信", analysis) and not _ACTIONABLE.search(text):
            return True

    plat_hint = str(ai.get("platform") or "").strip()
    if plat_hint in ("本站私信", "无") and weak and len(core) <= 28:
        if _INVITE_FLUFF.search(text) or (len(core) <= 10 and core in _SOLO_EXACT_PING_CORE):
            return True

    return False
