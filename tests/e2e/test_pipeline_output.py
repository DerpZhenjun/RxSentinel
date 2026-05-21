"""
E2E（第一层）：清洗 JSONL → `run_platform_pipeline`（`call_llm` mock）→ 输出 JSONL。

无 Mongo、无真模型；fixtures 见 `tests/fixtures/`。
断言：`source_platform`、`source_url`、`video_title` 映射、无效交易过滤、哔哩 avid 路由等。
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# conftest 已挂 ProcessCdata
import ai_processor_common as apc

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
BILI_FIXTURE = FIXTURES_DIR / "bili_filtered_comments.jsonl"
XHS_FIXTURE = FIXTURES_DIR / "xhs_filtered_comments.jsonl"

PROMPT_TEMPLATE = "{video_title}\n{author}\n{parent_comment}\n{comment_text}"
ENGINE = "MockLLM"
MODEL = "mock-model-v1"


def _valid_trade_response(platform="闲鱼", merchant="闲鱼搜补"):
    """`is_valid_trade=True` 的标准返回。"""
    return {
        "original_content": "测试原文",
        "is_valid_trade": True,
        "platform": platform,
        "merchant": merchant,
        "AI_analysis": "通过闲鱼搜索关键词购买",
        "confidence_score": 9,
    }


def _invalid_trade_response():
    """无效交易：流水线应丢弃该行输出。"""
    return {
        "original_content": "今天天气真好",
        "is_valid_trade": False,
        "platform": "无",
        "merchant": "无",
        "AI_analysis": "无交易迹象",
        "confidence_score": 1,
    }


def _read_fixture(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def _run_pipeline(platform: str, input_lines: list[str], call_llm_fn) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = os.path.join(tmpdir, "ai_extracted_channels.jsonl")
        chart_file = os.path.join(tmpdir, "chart.png")
        log_file = os.path.join(tmpdir, "pipeline.log")

        apc.run_platform_pipeline(
            platform=platform,
            input_lines=input_lines,
            output_file=output_file,
            chart_output_file=chart_file,
            log_file=log_file,
            prompt_template=PROMPT_TEMPLATE,
            engine=ENGINE,
            model_name=MODEL,
            call_llm=call_llm_fn,
            delay=0,  # 单测不设节流
        )

        if not os.path.exists(output_file):
            return []
        with open(output_file, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]


class TestBiliBasicFields:
    """验证 B 站管道输出的基础字段。"""

    def _make_llm(self, responses: list[dict]):
        """按序耗尽 `responses` 后退回无效模板，防迭代失控。"""
        it = iter(responses)
        def call_llm(_prompt):
            try:
                return next(it)
            except StopIteration:
                return _invalid_trade_response()
        return call_llm

    def test_source_platform_is_bili(self):
        """所有命中的 lead 必须有 source_platform='bili'。"""
        lines = _read_fixture(BILI_FIXTURE)
        call_llm = self._make_llm([_valid_trade_response()] * len(lines))
        leads = _run_pipeline("bili", lines, call_llm)
        assert len(leads) > 0
        for lead in leads:
            assert lead["source_platform"] == "bili", \
                f"source_platform 期望 'bili'，实际 {lead['source_platform']!r}"

    def test_video_title_mapped_from_injected(self):
        """video_title 必须来自输入行的 injected_video_title 字段。"""
        line = json.dumps({
            "content": "闲鱼买的",
            "injected_video_title": "HRT用药经验分享",
            "bvid": "BV1GJ411x7h7",
            "video_id": "123456789",
            "nickname": "小明",
            "user_id": "100001",
        })
        leads = _run_pipeline("bili", [line], lambda _: _valid_trade_response())
        assert len(leads) == 1
        assert leads[0]["video_title"] == "HRT用药经验分享"

    def test_all_required_fields_present(self):
        """每条 lead 必须包含所有必要字段。"""
        required = {
            "source_platform", "video_title", "source_url",
            "original_content", "thread_parent_content", "platform", "merchant", "AI_analysis",
        }
        lines = _read_fixture(BILI_FIXTURE)[:1]
        leads = _run_pipeline("bili", lines, lambda _: _valid_trade_response())
        assert len(leads) == 1
        missing = required - set(leads[0].keys())
        assert not missing, f"缺少字段: {missing}"


class TestBiliSourceUrl:
    """验证各种 B 站 ID 组合下的 source_url 构造。"""

    def _single_lead(self, comment_data: dict) -> dict | None:
        line = json.dumps(comment_data)
        leads = _run_pipeline("bili", [line], lambda _: _valid_trade_response())
        return leads[0] if leads else None

    def test_bvid_constructs_bv_url(self):
        """有效 bvid 应构造 /video/BV... 格式 URL。"""
        lead = self._single_lead({
            "content": "闲鱼有",
            "injected_video_title": "测试",
            "bvid": "BV1GJ411x7h7",
            "video_id": "123456789",
            "nickname": "用户", "user_id": "1",
        })
        assert lead is not None
        assert lead["source_url"] == "https://www.bilibili.com/video/BV1GJ411x7h7"

    def test_bvid_has_priority_over_video_id(self):
        """同时有 bvid 和 video_id 时，bvid 优先。"""
        lead = self._single_lead({
            "content": "私我",
            "injected_video_title": "测试",
            "bvid": "BV1xy4y167Au",
            "video_id": "960904835",
            "nickname": "用户", "user_id": "2",
        })
        assert lead is not None
        assert "BV1xy4y167Au" in lead["source_url"]
        assert "960904835" not in lead["source_url"]

    def test_no_bvid_falls_back_to_av_url(self):
        """没有 bvid 时，用 video_id 构造 /video/av... URL。"""
        lead = self._single_lead({
            "content": "拼多多上有",
            "injected_video_title": "测试",
            "video_id": "960904835",
            "nickname": "用户", "user_id": "3",
        })
        assert lead is not None
        assert lead["source_url"] == "https://www.bilibili.com/video/av960904835"

    def test_15digit_avid_goes_to_www_not_t_bilibili(self):
        """15 位 avid 必须路由到 www.bilibili.com/video/av，不能是 t.bilibili.com。"""
        lead = self._single_lead({
            "content": "闲鱼买",
            "injected_video_title": "测试",
            "video_id": "116430322276178",
            "nickname": "用户", "user_id": "4",
        })
        assert lead is not None
        assert "t.bilibili.com" not in lead["source_url"], \
            f"15 位 avid 不应路由到 t.bilibili.com，实际: {lead['source_url']}"
        assert "www.bilibili.com/video/av116430322276178" in lead["source_url"]

    def test_invalid_bvid_format_rejected(self):
        """bvid 不以 'BV' 开头时应视为无效，回退到 video_id。"""
        lead = self._single_lead({
            "content": "有货",
            "injected_video_title": "测试",
            "bvid": "not_a_bvid",
            "video_id": "123456789",
            "nickname": "用户", "user_id": "5",
        })
        assert lead is not None
        assert "av123456789" in lead["source_url"]

    def test_empty_url_when_no_valid_id(self):
        """没有有效 ID 时，source_url 应为空字符串（lead 不会被过滤，仍然输出）。"""
        lead = self._single_lead({
            "content": "有货",
            "injected_video_title": "测试",
            "bvid": "",
            "video_id": "",
            "nickname": "用户", "user_id": "6",
        })
        assert lead is not None
        assert lead["source_url"] == ""


class TestFilterLogic:
    """验证无效记录不进入输出。"""

    def test_invalid_trade_not_in_output(self):
        """is_valid_trade=False 的记录不应出现在输出中。"""
        line = json.dumps({
            "content": "今天天气真好",
            "injected_video_title": "日常vlog",
            "bvid": "BV1xx411c7mD", "video_id": "111222333",
            "nickname": "路人甲", "user_id": "3",
        })
        leads = _run_pipeline("bili", [line], lambda _: _invalid_trade_response())
        assert len(leads) == 0, "is_valid_trade=False 的记录不应出现在输出中"

    def test_platform_wu_not_in_output(self):
        """platform='无' 的记录不应出现在输出中（即使 is_valid_trade=True）。"""
        response = _valid_trade_response()
        response["platform"] = "无"
        line = json.dumps({
            "content": "随便说说", "injected_video_title": "测试",
            "bvid": "BV1GJ411x7h7", "video_id": "1",
            "nickname": "用户", "user_id": "1",
        })
        leads = _run_pipeline("bili", [line], lambda _: response)
        assert len(leads) == 0, "platform='无' 的 lead 不应出现在输出中"

    def test_empty_content_skipped(self):
        """content 为空的行应被跳过，不进入 AI 处理。"""
        calls = []
        def tracking_llm(_prompt):
            calls.append(_prompt)
            return _valid_trade_response()

        line = json.dumps({"content": "", "injected_video_title": "测试",
                           "bvid": "BV1GJ411x7h7", "nickname": "用户", "user_id": "1"})
        _run_pipeline("bili", [line], tracking_llm)
        assert len(calls) == 0, "空 content 不应触发 LLM 调用"

    def test_mixed_valid_invalid_only_valid_in_output(self):
        """混合输入中，只有命中的记录出现在输出。"""
        lines = _read_fixture(BILI_FIXTURE)  # 4 行：行1,2,4 预期命中，行3 日常内容

        responses = [
            _valid_trade_response("闲鱼", "闲鱼搜补"),   # 行1: 闲鱼买
            _valid_trade_response("本站私信", "【个人引流】药师小王"),  # 行2: 私我
            _invalid_trade_response(),                    # 行3: 今天天气真好
            _valid_trade_response("拼多多", "拼多多官方"),  # 行4: 拼多多上有
        ]
        it = iter(responses)
        def seq_llm(_): return next(it)

        leads = _run_pipeline("bili", lines, seq_llm)
        assert len(leads) == 3, f"期望 3 条命中，实际 {len(leads)} 条"


class TestXhsPipeline:
    """验证非 B 站平台管道的基础正确性。"""

    def test_source_platform_is_xhs(self):
        """小红书管道输出的 source_platform 应为 'xhs'。"""
        lines = _read_fixture(XHS_FIXTURE)
        it = iter([_valid_trade_response("闲鱼", "搜补"), _invalid_trade_response()])
        leads = _run_pipeline("xhs", lines, lambda _: next(it))
        assert len(leads) == 1
        assert leads[0]["source_platform"] == "xhs"

    def test_xhs_source_url_format(self):
        """小红书 source_url 应包含 xiaohongshu.com/explore/<note_id>。"""
        line = json.dumps({
            "content": "闲鱼有货",
            "injected_video_title": "HRT记录",
            "note_id": "64a1b2c3d4e5f6a7b8c9d0e1",
            "nickname": "用户", "user_id": "200001",
        })
        leads = _run_pipeline("xhs", [line], lambda _: _valid_trade_response())
        assert len(leads) == 1
        assert leads[0]["source_url"] == \
            "https://www.xiaohongshu.com/explore/64a1b2c3d4e5f6a7b8c9d0e1"


class TestPipelineIdempotency:
    def test_same_input_produces_same_output(self):
        """相同输入两次调用管道，输出内容应完全一致。"""
        line = json.dumps({
            "content": "闲鱼买的",
            "injected_video_title": "HRT记录",
            "bvid": "BV1GJ411x7h7", "video_id": "123456789",
            "nickname": "小明", "user_id": "100001",
        })

        def fixed_llm(_): return _valid_trade_response("闲鱼", "固定商家")

        leads_1 = _run_pipeline("bili", [line], fixed_llm)
        leads_2 = _run_pipeline("bili", [line], fixed_llm)

        assert len(leads_1) == len(leads_2) == 1
        for key in ("source_platform", "source_url", "video_title", "platform", "merchant"):
            assert leads_1[0][key] == leads_2[0][key], \
                f"字段 {key!r} 在两次运行间不一致"
