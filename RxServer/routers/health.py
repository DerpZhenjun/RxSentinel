"""存活探测与契约元数据：`/ping` 无 Mongo；`/api/health` 执行 admin.ping；`/api/sentinel/schema` 列出契约字段。

`import sentinel_api` 共享 limiter / `_get_mongo_client`；单测可 monkeypatch 宿主导出符号。"""

from fastapi import Depends, Request
from fastapi.routing import APIRouter
from pymongo.errors import PyMongoError
from sentinel_contract import LEAD_CONTRACT_NAME, LEAD_SCHEMA_VERSION, LeadContract

import sentinel_api  # 环形 import：宿主须先于路由模块完成 FastAPI / limiter / DB 绑定

router = APIRouter()


@router.get("/ping")
async def ping():
    """编排探针：零外部依赖，负载均衡只看 HTTP 200 即可。"""
    return {"status": "ok"}


@router.get("/api/health")
@sentinel_api.limiter.limit("120/minute")
async def health(request: Request):
    try:
        client = sentinel_api._get_mongo_client()
        ping_result = client.admin.command("ping")
    except PyMongoError as exc:
        raise sentinel_api._db_error("/api/health", exc, status=503) from exc
    return {
        "status": "ok",
        "db": sentinel_api.DB_NAME,
        "collection": sentinel_api.COLLECTION_NAME,
        "mongo_ping": ping_result.get("ok", 0),
    }


@router.get("/api/sentinel/schema")
@sentinel_api.limiter.limit("120/minute")
async def get_schema_contract(
    request: Request,
    _: None = Depends(sentinel_api.require_auth),
):
    """OpenAPI 静态契约声明；真正写入仍以 `LeadContract` 校验为准。"""
    return {
        "schema_version": LEAD_SCHEMA_VERSION,
        "contract": LEAD_CONTRACT_NAME,
        "collection": sentinel_api.COLLECTION_NAME,
        "fields": list(LeadContract.model_fields.keys()),
        "compatibility": {
            "legacy_read_upgrade": True,
            "read_rewrite_on_upgrade": True,
            "ingest_validate_before_write": True,
        },
    }
