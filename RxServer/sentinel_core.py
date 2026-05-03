"""Mongo / 限流 / 鉴权共享层：`routers.*` 只依赖本模块，避免与 `sentinel_api` 环形 import。

单测可对 `sentinel_core.get_collection`、`_API_SECRET_KEY` 等打桩。"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import Header, HTTPException
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
DB_NAME = os.getenv("MONGODB_DB", "Oestrogen")
COLLECTION_NAME = os.getenv("MONGODB_COLLECTION", "sentinel_leads")

_API_SECRET_KEY: str = os.getenv("API_SECRET_KEY", "").strip()


def require_auth(authorization: str | None = Header(default=None)) -> None:
    """Bearer 头逐字节对齐；`.env` 未配密钥则整条链路放行（仅限本机联调）。"""
    if not _API_SECRET_KEY:
        return
    if authorization != f"Bearer {_API_SECRET_KEY}":
        raise HTTPException(
            status_code=401,
            detail={"error_code": "UNAUTHORIZED", "message": "缺少或无效的 API 密钥"},
        )


_RATELIMIT_ENV_PLACEHOLDER = Path(__file__).resolve().parent / "ratelimit_env_placeholder.env"
limiter = Limiter(key_func=get_remote_address, config_filename=str(_RATELIMIT_ENV_PLACEHOLDER))

_mongo_pool: dict[str, MongoClient] = {}


def _get_mongo_client() -> MongoClient:
    """同一 URI 进程内单例 MongoClient，削握手与连接风暴。"""
    if MONGO_URI not in _mongo_pool:
        _mongo_pool[MONGO_URI] = MongoClient(
            MONGO_URI, serverSelectionTimeoutMS=4000, connectTimeoutMS=4000
        )
    return _mongo_pool[MONGO_URI]


def get_collection() -> Collection:
    """路由与测试共用集合句柄；不显式 close，随进程退出回收。"""
    return _get_mongo_client()[DB_NAME][COLLECTION_NAME]


def ensure_indexes(col: Collection) -> None:
    col.create_index("fingerprint", unique=True, background=True)
    col.create_index([("ingested_at", DESCENDING)], background=True)
    col.create_index([("platform", ASCENDING), ("ingested_at", DESCENDING)], background=True)
    col.create_index([("merchant", ASCENDING), ("ingested_at", DESCENDING)], background=True)
    col.create_index([("source_platform", ASCENDING), ("ingested_at", DESCENDING)], background=True)


def _db_error(endpoint: str, exc: Exception, status: int = 503) -> HTTPException:
    """Mongo 异常 → 503 + 泛化 `detail`，细节只落日志，防对内拓扑泄露。"""
    logger.error("DB error in %s: %s", endpoint, exc, exc_info=True)
    return HTTPException(
        status_code=status,
        detail={"error_code": "DB_ERROR", "message": "数据库服务暂时不可用，请稍后重试"},
    )
