"""
RxSentinel 集成测试（真 Mongo）。

本文件一律 `@pytest.mark.integration`；Mongo 不可用时 `mongo_client_session` skip。
示例：`pytest tests/integration/test_integration.py -v -m integration`
"""

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration  # 本文件依赖真 Mongo；未部署则 skip

# routers.leads 是通过 sentinel_api 的循环导入加载的。
# 直接顶层 import 会在 sentinel_api 尚未完整加载时触发 ImportError，
# 因此必须先确保 sentinel_api 完成初始化，再通过 sys.modules 拿到引用。
import sentinel_api as _sentinel_api_init  # noqa: F401 — 先初始化宿主再解析 routers.leads
import sys as _sys
_leads_mod = _sys.modules["routers.leads"]


class TestSyncStageFilesToMongo:

    def test_jsonl_lines_upserted(self, test_db, integration_mongo_uri, integration_db_name, tmp_path):
        """JSONL 每行 fingerprint upsert 入 raw_comments。"""
        from webui_core import sync_stage_files_to_mongo

        jsonl = tmp_path / "sample.jsonl"
        jsonl.write_text(
            '{"content": "买糖 tg私我", "author": "user1"}\n'
            '{"content": "正常评论内容", "author": "user2"}\n',
            encoding="utf-8",
        )

        count, logs = sync_stage_files_to_mongo(
            stage="crawler",
            platform="bili",
            file_paths=[str(jsonl)],
            mongo_uri=integration_mongo_uri,
            mongo_db_name=integration_db_name,
        )

        assert count == 2
        assert any("upsert 2" in msg for msg in logs)

        col = test_db["raw_comments"]
        assert col.count_documents({"platform": "bili"}) == 2
        docs = list(col.find({"platform": "bili"}, {"payload": 1}))
        contents = {d["payload"].get("content") for d in docs}
        assert "买糖 tg私我" in contents

    def test_csv_rows_upserted(self, test_db, integration_mongo_uri, integration_db_name, tmp_path):
        """CSV DictReader 逐行写入 filtered_comments。"""
        from webui_core import sync_stage_files_to_mongo

        csv_file = tmp_path / "data.csv"
        csv_file.write_text(
            "author,content\nuser1,买糖\nuser2,普通内容\n",
            encoding="utf-8",
        )

        count, logs = sync_stage_files_to_mongo(
            stage="filter",
            platform="weibo",
            file_paths=[str(csv_file)],
            mongo_uri=integration_mongo_uri,
            mongo_db_name=integration_db_name,
        )

        assert count == 2
        col = test_db["filtered_comments"]
        assert col.count_documents({"platform": "weibo"}) == 2

    def test_idempotent_double_sync(self, test_db, integration_mongo_uri, integration_db_name, tmp_path):
        """同一文件同步两遍：指纹幂等，文档条数仍为 2。"""
        from webui_core import sync_stage_files_to_mongo

        jsonl = tmp_path / "dup.jsonl"
        jsonl.write_text('{"x": 1}\n{"x": 2}\n', encoding="utf-8")

        sync_stage_files_to_mongo("crawler", "bili", [str(jsonl)], integration_mongo_uri, integration_db_name)
        sync_stage_files_to_mongo("crawler", "bili", [str(jsonl)], integration_mongo_uri, integration_db_name)

        col = test_db["raw_comments"]
        assert col.count_documents({}) == 2  # 依然只有 2 条

    def test_corrupt_json_line_gracefully_stored(self, test_db, integration_mongo_uri, integration_db_name, tmp_path):
        """JSON 解析失败的行以 _raw_line 字段存入，不抛出异常。"""
        from webui_core import sync_stage_files_to_mongo

        jsonl = tmp_path / "corrupt.jsonl"
        jsonl.write_text(
            '{"good": "line"}\n'
            'not valid json {{{}\n',
            encoding="utf-8",
        )

        count, logs = sync_stage_files_to_mongo(
            "crawler", "bili", [str(jsonl)], integration_mongo_uri, integration_db_name
        )

        assert count == 2
        col = test_db["raw_comments"]
        corrupt_docs = list(col.find({"payload._raw_line": {"$exists": True}}))
        assert len(corrupt_docs) == 1

    def test_empty_file_list_returns_zero(self, test_db, integration_mongo_uri, integration_db_name):
        """空文件列表时立即返回 0，不建立连接。"""
        from webui_core import sync_stage_files_to_mongo

        count, logs = sync_stage_files_to_mongo(
            "crawler", "bili", [], integration_mongo_uri, integration_db_name
        )
        assert count == 0
        assert logs == []

    def test_missing_file_skipped_gracefully(self, test_db, integration_mongo_uri, integration_db_name):
        """文件不存在时返回 0 条并记录警告，不抛出异常。"""
        from webui_core import sync_stage_files_to_mongo

        count, logs = sync_stage_files_to_mongo(
            "crawler", "bili",
            ["/nonexistent/path/file.jsonl"],
            integration_mongo_uri, integration_db_name,
        )
        assert count == 0
        assert any("⚠️" in msg for msg in logs)

    def test_invalid_stage_raises(self, integration_mongo_uri, integration_db_name):
        """未知 stage 参数应立即抛出 ValueError。"""
        from webui_core import sync_stage_files_to_mongo

        with pytest.raises(ValueError, match="Unknown stage"):
            sync_stage_files_to_mongo(
                "bad_stage", "bili", [], integration_mongo_uri, integration_db_name
            )

    def test_fingerprint_is_deterministic(self, tmp_path):
        """相同输入产生相同指纹（基础幂等保证）。"""
        from webui_core import build_fingerprint

        fp1 = build_fingerprint("crawler", "bili", "/a/b.jsonl", 1, '{"x": 1}')
        fp2 = build_fingerprint("crawler", "bili", "/a/b.jsonl", 1, '{"x": 1}')
        assert fp1 == fp2
        assert len(fp1) == 40  # SHA-1 十六进制长度

    def test_fingerprint_changes_on_different_line(self, tmp_path):
        """不同行号产生不同指纹。"""
        from webui_core import build_fingerprint

        fp1 = build_fingerprint("crawler", "bili", "/f.jsonl", 1, '{"x": 1}')
        fp2 = build_fingerprint("crawler", "bili", "/f.jsonl", 2, '{"x": 1}')
        assert fp1 != fp2


def _make_lead(n: int) -> dict:
    """构造最小合法线索文档。"""
    return {
        "schema_version": "2.0.0",
        "contract": "sentinel_leads.v2",
        "fingerprint": f"fp_{n}",
        "video_title": f"Video {n}",
        "source_url": f"https://example.com/{n}",
        "original_content": f"content_{n}",
        "platform": "推特",
        "merchant": f"merchant_{n}",
        "AI_analysis": f"analysis_{n}",
        "source_platform": "WB",
        "ingested_at": int(time.time()) + n,
    }


class TestSentinelApiWithRealMongo:

    def _patched_client(self, test_db):
        """`get_collection` 绑到测试库 `sentinel_leads`。"""
        import sentinel_api
        col = test_db["sentinel_leads"]
        return TestClient(sentinel_api.app), col

    def test_leads_empty_collection(self, test_db):
        """空数据库时 /api/sentinel/leads 返回空列表，total=0。"""
        import sentinel_api

        col = test_db["sentinel_leads"]
        with patch.object(sentinel_api, "get_collection", return_value=col):
            client = TestClient(sentinel_api.app)
            resp = client.get("/api/sentinel/leads?page=1&page_size=10")

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["paging"]["total"] == 0

    def test_leads_insert_and_query(self, test_db):
        """插入 3 条数据后通过 API 能查回全部 3 条。"""
        import sentinel_api

        col = test_db["sentinel_leads"]
        col.insert_many([_make_lead(i) for i in range(3)])

        with patch.object(sentinel_api, "get_collection", return_value=col):
            client = TestClient(sentinel_api.app)
            resp = client.get("/api/sentinel/leads?page=1&page_size=10")

        assert resp.status_code == 200
        assert resp.json()["count"] == 3

    def test_leads_pagination(self, test_db):
        """分页：page_size=2, 共 5 条 → 第 1 页 has_next=True，第 3 页 count=1。"""
        import sentinel_api

        col = test_db["sentinel_leads"]
        col.insert_many([_make_lead(i) for i in range(5)])

        with patch.object(sentinel_api, "get_collection", return_value=col):
            client = TestClient(sentinel_api.app)

            r1 = client.get("/api/sentinel/leads?page=1&page_size=2")
            assert r1.json()["paging"]["has_next"] is True

            r3 = client.get("/api/sentinel/leads?page=3&page_size=2")
            assert r3.json()["count"] == 1
            assert r3.json()["paging"]["has_next"] is False

    def test_stats_returns_aggregated_data(self, test_db):
        """插入数据后 /api/sentinel/stats 返回正确的 total 和 top_platforms。"""
        import sentinel_api

        col = test_db["sentinel_leads"]
        col.insert_many([_make_lead(i) for i in range(4)])

        # 清 stats 内存缓存，强制走聚合
        _leads_mod._stats_cache["data"] = None

        with patch.object(sentinel_api, "get_collection", return_value=col):
            client = TestClient(sentinel_api.app)
            resp = client.get("/api/sentinel/stats")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 4
        assert any(p["platform"] == "推特" for p in body["top_platforms"])

    def test_stats_ttl_cache_served(self, test_db):
        """TTL 缓存命中时返回缓存数据，而非重新聚合。"""
        import sentinel_api

        _leads_mod._stats_cache["data"] = {"total": 999, "top_platforms": [], "top_merchants": [], "source_platforms": []}
        _leads_mod._stats_cache["ts"] = time.time()  # 缓存仍在 TTL 内

        col = test_db["sentinel_leads"]
        with patch.object(sentinel_api, "get_collection", return_value=col):
            client = TestClient(sentinel_api.app)
            resp = client.get("/api/sentinel/stats")

        assert resp.status_code == 200
        assert resp.json()["total"] == 999  # 命中内存缓存分支

        _leads_mod._stats_cache["data"] = None  # 避免污染后续用例

    def test_stats_ttl_cache_expires(self, test_db):
        """过期缓存（ts 在 TTL 之外）应重新计算。"""
        import sentinel_api

        col = test_db["sentinel_leads"]
        col.insert_many([_make_lead(i) for i in range(2)])

        _leads_mod._stats_cache["data"] = {"total": 999, "top_platforms": [], "top_merchants": [], "source_platforms": []}
        _leads_mod._stats_cache["ts"] = time.time() - _leads_mod._STATS_TTL - 1  # 故意戳过期

        with patch.object(sentinel_api, "get_collection", return_value=col):
            client = TestClient(sentinel_api.app)
            resp = client.get("/api/sentinel/stats")

        assert resp.status_code == 200
        assert resp.json()["total"] == 2  # 走 DB 重算而非缓存里的 999

        _leads_mod._stats_cache["data"] = None  # 避免污染后续用例

    def test_deduplication_removes_duplicates(self, test_db):
        """后端去重：相同 (source_url, original_content, platform, merchant) 只返回最新一条。"""
        import sentinel_api

        col = test_db["sentinel_leads"]
        base = _make_lead(0)
        dup = dict(base)
        dup["fingerprint"] = "fp_dup"
        dup["ingested_at"] = base["ingested_at"] - 10  # 故意旧于 base，聚合应丢掉 dup

        col.insert_many([base, dup])

        with patch.object(sentinel_api, "get_collection", return_value=col):
            client = TestClient(sentinel_api.app)
            resp = client.get("/api/sentinel/leads?page=1&page_size=10")

        assert resp.status_code == 200
        assert resp.json()["count"] == 1  # `$group` 指纹折叠后仅剩最新根文档
