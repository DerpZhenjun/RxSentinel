"""sentinel_api / routers.leads：假集合分页、合约回填、鉴权分支。

运行：`pytest tests/unit/test_sentinel_api.py -q`
"""
from types import SimpleNamespace

from fastapi.testclient import TestClient

import sentinel_api
import sentinel_core

class FakeCollection:
    """极简 Mongo 替身：支撑 `$match/$sort/$group/...` 单测链路。"""
    def __init__(self, docs):
        self.docs = list(docs)
        self.bulk_ops = []

    def create_index(self, *args, **kwargs):
        return None

    def count_documents(self, _query):
        return len(self.docs)

    def find(self, _query, _projection):
        return FakeCursor(self.docs)

    def aggregate(self, pipeline):
        rows = [dict(d) for d in self.docs]
        for stage in pipeline:
            if "$match" in stage:
                cond = stage["$match"] or {}
                if "merchant" in cond and "$nin" in cond["merchant"]:
                    deny = set(cond["merchant"]["$nin"])
                    rows = [r for r in rows if r.get("merchant") not in deny]
            elif "$sort" in stage:
                for key, direction in reversed(list(stage["$sort"].items())):
                    reverse = direction == -1
                    rows.sort(key=lambda x: x.get(key, 0), reverse=reverse)
            elif "$group" in stage:
                group_spec = stage["$group"]
                gid = group_spec.get("_id")
                if isinstance(gid, dict):
                    grouped = {}
                    for r in rows:
                        key = (
                            r.get("source_platform", "UNKNOWN"),
                            r.get("source_url", ""),
                            r.get("original_content", ""),
                            r.get("platform", "无"),
                            r.get("merchant", "未指明"),
                            r.get("video_title", ""),
                        )
                        if key not in grouped:
                            grouped[key] = {"doc": r}
                    rows = [v for v in grouped.values()]
                else:
                    counter = {}
                    platform_map = {}
                    for r in rows:
                        key = r.get(gid.lstrip("$")) if isinstance(gid, str) and gid.startswith("$") else r.get(gid)
                        counter[key] = counter.get(key, 0) + 1
                        if key not in platform_map:
                            platform_map[key] = r.get("platform", "无")
                    rows = [
                        {"_id": k, "count": v, "platform": platform_map.get(k, "无")}
                        for k, v in counter.items()
                    ]
            elif "$replaceRoot" in stage:
                rows = [r.get("doc", r) for r in rows]
            elif "$skip" in stage:
                rows = rows[stage["$skip"] :]
            elif "$limit" in stage:
                rows = rows[: stage["$limit"]]
            elif "$count" in stage:
                rows = [{"total": len(rows)}]
        return iter(rows)

    def bulk_write(self, ops, ordered=False):
        self.bulk_ops.extend(ops)
        for op in ops:
            target_id = op._filter.get("_id")
            new_url = op._doc.get("$set", {}).get("source_url")
            for d in self.docs:
                if d.get("_id") == target_id:
                    d["source_url"] = new_url
        return SimpleNamespace(modified_count=len(ops))


def _sample_docs():
    return [
        {
            "_id": 1,
            "video_title": "A",
            "source_url": "[https://t.bilibili.com/](https://t.bilibili.com/)116023256686173",
            "original_content": "c1",
            "platform": "推特",
            "merchant": "m1",
            "AI_analysis": "a1",
            "source_platform": "BILI",
            "ingested_at": 3,
        },
        {
            "_id": 2,
            "video_title": "B",
            "source_url": "https://ok.example.com/x",
            "original_content": "c2",
            "platform": "推特",
            "merchant": "m2",
            "AI_analysis": "a2",
            "source_platform": "WB",
            "ingested_at": 2,
        },
        {
            "_id": 22,
            "fingerprint": "legacy_duplicate",
            "video_title": "B",
            "source_url": "https://ok.example.com/x",
            "original_content": "c2",
            "platform": "推特",
            "merchant": "m2",
            "AI_analysis": "a2",
            "source_platform": "WB",
            "ingested_at": 2,
        },
        {
            "_id": 3,
            "video_title": "C",
            "source_url": "https://www.bilibili.com/video/BV1xx411c7mD",
            "original_content": "c3",
            "platform": "推特",
            "merchant": "m3",
            "AI_analysis": "a3",
            "source_platform": "BILI",
            "ingested_at": 1,
        },
    ]


def test_leads_pagination_and_has_next(monkeypatch):
    fake_col = FakeCollection(_sample_docs())
    monkeypatch.setattr(sentinel_core, "get_collection", lambda: fake_col)

    client = TestClient(sentinel_api.app)
    resp = client.get("/api/sentinel/leads?page=1&page_size=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["paging"]["page"] == 1
    assert body["paging"]["page_size"] == 2
    assert body["paging"]["total"] == 3
    assert body["paging"]["has_next"] is True

    # 第二页
    resp2 = client.get("/api/sentinel/leads?page=2&page_size=2")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["count"] == 1
    assert body2["paging"]["has_next"] is False


def test_leads_normalize_source_url_and_writeback(monkeypatch):
    fake_col = FakeCollection(_sample_docs())
    monkeypatch.setattr(sentinel_core, "get_collection", lambda: fake_col)

    client = TestClient(sentinel_api.app)
    resp = client.get("/api/sentinel/leads?page=1&page_size=3")
    assert resp.status_code == 200
    body = resp.json()
    items = body["items"]

    # 首条：Markdown 嵌套的哔哩动态链 → 归一成直连
    assert items[0]["source_url"] == "https://t.bilibili.com/116023256686173"
    assert items[0]["schema_version"] == "2.0.0"
    assert items[0]["contract"] == "sentinel_leads.v2"
    # 合约回填：`bulk_write` 应有 ops
    assert len(fake_col.bulk_ops) >= 1


def test_schema_self_check_endpoint():
    client = TestClient(sentinel_api.app)
    resp = client.get("/api/sentinel/schema")
    assert resp.status_code == 200
    body = resp.json()
    assert body["schema_version"] == "2.0.0"
    assert body["contract"] == "sentinel_leads.v2"
    assert "fields" in body and "source_url" in body["fields"]
    assert "thread_parent_content" in body["fields"]
    assert body["compatibility"]["legacy_read_upgrade"] is True


_TEST_TOKEN = "test-secret-abc123"


def _make_authed_client(monkeypatch, fake_col=None):
    """返回已配置 Token 的测试客户端 + monkeypatched 集合。"""
    monkeypatch.setattr(sentinel_core, "_API_SECRET_KEY", _TEST_TOKEN)
    if fake_col is not None:
        monkeypatch.setattr(sentinel_core, "get_collection", lambda: fake_col)
    return TestClient(sentinel_api.app)


class TestAuth:
    def test_dev_mode_no_token_required(self, monkeypatch):
        """_API_SECRET_KEY 为空时所有接口不需要鉴权（开发模式）。"""
        monkeypatch.setattr(sentinel_core, "_API_SECRET_KEY", "")
        client = TestClient(sentinel_api.app)
        resp = client.get("/api/sentinel/schema")
        assert resp.status_code == 200

    def test_ping_always_public(self, monkeypatch):
        """/ping 不受鉴权影响，即使配置了 Token 也公开。"""
        client = _make_authed_client(monkeypatch)
        assert client.get("/ping").status_code == 200

    def test_health_always_public(self, monkeypatch):
        """/api/health 不受鉴权影响。"""
        client = _make_authed_client(monkeypatch)
        # health 需要 MongoDB；此处仅验证鉴权层不拦截（会因 DB 不可用返回 503，非 401）
        resp = client.get("/api/health")
        assert resp.status_code != 401

    def test_missing_token_returns_401(self, monkeypatch):
        """配置了 Token 时，不带 Authorization 头 → 401。"""
        client = _make_authed_client(monkeypatch)
        assert client.get("/api/sentinel/schema").status_code == 401
        assert client.get("/api/sentinel/leads").status_code == 401
        assert client.get("/api/sentinel/stats").status_code == 401
        assert client.get("/api/sentinel/check_url?url=https://example.com").status_code == 401

    def test_wrong_token_returns_401(self, monkeypatch):
        """错误 Token → 401。"""
        client = _make_authed_client(monkeypatch)
        headers = {"Authorization": "Bearer wrong-token"}
        assert client.get("/api/sentinel/schema", headers=headers).status_code == 401

    def test_correct_token_grants_access(self, monkeypatch):
        """正确 Token → 200。"""
        client = _make_authed_client(monkeypatch)
        headers = {"Authorization": f"Bearer {_TEST_TOKEN}"}
        assert client.get("/api/sentinel/schema", headers=headers).status_code == 200

    def test_leads_with_correct_token(self, monkeypatch):
        """正确 Token 下 /api/sentinel/leads 正常返回数据。"""
        fake_col = FakeCollection(_sample_docs())
        client = _make_authed_client(monkeypatch, fake_col)
        headers = {"Authorization": f"Bearer {_TEST_TOKEN}"}
        resp = client.get("/api/sentinel/leads?page=1&page_size=10", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["count"] > 0

    def test_401_response_body_has_error_code(self, monkeypatch):
        """401 响应体包含 error_code 字段，方便前端处理。"""
        client = _make_authed_client(monkeypatch)
        resp = client.get("/api/sentinel/leads")
        assert resp.status_code == 401
        body = resp.json()
        assert body.get("detail", {}).get("error_code") == "UNAUTHORIZED"
