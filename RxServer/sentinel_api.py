"""FastAPI 宿主：路由只做分发。共享状态见 `sentinel_core`。"""

import argparse
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from sentinel_core import (
    COLLECTION_NAME,
    DB_NAME,
    ensure_indexes,
    get_collection,
    limiter,
    logger,
)

# 单测打桩：路由已改用 `sentinel_core`，历史代码仍可 patch 下列同名导出（与 core 为同一对象）。
from sentinel_core import (  # noqa: F401
    MONGO_URI,
    _API_SECRET_KEY,
    _db_error,
    _get_mongo_client,
    require_auth,
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
