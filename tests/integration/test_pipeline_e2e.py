"""
集成：`PipelineRunner.run_merge_stage` → 真 Mongo → `/api/sentinel/*`。

磁盘写 AI JSONL，patch `PROCESS_DIR`/`MONGO_*` 指临时目录与测试库。
`pytest tests/integration/test_pipeline_e2e.py -v -m integration`
"""

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration  # 真 Mongo；未起则 skip

import sentinel_api as _sentinel_api_init  # noqa: F401 — 先加载宿主再取 routers.leads
import sys as _sys
_leads_mod = _sys.modules["routers.leads"]


def _write_ai_jsonl(base_dir: Path, platform: str, records: list[dict]) -> Path:
    """写入 `ProcessCdata/data/<plat>/jsonl/ai_extracted_channels.jsonl`。"""
    out_dir = base_dir / "ProcessCdata" / "data" / platform / "jsonl"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "ai_extracted_channels.jsonl"
    with out_file.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return out_file


def _make_ai_record(idx: int, platform_label: str = "微信") -> dict:
    """单条模拟 AI 输出。"""
    return {
        "video_title": f"视频{idx}",
        "source_url": f"https://www.bilibili.com/video/av{1000 + idx}",
        "original_content": f"评论内容 {idx}，加微信买糖",
        "platform": platform_label,
        "merchant": f"商家{idx}",
        "AI_analysis": f"风险分析 {idx}",
    }


def _build_runner(cfg, tmp_path: Path, test_db, integration_mongo_uri: str, integration_db_name: str):
    """shell/spawn/sleep 全 noop，只测 merge 文件与 Mongo。"""
    from pipeline_runner import PipelineRunner

    return PipelineRunner(
        config=cfg,
        log_fn=lambda msg: None,
        toast_fn=lambda msg, **_: None,
        progress_fn=lambda pct, text="": None,
        shell_fn=lambda cmd, cwd: 0,  # 禁止真实子进程
        spawn_fn=lambda cmd, cwd: None,
        sleep_fn=lambda secs: None,
    )


def _make_config(platforms: list[str], overwrite_dash: bool = True):
    from pipeline_runner import PipelineConfig
    return PipelineConfig(
        platforms=platforms,
        start_date="2025-01-01",
        end_date="2025-01-31",
        crawl_type="search",
        login_type="cookie",
        search_keyword="",
        crawler_storage_mode="只存入本地",
        filter_storage_mode="只存入本地",
        ai_storage_mode="只存入本地",
        filter_read_mode="从本地读",
        ai_read_mode="从本地读",
        ai_platform="Ollama (本地离线)",
        active_model_name="qwen3:8b",
        ds_api_key="",
        max_process=0,
        custom_ai_prompt="",
        auto_push=True,
        overwrite_dash=overwrite_dash,
    )


class TestMergeStageWithRealMongo:
    """`run_merge_stage`：JSONL → `public/extracted_channels.jsonl` → Mongo upsert。"""

    def _run_merge(self, tmp_path, platforms, records_by_plat,
                   test_db, integration_mongo_uri, integration_db_name,
                   overwrite_dash=True):
        """写盘 → merge → 返回 `sentinel_leads` 集合句柄。"""
        for plat, records in records_by_plat.items():
            _write_ai_jsonl(tmp_path, plat, records)

        cfg = _make_config(platforms, overwrite_dash=overwrite_dash)
        runner = _build_runner(cfg, tmp_path, test_db, integration_mongo_uri, integration_db_name)

        proc_dir = str(tmp_path / "ProcessCdata")
        dash_dir = str(tmp_path / "SentinelDashboard")

        with patch("pipeline_runner.PROCESS_DIR", proc_dir), \
             patch("pipeline_runner.DASHBOARD_DIR", dash_dir), \
             patch("pipeline_runner.MONGO_URI", integration_mongo_uri), \
             patch("pipeline_runner.MONGO_DB_NAME", integration_db_name), \
             patch("pipeline_runner.MONGO_COLLECTION", "sentinel_leads"):
            runner.run_merge_stage()

        return test_db["sentinel_leads"]

    def test_records_inserted_into_mongo(self, test_db, integration_mongo_uri,
                                          integration_db_name, tmp_path):
        """3 条 JSONL 记录应全部写入 sentinel_leads。"""
        col = self._run_merge(
            tmp_path, ["bili"],
            {"bili": [_make_ai_record(i) for i in range(3)]},
            test_db, integration_mongo_uri, integration_db_name,
        )
        assert col.count_documents({}) == 3

    def test_source_platform_set_correctly(self, test_db, integration_mongo_uri,
                                            integration_db_name, tmp_path):
        """source_platform 字段应为平台名大写（BILI）。"""
        col = self._run_merge(
            tmp_path, ["bili"],
            {"bili": [_make_ai_record(1)]},
            test_db, integration_mongo_uri, integration_db_name,
        )
        doc = col.find_one({})
        assert doc["source_platform"] == "BILI"

    def test_cross_platform_dedup(self, test_db, integration_mongo_uri,
                                   integration_db_name, tmp_path):
        """两个平台各 2 条不同记录，合并后 MongoDB 中应有 4 条。"""
        col = self._run_merge(
            tmp_path, ["bili", "xhs"],
            {
                "bili": [_make_ai_record(1), _make_ai_record(2)],
                "xhs":  [_make_ai_record(3), _make_ai_record(4)],
            },
            test_db, integration_mongo_uri, integration_db_name,
        )
        assert col.count_documents({}) == 4

    def test_duplicate_content_deduped(self, test_db, integration_mongo_uri,
                                        integration_db_name, tmp_path):
        """相同 source_url + original_content 的记录应去重，只保留一条。"""
        dup = _make_ai_record(99)
        col = self._run_merge(
            tmp_path, ["bili"],
            {"bili": [dup, dup]},   # 两条完全相同
            test_db, integration_mongo_uri, integration_db_name,
        )
        assert col.count_documents({}) == 1

    def test_fingerprint_field_present(self, test_db, integration_mongo_uri,
                                        integration_db_name, tmp_path):
        """每条记录都应有 fingerprint 字段（由 to_contract_doc 生成）。"""
        col = self._run_merge(
            tmp_path, ["bili"],
            {"bili": [_make_ai_record(1)]},
            test_db, integration_mongo_uri, integration_db_name,
        )
        doc = col.find_one({})
        assert "fingerprint" in doc and doc["fingerprint"]

    def test_jsonl_merged_file_written_to_disk(self, test_db, integration_mongo_uri,
                                                integration_db_name, tmp_path):
        """run_merge_stage 应在 SentinelDashboard/public/ 写入聚合 JSONL 文件。"""
        self._run_merge(
            tmp_path, ["bili"],
            {"bili": [_make_ai_record(1), _make_ai_record(2)]},
            test_db, integration_mongo_uri, integration_db_name,
        )
        merged = tmp_path / "SentinelDashboard" / "public" / "extracted_channels.jsonl"
        assert merged.exists()
        lines = [l for l in merged.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 2

    def test_stale_records_cleared_before_upsert(self, test_db, integration_mongo_uri,
                                                   integration_db_name, tmp_path):
        """同平台的旧记录应在写入前被清除，防止历史 fingerprint 幽灵堆积。"""
        # 首轮写入 3 条
        self._run_merge(
            tmp_path, ["bili"],
            {"bili": [_make_ai_record(i) for i in range(3)]},
            test_db, integration_mongo_uri, integration_db_name,
        )
        assert test_db["sentinel_leads"].count_documents({}) == 3

        # 第二轮仅 1 条：应先删该平台旧快照再 upsert
        col = self._run_merge(
            tmp_path, ["bili"],
            {"bili": [_make_ai_record(99)]},
            test_db, integration_mongo_uri, integration_db_name,
            overwrite_dash=True,
        )
        # 期望库里只剩本轮一条，排除 fingerprint 幽灵叠加
        assert col.count_documents({}) == 1


class TestApiReturnsAfterMerge:
    """merge 落库后，`TestClient` 验证 `/api/sentinel/leads`、`/stats`。"""

    def test_leads_endpoint_reflects_merged_data(self, test_db, integration_mongo_uri,
                                                   integration_db_name, tmp_path):
        """merge 写入 2 条数据后，API /leads 应返回 count=2。"""
        import sentinel_api

        # merge
        records = [_make_ai_record(i) for i in range(2)]
        _write_ai_jsonl(tmp_path, "bili", records)

        cfg = _make_config(["bili"])
        runner = _build_runner(cfg, tmp_path, test_db, integration_mongo_uri, integration_db_name)
        col = test_db["sentinel_leads"]

        with patch("pipeline_runner.PROCESS_DIR", str(tmp_path / "ProcessCdata")), \
             patch("pipeline_runner.DASHBOARD_DIR", str(tmp_path / "SentinelDashboard")), \
             patch("pipeline_runner.MONGO_URI", integration_mongo_uri), \
             patch("pipeline_runner.MONGO_DB_NAME", integration_db_name), \
             patch("pipeline_runner.MONGO_COLLECTION", "sentinel_leads"):
            runner.run_merge_stage()

        # API：`get_collection` 指向测试集合
        with patch.object(sentinel_api, "get_collection", return_value=col):
            client = TestClient(sentinel_api.app)
            resp = client.get("/api/sentinel/leads?page=1&page_size=10")

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2

    def test_source_platform_visible_in_api_response(self, test_db, integration_mongo_uri,
                                                       integration_db_name, tmp_path):
        """API 返回的每条 lead 应包含正确的 source_platform 字段。"""
        import sentinel_api

        _write_ai_jsonl(tmp_path, "xhs", [_make_ai_record(1)])

        cfg = _make_config(["xhs"])
        runner = _build_runner(cfg, tmp_path, test_db, integration_mongo_uri, integration_db_name)
        col = test_db["sentinel_leads"]

        with patch("pipeline_runner.PROCESS_DIR", str(tmp_path / "ProcessCdata")), \
             patch("pipeline_runner.DASHBOARD_DIR", str(tmp_path / "SentinelDashboard")), \
             patch("pipeline_runner.MONGO_URI", integration_mongo_uri), \
             patch("pipeline_runner.MONGO_DB_NAME", integration_db_name), \
             patch("pipeline_runner.MONGO_COLLECTION", "sentinel_leads"):
            runner.run_merge_stage()

        with patch.object(sentinel_api, "get_collection", return_value=col):
            client = TestClient(sentinel_api.app)
            resp = client.get("/api/sentinel/leads?page=1&page_size=10")

        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["source_platform"] == "XHS"

    def test_stats_endpoint_reflects_merged_data(self, test_db, integration_mongo_uri,
                                                   integration_db_name, tmp_path):
        """merge 后 /stats 端点应返回正确 total 并包含对应平台。"""
        import sentinel_api

        _write_ai_jsonl(tmp_path, "bili", [_make_ai_record(i) for i in range(4)])

        cfg = _make_config(["bili"])
        runner = _build_runner(cfg, tmp_path, test_db, integration_mongo_uri, integration_db_name)
        col = test_db["sentinel_leads"]

        with patch("pipeline_runner.PROCESS_DIR", str(tmp_path / "ProcessCdata")), \
             patch("pipeline_runner.DASHBOARD_DIR", str(tmp_path / "SentinelDashboard")), \
             patch("pipeline_runner.MONGO_URI", integration_mongo_uri), \
             patch("pipeline_runner.MONGO_DB_NAME", integration_db_name), \
             patch("pipeline_runner.MONGO_COLLECTION", "sentinel_leads"):
            runner.run_merge_stage()

        _leads_mod._stats_cache["data"] = None  # 强制 stats 重算

        with patch.object(sentinel_api, "get_collection", return_value=col):
            client = TestClient(sentinel_api.app)
            resp = client.get("/api/sentinel/stats")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 4
        _leads_mod._stats_cache["data"] = None  # 防止泄漏到其他集成用例
