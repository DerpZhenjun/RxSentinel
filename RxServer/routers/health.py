"""存活探测与契约元数据：`/ping` 无 Mongo；`/api/health` 执行 admin.ping；`/api/sentinel/schema` 列出契约字段。

共享依赖从 `sentinel_core` 引入，避免与 `sentinel_api` 环形 import。"""

from fastapi import Depends, Request
from fastapi.routing import APIRouter
from pymongo.errors import PyMongoError
from sentinel_contract import LEAD_CONTRACT_NAME, LEAD_SCHEMA_VERSION, LeadContract

import sentinel_core

router = APIRouter()


@router.get("/ping")
async def ping():
    """编排探针：零外部依赖，负载均衡只看 HTTP 200 即可。"""
    return {"status": "ok"}


@router.get("/api/health")
@sentinel_core.limiter.limit("120/minute")
async def health(request: Request):
    try:
        client = sentinel_core._get_mongo_client()
        ping_result = client.admin.command("ping")
    except PyMongoError as exc:
        raise sentinel_core._db_error("/api/health", exc, status=503) from exc
    return {
        "status": "ok",
        "db": sentinel_core.DB_NAME,
        "collection": sentinel_core.COLLECTION_NAME,
        "mongo_ping": ping_result.get("ok", 0),
    }


@router.get("/api/sentinel/schema")
@sentinel_core.limiter.limit("120/minute")
async def get_schema_contract(
    request: Request,
    _: None = Depends(sentinel_core.require_auth),
):
    """OpenAPI 静态契约声明；真正写入仍以 `LeadContract` 校验为准。"""
    return {
        "schema_version": LEAD_SCHEMA_VERSION,
        "contract": LEAD_CONTRACT_NAME,
        "collection": sentinel_core.COLLECTION_NAME,
        "fields": list(LeadContract.model_fields.keys()),
        "compatibility": {
            "legacy_read_upgrade": True,
            "read_rewrite_on_upgrade": True,
            "ingest_validate_before_write": True,
        },
    }
