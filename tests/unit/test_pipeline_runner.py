"""PipelineRunner：注入式假 shell/spawn/sleep，验证命令拼装与阶段短路。

不落真实子进程、Mongo、磁盘。"""

import json

import pytest
from unittest.mock import patch

from pipeline_runner import (
    DASH_MERGE_SKIP,
    PipelineConfig,
    PipelineRunner,
    CRAWLER_DIR,
    PROCESS_DIR,
    DASHBOARD_DIR,
    ROOT_DIR,
)


def _cfg(**overrides) -> PipelineConfig:
    """最小可跑配置；字段由 `overrides` 覆盖。"""
    defaults = dict(
        platforms=["bili"],
        start_date="2025-01-01",
        end_date="2025-01-31",
        crawl_type="search",
        login_type="cookie",
        search_keyword="买糖",
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
    )
    defaults.update(overrides)
    return PipelineConfig(**defaults)


def _make_runner(cfg: PipelineConfig, shell_calls: list, spawn_calls: list) -> PipelineRunner:
    """shell/spawn 调用记入列表，便于断言顺序与参数。"""
    return PipelineRunner(
        config=cfg,
        log_fn=lambda msg: None,
        toast_fn=lambda msg, **_: None,
        progress_fn=lambda pct, text="": None,
        shell_fn=lambda cmd, cwd: (shell_calls.append((cmd, cwd)), 0)[1],
        spawn_fn=lambda cmd, cwd: spawn_calls.append((cmd, cwd)),
        sleep_fn=lambda secs: None,
    )


# patch 目标一律写 `pipeline_runner` 模块属性，避免打到别处。
_MOD = "pipeline_runner"


class TestCrawlStage:

    def test_crawl_builds_correct_command(self):
        """crawl 阶段应为 bili 平台构建含 --platform bili 的命令。"""
        shell_calls, spawn_calls = [], []
        cfg = _cfg(platforms=["bili"])
        runner = _make_runner(cfg, shell_calls, spawn_calls)
        with patch(f"{_MOD}.has_raw_data", return_value=False):
            runner.run_crawl_stage()
        assert len(shell_calls) == 1
        cmd, cwd = shell_calls[0]
        assert "--platform bili" in cmd
        assert "--lt cookie" in cmd
        assert "--type search" in cmd
        assert cwd == CRAWLER_DIR

    def test_crawl_appends_keywords_in_search_mode(self):
        """search 模式且有关键词时，命令应包含 --keywords。"""
        shell_calls, spawn_calls = [], []
        cfg = _cfg(crawl_type="search", search_keyword="买糖,卖糖")
        runner = _make_runner(cfg, shell_calls, spawn_calls)
        with patch(f"{_MOD}.has_raw_data", return_value=False):
            runner.run_crawl_stage()
        cmd = shell_calls[0][0]
        assert "--keywords" in cmd
        assert "买糖" in cmd

    def test_crawl_no_keywords_in_detail_mode(self):
        """detail 模式下命令不应包含 --keywords。"""
        shell_calls, spawn_calls = [], []
        cfg = _cfg(crawl_type="detail", search_keyword="买糖")
        runner = _make_runner(cfg, shell_calls, spawn_calls)
        with patch(f"{_MOD}.has_raw_data", return_value=False):
            runner.run_crawl_stage()
        cmd = shell_calls[0][0]
        assert "--keywords" not in cmd

    def test_crawl_douyin_uses_dy_alias(self):
        """douyin 平台在命令中应替换为 dy。"""
        shell_calls, spawn_calls = [], []
        cfg = _cfg(platforms=["douyin"])
        runner = _make_runner(cfg, shell_calls, spawn_calls)
        with patch(f"{_MOD}.has_raw_data", return_value=False):
            runner.run_crawl_stage()
        cmd = shell_calls[0][0]
        assert "--platform dy" in cmd
        assert "--platform douyin" not in cmd

    def test_crawl_skips_when_data_exists(self):
        """has_raw_data=True 且平台不在覆盖列表时，不应执行任何命令。"""
        shell_calls, spawn_calls = [], []
        cfg = _cfg(platforms=["bili"], overwrite_crawler_plats=[])
        runner = _make_runner(cfg, shell_calls, spawn_calls)
        with patch(f"{_MOD}.has_raw_data", return_value=True):
            runner.run_crawl_stage()
        assert shell_calls == []

    def test_crawl_overwrite_forces_rerun(self):
        """平台在 overwrite_crawler_plats 列表中时，即使数据存在也应执行。"""
        shell_calls, spawn_calls = [], []
        cfg = _cfg(platforms=["bili"], overwrite_crawler_plats=["bili"])
        runner = _make_runner(cfg, shell_calls, spawn_calls)
        with patch(f"{_MOD}.has_raw_data", return_value=True):
            runner.run_crawl_stage()
        assert len(shell_calls) == 1

    def test_crawl_runs_multiple_platforms(self):
        """多平台时应为每个平台各运行一条命令。"""
        shell_calls, spawn_calls = [], []
        cfg = _cfg(platforms=["bili", "xhs"])
        runner = _make_runner(cfg, shell_calls, spawn_calls)
        with patch(f"{_MOD}.has_raw_data", return_value=False):
            runner.run_crawl_stage()
        platforms_in_cmds = [cmd for cmd, _ in shell_calls]
        assert any("bili" in c for c in platforms_in_cmds)
        assert any("xhs" in c for c in platforms_in_cmds)

    def test_crawl_only_mode_schedules_deferred_cleanup(self):
        """只入库模式时，self._deferred_cleanup 应包含 crawler 阶段的清理任务。"""
        shell_calls, spawn_calls = [], []
        cfg = _cfg(crawler_storage_mode="只入库")
        runner = _make_runner(cfg, shell_calls, spawn_calls)
        with patch(f"{_MOD}.has_raw_data", return_value=False), \
             patch(f"{_MOD}._sync_core", return_value=(0, [])):
            runner.run_crawl_stage()
        assert ("crawler", "bili") in runner._deferred_cleanup


class TestFilterStage:

    def _run_filter(self, cfg, *, has_data=False):
        shell_calls: list = []
        runner = _make_runner(cfg, shell_calls, [])
        with patch(f"{_MOD}.has_filtered_data", return_value=has_data), \
             patch(f"{_MOD}.save_variant_lexicon_for_ui"):
            runner.run_filter_stage()
        return shell_calls

    def test_filter_runs_command(self):
        """filter 阶段应为 bili 平台运行 data_filter.py。"""
        cmds = self._run_filter(_cfg())
        assert len(cmds) == 1
        cmd, cwd = cmds[0]
        assert "data_filter.py" in cmd
        assert "--platforms bili" in cmd
        assert cwd == PROCESS_DIR

    def test_filter_includes_date_range(self):
        """filter 命令应包含指定的 --start-date 和 --end-date。"""
        cmds = self._run_filter(_cfg(start_date="2025-03-01", end_date="2025-03-31"))
        cmd = cmds[0][0]
        assert "--start-date 2025-03-01" in cmd
        assert "--end-date 2025-03-31" in cmd

    def test_filter_includes_strictness(self):
        """clean_strictness 应作为 --strictness 参数传入命令。"""
        cmds = self._run_filter(_cfg(clean_strictness="严苛"))
        assert "--strictness 严苛" in cmds[0][0]

    def test_filter_local_read_mode(self):
        """从本地读 → --read-source local。"""
        cmds = self._run_filter(_cfg(filter_read_mode="从本地读"))
        assert "--read-source local" in cmds[0][0]

    def test_filter_db_read_mode(self):
        """从数据库读 → --read-source db。"""
        cmds = self._run_filter(_cfg(filter_read_mode="从数据库读"))
        assert "--read-source db" in cmds[0][0]

    def test_filter_skips_when_data_exists(self):
        """has_filtered_data=True 且不在覆盖列表时，不运行命令。"""
        cmds = self._run_filter(_cfg(overwrite_filter_plats=[]), has_data=True)
        assert cmds == []

    def test_filter_overwrite_forces_rerun(self):
        """平台在 overwrite_filter_plats 时即使数据存在也执行。"""
        shell_calls: list = []
        cfg = _cfg(overwrite_filter_plats=["bili"])
        runner = _make_runner(cfg, shell_calls, [])
        with patch(f"{_MOD}.has_filtered_data", return_value=True), \
             patch(f"{_MOD}.save_variant_lexicon_for_ui"):
            runner.run_filter_stage()
        assert len(shell_calls) == 1


class TestAiStage:

    def _run_ai(self, cfg, *, has_data=False):
        shell_calls: list = []
        runner = _make_runner(cfg, shell_calls, [])
        with patch(f"{_MOD}.has_ai_data", return_value=has_data), \
             patch(f"{_MOD}.save_prompt_template"):
            runner.run_ai_stage()
        return shell_calls

    def test_ollama_command_built_correctly(self):
        """Ollama 模式应调用 ollama_processor.py 并传入模型名。"""
        cmds = self._run_ai(_cfg(
            ai_platform="Ollama (本地离线)",
            active_model_name="qwen3:8b",
        ))
        assert len(cmds) == 1
        cmd = cmds[0][0]
        assert "ollama_processor.py" in cmd
        assert "--model" in cmd
        assert "qwen3:8b" in cmd

    def test_deepseek_command_built_correctly(self):
        """DeepSeek 模式应调用 deepseek_processor.py 并包含 --api-key。"""
        cmds = self._run_ai(_cfg(
            ai_platform="DeepSeek (云端 API)",
            active_model_name="deepseek-chat",
            ds_api_key="sk-abc123",
        ))
        assert len(cmds) == 1
        cmd = cmds[0][0]
        assert "deepseek_processor.py" in cmd
        assert "--api-key" in cmd
        assert "sk-abc123" in cmd

    def test_ai_local_read_mode(self):
        """从本地读 → --read-source local。"""
        cmds = self._run_ai(_cfg(ai_read_mode="从本地读"))
        assert "--read-source local" in cmds[0][0]

    def test_ai_db_read_mode(self):
        """从数据库读 → --read-source db。"""
        cmds = self._run_ai(_cfg(ai_read_mode="从数据库读"))
        assert "--read-source db" in cmds[0][0]

    def test_ai_max_process_passed_to_command(self):
        """max_process 参数应作为 --max-count 传入命令。"""
        cmds = self._run_ai(_cfg(max_process=200))
        assert "--max-count 200" in cmds[0][0]

    def test_ai_skips_when_data_exists(self):
        """has_ai_data=True 且不在覆盖列表时，不运行命令。"""
        cmds = self._run_ai(_cfg(overwrite_ai_plats=[]), has_data=True)
        assert cmds == []

    def test_ai_overwrite_forces_rerun(self):
        """平台在 overwrite_ai_plats 时即使数据存在也执行。"""
        shell_calls: list = []
        cfg = _cfg(overwrite_ai_plats=["bili"])
        runner = _make_runner(cfg, shell_calls, [])
        with patch(f"{_MOD}.has_ai_data", return_value=True), \
             patch(f"{_MOD}.save_prompt_template"):
            runner.run_ai_stage()
        assert len(shell_calls) == 1

    def test_deepseek_raises_without_api_key(self):
        """DeepSeek 模式且 ds_api_key 为空时应抛出 ValueError。"""
        cfg = _cfg(ai_platform="DeepSeek (云端 API)", ds_api_key="")
        shell_calls: list = []
        runner = _make_runner(cfg, shell_calls, [])
        with patch(f"{_MOD}.has_ai_data", return_value=False), \
             patch(f"{_MOD}.save_prompt_template"), \
             pytest.raises(ValueError, match="Missing API Key"):
            runner.run_ai_stage()
        assert shell_calls == []

    def test_ollama_raises_without_model_name(self):
        """Ollama 模式且 active_model_name 为空时应抛出 ValueError。"""
        cfg = _cfg(ai_platform="Ollama (本地离线)", active_model_name="  ")
        shell_calls: list = []
        runner = _make_runner(cfg, shell_calls, [])
        with patch(f"{_MOD}.has_ai_data", return_value=False), \
             patch(f"{_MOD}.save_prompt_template"), \
             pytest.raises(ValueError, match="Missing Ollama Model Name"):
            runner.run_ai_stage()
        assert shell_calls == []


class TestFullPipeline:

    def _run_full(self, cfg, *, sentinel_api_exists: bool = True):
        """
        跑 `run_full_pipeline`，外部副作用全部 patch。

        `sentinel_api_exists`：控制 `SENTINEL_API_FILE` 是否存在，用于分支「要不要 spawn API」。
        """
        from pipeline_runner import SENTINEL_API_FILE

        def _fake_exists(path: str) -> bool:
            # 合并产物与上游 JSONL 一律视为不存在 → 走完整 `_build_merged_file`
            # `SENTINEL_API_FILE` 是否存在单独分支
            if path == SENTINEL_API_FILE:
                return sentinel_api_exists
            return False

        shell_calls, spawn_calls = [], []
        runner = _make_runner(cfg, shell_calls, spawn_calls)
        with patch(f"{_MOD}.has_raw_data", return_value=False), \
             patch(f"{_MOD}.has_filtered_data", return_value=False), \
             patch(f"{_MOD}.has_ai_data", return_value=False), \
             patch(f"{_MOD}.save_variant_lexicon_for_ui"), \
             patch(f"{_MOD}.save_prompt_template"), \
             patch(f"{_MOD}._sync_core"), \
             patch(f"{_MOD}.cleanup_stage_local_files"), \
             patch(f"{_MOD}.os.path.exists", side_effect=_fake_exists), \
             patch(f"{_MOD}.requests.get", side_effect=ConnectionError), \
             patch(f"{_MOD}.os.makedirs"):
            runner.run_full_pipeline()
        return shell_calls, spawn_calls

    def test_full_pipeline_runs_three_shell_stages(self):
        """全链路执行应产生 3 条 shell 命令（爬取、清洗、AI）。"""
        cfg = _cfg(platforms=["bili"])
        shell_calls, _ = self._run_full(cfg)
        assert len(shell_calls) == 3

    def test_full_pipeline_demo_verify_runs_generator_then_ai(self):
        """验证集模式：生成脚本 + AI，不跑爬虫与清洗 shell。"""
        cfg = _cfg(platforms=["bili"], demo_verify_dataset=True)
        shell_calls, _ = self._run_full(cfg)
        assert len(shell_calls) == 2
        gen_cmd, gen_cwd = shell_calls[0]
        assert "generate_demo_verify_dataset.py" in gen_cmd
        assert "--install-to-process-data" in gen_cmd
        assert gen_cwd == ROOT_DIR
        ai_cmd = shell_calls[1][0]
        assert "ollama_processor.py" in ai_cmd or "deepseek_processor.py" in ai_cmd

    def test_full_pipeline_demo_verify_backup_flag(self):
        cfg = _cfg(
            platforms=["bili"],
            demo_verify_dataset=True,
            demo_verify_backup_filtered=True,
        )
        shell_calls, _ = self._run_full(cfg)
        assert "--backup-existing-filtered" in shell_calls[0][0]

    def test_full_pipeline_demo_verify_skips_ai_when_output_exists(self):
        """验证集第二次启动：已有 ai_extracted_channels.jsonl 时不应再调 AI（省 token）。"""
        cfg = _cfg(platforms=["bili"], demo_verify_dataset=True)
        shell_calls, _ = [], []

        def _fake_exists(path: str) -> bool:
            from pipeline_runner import SENTINEL_API_FILE
            if path == SENTINEL_API_FILE:
                return True
            return False

        runner = _make_runner(cfg, shell_calls, [])
        with patch(f"{_MOD}.has_raw_data", return_value=False), \
             patch(f"{_MOD}.has_filtered_data", return_value=False), \
             patch(f"{_MOD}.has_ai_data", return_value=True), \
             patch(f"{_MOD}.save_variant_lexicon_for_ui"), \
             patch(f"{_MOD}.save_prompt_template"), \
             patch(f"{_MOD}._sync_core"), \
             patch(f"{_MOD}.cleanup_stage_local_files"), \
             patch(f"{_MOD}.os.path.exists", side_effect=_fake_exists), \
             patch(f"{_MOD}.requests.get", side_effect=ConnectionError), \
             patch(f"{_MOD}.os.makedirs"):
            runner.run_full_pipeline()
        assert len(shell_calls) == 1
        assert "generate_demo_verify_dataset.py" in shell_calls[0][0]
        assert not any(
            "deepseek_processor.py" in c[0] or "ollama_processor.py" in c[0]
            for c in shell_calls
        )

    def test_full_pipeline_dash_only_takes_precedence_over_demo_verify(self):
        """dash_only 优先：与 demo_verify 同时 True 时不执行验证集脚本（WebUI 会拦截同时勾选）。"""
        cfg = _cfg(
            dash_only=True,
            demo_verify_dataset=True,
            dash_merge_mode=DASH_MERGE_SKIP,
            ai_platform="DeepSeek (云端 API)",
            ds_api_key="",
        )
        shell_calls, spawn_calls = [], []
        runner = _make_runner(cfg, shell_calls, spawn_calls)
        with patch(f"{_MOD}.requests.get", side_effect=ConnectionError), \
             patch(f"{_MOD}.os.makedirs"):
            runner.run_full_pipeline()
        assert shell_calls == []

    def test_full_pipeline_spawns_sentinel_api(self):
        """SENTINEL_API_FILE 存在且 API 不可达时，应通过 spawn_fn 启动 Sentinel API。"""
        cfg = _cfg(platforms=["bili"])
        _, spawn_calls = self._run_full(cfg, sentinel_api_exists=True)
        cmds = [cmd for cmd, _ in spawn_calls]
        assert any("sentinel_api" in c.lower() or "8000" in c for c in cmds), \
            f"Sentinel API 未被 spawn，实际 spawn 调用：{cmds}"

    def test_full_pipeline_always_spawns_npm(self):
        """收尾仍会 `npm run dev`；阶段四跳过与否只影响 merge，不影响 spawn 前端。"""
        for dash_merge_mode in ("同时入库和存入本地", DASH_MERGE_SKIP):
            _, spawn_calls = self._run_full(_cfg(dash_merge_mode=dash_merge_mode))
            cmds = [cmd for cmd, _ in spawn_calls]
            assert any("npm" in c for c in cmds), \
                f"dash_merge_mode={dash_merge_mode!r} 时 npm 未被 spawn，实际调用：{cmds}"

    def test_full_pipeline_dash_only_skips_upstream_shell(self):
        """dash_only 时不跑采集 / 清洗 / AI，且不触发 DeepSeek 等 shell。"""
        cfg = _cfg(dash_only=True, dash_merge_mode=DASH_MERGE_SKIP,
                    ai_platform="DeepSeek (云端 API)", ds_api_key="")
        shell_calls, spawn_calls = [], []
        runner = _make_runner(cfg, shell_calls, spawn_calls)
        with patch(f"{_MOD}.requests.get", side_effect=ConnectionError), \
             patch(f"{_MOD}.os.makedirs"):
            runner.run_full_pipeline()
        assert shell_calls == []
        cmds = [cmd for cmd, _ in spawn_calls]
        assert any("npm" in c for c in cmds), f"npm 未被 spawn：{cmds}"

    def test_full_pipeline_merge_skip_writes_no_jsonl(self):
        """`dash_merge_mode=跳过` 时 merge 阶段应提前返回，不写 JSONL 文件。"""
        open_calls = []
        cfg = _cfg(dash_merge_mode=DASH_MERGE_SKIP)
        shell_calls, spawn_calls = [], []
        runner = _make_runner(cfg, shell_calls, spawn_calls)

        real_open = open
        def tracking_open(path, mode="r", **kw):
            if "extracted_channels.jsonl" in str(path) and "w" in mode:
                open_calls.append(path)
            return real_open(path, mode, **kw)

        with patch(f"{_MOD}.has_raw_data", return_value=False), \
             patch(f"{_MOD}.has_filtered_data", return_value=False), \
             patch(f"{_MOD}.has_ai_data", return_value=False), \
             patch(f"{_MOD}.save_variant_lexicon_for_ui"), \
             patch(f"{_MOD}.save_prompt_template"), \
             patch(f"{_MOD}._sync_core"), \
             patch(f"{_MOD}.cleanup_stage_local_files"), \
             patch(f"{_MOD}.os.path.exists", return_value=False), \
             patch(f"{_MOD}.requests.get", side_effect=ConnectionError), \
             patch(f"{_MOD}.os.makedirs"), \
             patch("builtins.open", side_effect=tracking_open):
            runner.run_full_pipeline()
        assert open_calls == [], "阶段四跳过时不应写入 extracted_channels.jsonl"

    def test_merge_mongo_only_does_not_open_jsonl_for_write(self, tmp_path):
        """「只入库」重建合并时应只组装 Mongo 行，不写 public/extracted_channels.jsonl。"""
        proc_root = tmp_path / "ProcessCdata"
        jdir = proc_root / "data" / "bili" / "jsonl"
        jdir.mkdir(parents=True)
        rec = {
            "video_title": "x",
            "source_url": "https://example.com/a",
            "original_content": "c",
            "platform": "微信",
            "merchant": "m",
            "AI_analysis": "risk",
        }
        (jdir / "ai_extracted_channels.jsonl").write_text(
            json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8",
        )

        open_calls = []
        cfg = _cfg(platforms=["bili"], dash_merge_mode="只入库")
        shell_calls, spawn_calls = [], []
        runner = _make_runner(cfg, shell_calls, spawn_calls)

        real_open = open

        def tracking_open(path, mode="r", **kw):
            if "extracted_channels.jsonl" in str(path) and "w" in mode:
                open_calls.append((path, mode))
            return real_open(path, mode, **kw)

        dash_root = tmp_path / "SentinelDashboard"
        with patch(f"{_MOD}.PROCESS_DIR", str(proc_root)), \
             patch(f"{_MOD}.DASHBOARD_DIR", str(dash_root)), \
             patch.object(runner, "_persist_leads_to_mongo"), \
             patch(f"{_MOD}.os.makedirs"), \
             patch("builtins.open", side_effect=tracking_open):
            runner.run_merge_stage()
        assert open_calls == [], "只入库模式不应以写模式打开 extracted_channels.jsonl"

    def test_full_pipeline_no_real_subprocesses(self):
        """全链路测试期间不应有任何真实子进程被创建。"""
        import subprocess as _sp
        cfg = _cfg(platforms=["bili"])
        with patch.object(_sp, "Popen") as mock_popen:
            self._run_full(cfg)
        mock_popen.assert_not_called()

    def test_full_pipeline_no_real_sleep(self):
        """全链路测试期间不应调用真实 time.sleep。"""
        import time as _time
        cfg = _cfg(platforms=["bili"])
        sleep_calls = []
        shell_calls, spawn_calls = [], []
        runner = PipelineRunner(
            config=cfg,
            log_fn=lambda msg: None,
            toast_fn=lambda msg, **_: None,
            progress_fn=lambda pct, text="": None,
            shell_fn=lambda cmd, cwd: (shell_calls.append((cmd, cwd)), 0)[1],
            spawn_fn=lambda cmd, cwd: spawn_calls.append((cmd, cwd)),
            sleep_fn=lambda secs: sleep_calls.append(secs),
        )
        with patch(f"{_MOD}.has_raw_data", return_value=False), \
             patch(f"{_MOD}.has_filtered_data", return_value=False), \
             patch(f"{_MOD}.has_ai_data", return_value=False), \
             patch(f"{_MOD}.save_variant_lexicon_for_ui"), \
             patch(f"{_MOD}.save_prompt_template"), \
             patch(f"{_MOD}._sync_core"), \
             patch(f"{_MOD}.cleanup_stage_local_files"), \
             patch(f"{_MOD}.os.path.exists", return_value=False), \
             patch(f"{_MOD}.requests.get", side_effect=ConnectionError), \
             patch(f"{_MOD}.os.makedirs"):
            runner.run_full_pipeline()
        assert len(sleep_calls) > 0, "sleep_fn 应被调用但未记录到任何调用"
        with patch.object(_time, "sleep") as mock_sleep:
            mock_sleep.assert_not_called()
