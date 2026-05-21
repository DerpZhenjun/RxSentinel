"""sentinel_leads v2：契约校验、外链归一、`fingerprint` 确定性拼装。

入库与读路径升级共用同一文档形状；指纹作 Mongo upsert 幂等键，拦同源重复写入。"""

import hashlib
import re
import time
from typing import Any

from pydantic import BaseModel

LEAD_SCHEMA_VERSION = "2.0.0"
LEAD_CONTRACT_NAME = "sentinel_leads.v2"


class LeadContract(BaseModel):
    """Pydantic 硬闸：任一字段不合规直接拒写，避免脏文档污染大屏聚合。"""
    schema_version: str
    contract: str
    fingerprint: str
    source_platform: str
    video_title: str
    source_url: str
    original_content: str
    thread_parent_content: str = ""
    platform: str
    merchant: str
    AI_analysis: str
    ingested_at: int


def normalize_platform_name(platform_value: str) -> str:
    """别名映射到固定展示名，防止同一渠道在多桶统计里拆开。"""
    raw = str(platform_value or "").strip().lower()
    if raw in {"推", "推特", "twitter", "x"}:
        return "推特"
    if raw in {"tg", "telegram", "电报", "纸飞机"}:
        return "Telegram"
    if raw in {"微信", "绿泡", "绿泡泡", "vx", "v"}:
        return "微信"
    return str(platform_value or "无").strip() or "无"


def normalize_bili_url(raw: str) -> str:
    """B 站：从杂乱文本抽取 BV/av/动态 ID，落成规范播放页或动态页；无解返回空。"""
    value = (raw or "").strip()
    if not value:
        return ""
    bv = re.search(r"BV[0-9A-Za-z]+", value)
    if bv:
        return f"https://www.bilibili.com/video/{bv.group(0)}"
    av = re.search(r"av\d+", value, flags=re.IGNORECASE)
    if av:
        return f"https://www.bilibili.com/video/{av.group(0).lower()}"
    dynamic = re.search(r"\b\d{12,}\b", value)
    if dynamic:
        return f"https://t.bilibili.com/{dynamic.group(0)}"
    return ""


def normalize_general_url(raw: str) -> str:
    """取文本中最后一个 http(s)；疑似 Markdown 断裂（含 `](`）丢弃，避免伪链接入库。"""
    value = (raw or "").strip()
    if not value:
        return ""
    matches = re.findall(r"https?://[^\s)]+", value)
    if not matches:
        return ""
    url = matches[-1].rstrip("]")
    # `](`：Markdown 未闭合链接，常为爬虫占位，拒绝入库
    if "](" in url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return ""


def normalize_source_url(url: str) -> str:
    """域名命中 B 站族先用 `normalize_bili_url`，否则走通用 URL 抽取兜底。"""
    text = (url or "").strip()
    lower = text.lower()
    if "bilibili.com" in lower or "t.bilibili.com" in lower or "bv" in text or "av" in lower:
        candidate = normalize_bili_url(text)
        if candidate:
            return candidate
    return normalize_general_url(text)


def build_lead_fingerprint(source_platform: str, source_url: str, original_content: str) -> str:
    """上游未带指纹时：三元组 UTF-8 → SHA1，保证跨阶段 replay 同一实体落到同一键。"""
    seed = f"{source_platform}_{source_url}_{original_content}"
    return hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()


def coalesce_video_title(raw: dict[str, Any]) -> str:
    """合并多路标题：AI/契约 `video_title`、清洗阶段 `injected_video_title`、各平台 `title`/`desc`。

    注意：``raw.get("injected_video_title", "默认")`` 在键存在且值为空串时**不会**使用默认，
    必须显式遍历，否则爬取已写入的标题在入库时仍会丢。
    """
    for key in ("video_title", "injected_video_title", "title", "desc"):
        v = raw.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def to_contract_doc(raw: dict[str, Any], now_ts: int | None = None) -> dict[str, Any]:
    """宽松 dict → 契约形状：填空默认、URL/平台名归一后走 `LeadContract.model_validate`。"""
    ts = int(now_ts if now_ts is not None else time.time())
    source_platform = str(raw.get("source_platform") or "UNKNOWN").strip() or "UNKNOWN"
    source_url = normalize_source_url(str(raw.get("source_url") or ""))
    original_content = str(raw.get("original_content") or "").strip()

    merged = {
        "schema_version": LEAD_SCHEMA_VERSION,
        "contract": LEAD_CONTRACT_NAME,
        "fingerprint": str(raw.get("fingerprint") or build_lead_fingerprint(source_platform, source_url, original_content)),
        "source_platform": source_platform,
        "video_title": coalesce_video_title(raw),
        "source_url": source_url,
        "original_content": original_content,
        "thread_parent_content": str(raw.get("thread_parent_content") or "").strip(),
        "platform": normalize_platform_name(str(raw.get("platform") or "无")),
        "merchant": str(raw.get("merchant") or "未指明").strip() or "未指明",
        "AI_analysis": str(raw.get("AI_analysis") or "暂无研判").strip() or "暂无研判",
        "ingested_at": int(raw.get("ingested_at") or ts),
    }
    model = LeadContract.model_validate(merged)
    return model.model_dump()


def upgrade_existing_doc(raw: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """迁遗留文档至 v2：`changed=False` 则读路径可跳过 bulk 回写，降写放大。"""
    upgraded = to_contract_doc(raw)
    changed = False
    for k, v in upgraded.items():
        if raw.get(k) != v:
            changed = True
            break
    return upgraded, changed


