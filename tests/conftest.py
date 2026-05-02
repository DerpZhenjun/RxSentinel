"""
pytest 共享入口：`tests/unit` 与 `tests/integration` 自动装载。

职责：
  - `sys.path`：仓库根、`RxServer`、`ProcessCdata` 可被 import
  - 在导入 `data_filter` 之前桩掉 `matplotlib`，规避 numpy 冲突
  - Mongo 会话级 fixture：库不可用时 skip，收尾 `drop_database` 不留垃圾
"""

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
RXSERVER_DIR = ROOT_DIR / "RxServer"
PROCESS_DIR = ROOT_DIR / "ProcessCdata"

for _p in (str(ROOT_DIR), str(RXSERVER_DIR), str(PROCESS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

if "matplotlib" not in sys.modules:
    _mpl_stub = types.ModuleType("matplotlib")
    _mpl_stub.pyplot = MagicMock()
    _mpl_stub.rcParams = {}
    sys.modules["matplotlib"] = _mpl_stub
    sys.modules["matplotlib.pyplot"] = MagicMock()

_INTEGRATION_URI = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
_INTEGRATION_DB = "rxsentinel_integration_test"


@pytest.fixture(scope="session")
def mongo_client_session():
    """会话级真 MongoClient；连不上则整文件 integration skip；yield 后删测试库。"""
    from pymongo import MongoClient

    try:
        client = MongoClient(_INTEGRATION_URI, serverSelectionTimeoutMS=2000)
        client.admin.command("ping")
    except Exception as exc:
        pytest.skip(f"MongoDB not available at {_INTEGRATION_URI}: {exc}")
        return

    yield client

    client.drop_database(_INTEGRATION_DB)
    client.close()


@pytest.fixture
def test_db(mongo_client_session):
    """函数级指向集成库；每条用例前后清集合。"""
    db = mongo_client_session[_INTEGRATION_DB]
    for col in db.list_collection_names():
        db.drop_collection(col)
    yield db
    for col in db.list_collection_names():
        db.drop_collection(col)


@pytest.fixture
def integration_mongo_uri():
    return _INTEGRATION_URI


@pytest.fixture
def integration_db_name():
    return _INTEGRATION_DB
