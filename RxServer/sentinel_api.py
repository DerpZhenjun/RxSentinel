"""FastAPI 宿主：Mongo、鉴权、慢限流与 `_db_error` 横切收口于此，路由只做分发。

大屏读 `/api/sentinel/*`、管线入库与此同源配置。子路由晚挂载：`routers.*` 反向引用本模块
共享符号，利用解释器 import 缓存——须先在本文初始化 `get_collection` / `limiter` 再 `include_router`。"""

import argparse
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
DB_NAME = os.getenv("MONGODB_DB", "Oestrogen")
COLLECTION_NAME = os.getenv("MONGODB_COLLECTION", "sentinel_leads")

# 密钥为空：全流程放行（仅适合本机）；生产须在 .env 落 `API_SECRET_KEY`。
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


# IP 粒度计数；超限走 slowapi 统一异常形态。
limiter = Limiter(key_func=get_remote_address)

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


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """启动期尽力建索引；连库失败仅告警，进程仍可起（降级读）。"""
    try:
        ensure_indexes(get_collection())
        logger.info("MongoDB indexes ensured. DB=%s collection=%s", DB_NAME, COLLECTION_NAME)
    except Exception as exc:
        logger.warning("MongoDB not available on startup, indexes skipped: %s", exc)
    yield


app = FastAPI(title="RxSentinel Data API", version="2.0.0", lifespan=_lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 共享绑定就绪后再挂路由，避免子模块 import 宿主时抢到半初始化状态。
from routers.health import router as _health_router  # noqa: E402
from routers.leads import router as _leads_router  # noqa: E402

app.include_router(_health_router)
app.include_router(_leads_router)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
