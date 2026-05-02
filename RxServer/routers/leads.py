"""大屏读接口：外链服务端探活代理、分页 leads、聚合 stats；读路径顺带契约回填（无序 bulk）。"""

import asyncio
import time
from typing import Any

import requests as _requests
from fastapi import Depends, HTTPException, Query, Request
from fastapi.routing import APIRouter
from pymongo import DESCENDING, UpdateOne
from pymongo.errors import PyMongoError
from pydantic import BaseModel
from sentinel_contract import upgrade_existing_doc

import sentinel_api


router = APIRouter()


class LeadItem(BaseModel):
    schema_version: str
    contract: str
    video_title: str
    source_url: str
    original_content: str
    platform: str
    merchant: str
    AI_analysis: str
    source_platform: str
    ingested_at: int


class Paging(BaseModel):
    page: int
    page_size: int
    total: int
    has_next: bool


class LeadListResponse(BaseModel):
    items: list[LeadItem]
    count: int
    paging: Paging


_url_check_cache: dict[str, tuple[bool | None, float]] = {}
_URL_CHECK_TTL = 3600.0

# B 站常见「软 404」：HTTP 仍 200，靠 HTML 片段特征拦；列表须与爬虫侧观测对齐以减少误判。
_BILI_DEAD_SIGNALS = [
    '"code":-404', '"code": -404',
    '"code":-404,', '"code": -404,',
    '"code":-403', '"code": -403',
    "该内容不存在", "稿件不见了", "视频不见了", "已失效",
    "内容已失效", "视频去哪了", "抱歉，您所访问的内容不存在",
    "视频已删除", "up主已删除视频", "因违规被删除",
    "<title>哔哩哔哩 (゜-゜)つロ 干杯~-bilibili</title>",
    "window._error",
    '"status":404', '"status": 404',
]
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


async def _check_url_alive(url: str) -> bool | None:
    """服务端代请求绕过浏览器 CORS；URL 维 TTL 缓存。`asyncio.to_thread` 隔离阻塞 requests。

    True：判定存活；False：明确失效；None：人机壳页 / 反爬导致信号不足，交由前端弱化展示。"""
    now = time.time()
    if url in _url_check_cache:
        result, ts = _url_check_cache[url]
        if (now - ts) < _URL_CHECK_TTL:
            return result

    def _do() -> bool | None:
        try:
            is_bili = "bilibili.com" in url
            if is_bili:
                r = _requests.get(
                    url, allow_redirects=True, timeout=8,
                    headers={"User-Agent": _BROWSER_UA},
                    stream=True,
                )
                if r.status_code >= 400 or "404" in str(r.url) or "/error" in str(r.url):
                    r.close()
                    return False
                snippet = b""
                # 仅扫响应头若干 KB：筛软 404，避免整页缓冲拖垮延迟与内存。
                for chunk in r.iter_content(512):
                    snippet += chunk
                    if len(snippet) >= 12288:
                        break
                r.close()
                text = snippet.decode("utf-8", errors="ignore")
                if any(sig in text for sig in _BILI_DEAD_SIGNALS):
                    return False
                if "__INITIAL_STATE__" not in text:
                    # SSR 壳或校验页：既不判死也不判活。
                    return None
                return True
            r = _requests.head(
                url, allow_redirects=True, timeout=6,
                headers={"User-Agent": _BROWSER_UA},
            )
            return not ("404" in str(r.url) or r.status_code >= 400)
        except Exception:
            return None

    result = await asyncio.to_thread(_do)
    _url_check_cache[url] = (result, now)
    return result


def _dedupe_stages(base_query: dict[str, Any]) -> list[dict[str, Any]]:
    """聚合管道：业务指纹 `_id` 折叠历史版本，`$first` 取最新 ingested_at 文档。"""
    return [
        {"$match": base_query},
        {"$sort": {"ingested_at": -1, "_id": -1}},
        {
            "$group": {
                "_id": {
                    "source_platform": {"$ifNull": ["$source_platform", "UNKNOWN"]},
                    "source_url": {"$ifNull": ["$source_url", ""]},
                    "original_content": {"$ifNull": ["$original_content", ""]},
                    "platform": {"$ifNull": ["$platform", "无"]},
                    "merchant": {"$ifNull": ["$merchant", "未指明"]},
                    "video_title": {"$ifNull": ["$video_title", ""]},
                },
                "doc": {"$first": "$$ROOT"},
            }
        },
        {"$replaceRoot": {"newRoot": "$doc"}},
    ]


def _normalize_doc(doc: dict[str, Any]) -> LeadItem:
    return LeadItem(
        schema_version=doc.get("schema_version", "legacy"),
        contract=doc.get("contract", "sentinel_leads.legacy"),
        video_title=doc.get("video_title", ""),
        source_url=doc.get("source_url", ""),
        original_content=doc.get("original_content", ""),
        platform=doc.get("platform", "无"),
        merchant=doc.get("merchant", "未指明"),
        AI_analysis=doc.get("AI_analysis", "暂无研判"),
        source_platform=doc.get("source_platform", "UNKNOWN"),
        ingested_at=int(doc.get("ingested_at", 0) or 0),
    )


_stats_cache: dict[str, Any] = {"data": None, "ts": 0.0}
_STATS_TTL = 60.0


def _get_cached_stats() -> dict | None:
    if _stats_cache["data"] is not None and (time.time() - _stats_cache["ts"]) < _STATS_TTL:
        return _stats_cache["data"]
    return None


def _set_stats_cache(data: dict) -> None:
    _stats_cache["data"] = data
    _stats_cache["ts"] = time.time()


@router.get("/api/sentinel/check_url")
@sentinel_api.limiter.limit("120/minute")
async def check_url(
    request: Request,
    url: str = Query(..., description="待检测的原始来源 URL"),
    _: None = Depends(sentinel_api.require_auth),
):
    if not url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400,
            detail={"error_code": "INVALID_URL", "message": "URL 必须以 http:// 或 https:// 开头"},
        )
    alive = await _check_url_alive(url)
    return {"url": url, "alive": alive}


@router.get("/api/sentinel/leads", response_model=LeadListResponse)
@sentinel_api.limiter.limit("60/minute")
async def get_leads(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5000, ge=1, le=50000),
    _: None = Depends(sentinel_api.require_auth),
):
    query: dict[str, Any] = {}
    skip = (page - 1) * page_size
    col = sentinel_api.get_collection()

    try:
        total_cursor = col.aggregate([*_dedupe_stages(query), {"$count": "total"}])
        total = int(next(iter(total_cursor), {"total": 0}).get("total", 0))

        docs = list(
            col.aggregate(
                [
                    *_dedupe_stages(query),
                    {"$sort": {"ingested_at": DESCENDING, "_id": DESCENDING}},
                    {"$skip": skip},
                    {"$limit": page_size},
                ]
            )
        )

        fix_ops: list[UpdateOne] = []
        for d in docs:
            upgraded, changed = upgrade_existing_doc(d)
            for k, v in upgraded.items():
                d[k] = v
            if changed:
                fix_ops.append(UpdateOne({"_id": d.get("_id")}, {"$set": upgraded}))
        if fix_ops:
            # 读路径顺带回填契约字段；`ordered=False` 稀释热点文档上的写锁争抢。
            col.bulk_write(fix_ops, ordered=False)

        items = [_normalize_doc(d) for d in docs]
        return LeadListResponse(
            items=items,
            count=len(items),
            paging=Paging(
                page=page,
                page_size=page_size,
                total=total,
                has_next=(skip + len(items)) < total,
            ),
        )
    except PyMongoError as exc:
        raise sentinel_api._db_error("/api/sentinel/leads", exc) from exc


@router.get("/api/sentinel/stats")
@sentinel_api.limiter.limit("30/minute")
async def get_stats(
    request: Request,
    _: None = Depends(sentinel_api.require_auth),
):
    cached = _get_cached_stats()
    if cached is not None:
        return cached

    base_query: dict[str, Any] = {}
    col = sentinel_api.get_collection()

    try:
        total = int(
            next(
                iter(col.aggregate([*_dedupe_stages(base_query), {"$count": "total"}])),
                {"total": 0},
            ).get("total", 0)
        )

        top_platforms = [
            {"platform": d["_id"] or "无", "count": d["count"]}
            for d in col.aggregate(
                [
                    *_dedupe_stages(base_query),
                    {"$group": {"_id": "$platform", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                    {"$limit": 15},
                ]
            )
        ]
        top_merchants = [
            {"merchant": d["_id"] or "未指明", "count": d["count"], "platform": d.get("platform", "无")}
            for d in col.aggregate(
                [
                    *_dedupe_stages(base_query),
                    {"$match": {"merchant": {"$nin": ["无", "未指明", "未知", ""]}}},
                    {"$group": {"_id": "$merchant", "count": {"$sum": 1}, "platform": {"$first": "$platform"}}},
                    {"$sort": {"count": -1}},
                    {"$limit": 20},
                ]
            )
        ]
        source_platforms = [
            {"source_platform": d["_id"] or "UNKNOWN", "count": d["count"]}
            for d in col.aggregate(
                [
                    *_dedupe_stages(base_query),
                    {"$group": {"_id": "$source_platform", "count": {"$sum": 1}}},
                    {"$sort": {"count": -1}},
                ]
            )
        ]

        result = {
            "total": total,
            "top_platforms": top_platforms,
            "top_merchants": top_merchants,
            "source_platforms": source_platforms,
        }
        _set_stats_cache(result)
        return result

    except PyMongoError as exc:
        raise sentinel_api._db_error("/api/sentinel/stats", exc) from exc
