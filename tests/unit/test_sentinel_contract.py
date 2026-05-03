"""sentinel_contract：别名、外链归一、fingerprint、`to_contract_doc` / `upgrade_existing_doc`。"""

import sys
import time
from pathlib import Path

from sentinel_contract import (
    LEAD_CONTRACT_NAME,
    LEAD_SCHEMA_VERSION,
    build_lead_fingerprint,
    normalize_bili_url,
    normalize_general_url,
    normalize_platform_name,
    normalize_source_url,
    to_contract_doc,
    upgrade_existing_doc,
)


class TestNormalizePlatformName:
    def test_twitter_aliases(self):
        for alias in ["推", "推特", "twitter", "Twitter", "TWITTER", "x", "X"]:
            assert normalize_platform_name(alias) == "推特", f"failed for: {alias!r}"

    def test_telegram_aliases(self):
        for alias in ["tg", "TG", "Tg", "telegram", "Telegram", "电报", "纸飞机"]:
            assert normalize_platform_name(alias) == "Telegram", f"failed for: {alias!r}"

    def test_wechat_aliases(self):
        for alias in ["微信", "绿泡", "绿泡泡", "vx", "VX", "Vx", "v", "V"]:
            assert normalize_platform_name(alias) == "微信", f"failed for: {alias!r}"

    def test_unknown_passes_through(self):
        assert normalize_platform_name("闲鱼") == "闲鱼"
        assert normalize_platform_name("拼多多") == "拼多多"
        assert normalize_platform_name("淘宝") == "淘宝"

    def test_empty_string_returns_wu(self):
        assert normalize_platform_name("") == "无"

    def test_none_returns_wu(self):
        assert normalize_platform_name(None) == "无"

    def test_whitespace_only_returns_wu(self):
        assert normalize_platform_name("   ") == "无"

    def test_leading_trailing_whitespace_stripped_before_match(self):
        assert normalize_platform_name("  twitter  ") == "推特"


class TestNormalizeBiliUrl:
    def test_bv_format(self):
        url = "https://www.bilibili.com/video/BV1xx411c7mD"
        assert normalize_bili_url(url) == "https://www.bilibili.com/video/BV1xx411c7mD"

    def test_bv_extracted_from_noisy_string(self):
        url = "去B站看看吧 BV1xx411c7mD 很不错"
        result = normalize_bili_url(url)
        assert "BV1xx411c7mD" in result

    def test_av_format_lowercase(self):
        result = normalize_bili_url("https://www.bilibili.com/video/av12345")
        assert result == "https://www.bilibili.com/video/av12345"

    def test_av_format_uppercase(self):
        result = normalize_bili_url("AV12345")
        assert "av12345" in result.lower()

    def test_dynamic_12digit_id(self):
        result = normalize_bili_url("123456789012")
        assert "t.bilibili.com/123456789012" in result

    def test_empty_string_returns_empty(self):
        assert normalize_bili_url("") == ""

    def test_none_returns_empty(self):
        assert normalize_bili_url(None) == ""

    def test_no_match_returns_empty(self):
        assert normalize_bili_url("some random text without IDs") == ""

    def test_short_number_not_treated_as_dynamic(self):
        # 动态号规则：≥12 位纯数字
        result = normalize_bili_url("12345")
        assert result == ""


class TestNormalizeGeneralUrl:
    def test_plain_https_url(self):
        url = "https://xianyu.taobao.com/item/12345"
        assert normalize_general_url(url) == url

    def test_plain_http_url(self):
        url = "http://example.com/path?q=1"
        assert normalize_general_url(url) == url

    def test_markdown_format_url(self):
        url = "[闲鱼链接](https://xianyu.taobao.com/item/12345)"
        assert normalize_general_url(url) == "https://xianyu.taobao.com/item/12345"

    def test_url_with_trailing_bracket_stripped(self):
        url = "https://example.com/item]"
        result = normalize_general_url(url)
        assert not result.endswith("]")

    def test_empty_string_returns_empty(self):
        assert normalize_general_url("") == ""

    def test_none_returns_empty(self):
        assert normalize_general_url(None) == ""

    def test_no_url_in_text_returns_empty(self):
        assert normalize_general_url("纯文字没有链接") == ""

    def test_multiple_urls_returns_last(self):
        text = "https://first.com 和 https://last.com"
        result = normalize_general_url(text)
        assert result == "https://last.com"

    def test_markdown_remnant_with_bracket_paren_rejected(self):
        """含有 ]( 的 URL 是 Markdown 链接残骸（avid 未填入），应被拒绝"""
        malformed = "https://www.bilibili.com/video/av](https://www.bilibili.com/video/av"
        assert normalize_general_url(malformed) == ""

    def test_url_ending_in_close_bracket_stripped(self):
        """URL 末尾的 ] 应被去除"""
        result = normalize_general_url("https://example.com/path]")
        assert result == "https://example.com/path"


class TestNormalizeBiliUrlExtra:
    def test_15digit_number_treated_as_dynamic_post(self):
        """normalize_bili_url：≥12 位纯数字一律当作动态帖 ID（无页面上下文）。"""
        result = normalize_bili_url("116430322276178")
        assert "t.bilibili.com" in result

    def test_av_url_with_15digit_avid(self):
        """带 av 前缀的长 avid 保留为稿件 URL，不误判动态域名。"""
        result = normalize_bili_url("https://www.bilibili.com/video/av116430322276178")
        assert result == "https://www.bilibili.com/video/av116430322276178"
        assert "t.bilibili.com" not in result

    def test_bv_url_passthrough(self):
        result = normalize_bili_url("https://www.bilibili.com/video/BV1GJ411x7h7")
        assert result == "https://www.bilibili.com/video/BV1GJ411x7h7"


class TestNormalizeSourceUrl:
    def test_bilibili_url_routed_correctly(self):
        url = "https://www.bilibili.com/video/BV1xx411c7mD"
        result = normalize_source_url(url)
        assert "BV1xx411c7mD" in result

    def test_general_url_passthrough(self):
        url = "https://xianyu.taobao.com/item/12345"
        assert normalize_source_url(url) == url

    def test_empty_returns_empty(self):
        assert normalize_source_url("") == ""

    def test_none_returns_empty(self):
        assert normalize_source_url(None) == ""

    def test_bv_string_without_full_url_returns_empty(self):
        # 路由条件要看 bilibili.com / 小写 bv、av；裸 `BV…` 不进哔哩分支 → 通用抽取也无 http → 空串
        result = normalize_source_url("BV1xx411c7mD")
        assert result == ""


class TestBuildLeadFingerprint:
    def test_deterministic(self):
        fp1 = build_lead_fingerprint("xhs", "http://example.com", "test content")
        fp2 = build_lead_fingerprint("xhs", "http://example.com", "test content")
        assert fp1 == fp2

    def test_different_content_gives_different_hash(self):
        fp1 = build_lead_fingerprint("xhs", "http://example.com", "content A")
        fp2 = build_lead_fingerprint("xhs", "http://example.com", "content B")
        assert fp1 != fp2

    def test_different_platform_gives_different_hash(self):
        fp1 = build_lead_fingerprint("xhs", "http://example.com", "content")
        fp2 = build_lead_fingerprint("bili", "http://example.com", "content")
        assert fp1 != fp2

    def test_returns_40char_hex_string(self):
        fp = build_lead_fingerprint("xhs", "http://example.com", "content")
        assert isinstance(fp, str)
        assert len(fp) == 40
        assert all(c in "0123456789abcdef" for c in fp)


class TestToContractDoc:
    def _raw(self, **overrides):
        base = {
            "source_platform": "xhs",
            "source_url": "https://xhs.com/note/abc123",
            "original_content": "求购补佳乐，私信我",
            "platform": "闲鱼",
            "merchant": "某某店铺",
            "AI_analysis": "存在交易暗语",
            "video_title": "HRT用药分享",
        }
        base.update(overrides)
        return base

    def test_schema_fields_injected(self):
        doc = to_contract_doc(self._raw(), now_ts=1700000000)
        assert doc["schema_version"] == LEAD_SCHEMA_VERSION
        assert doc["contract"] == LEAD_CONTRACT_NAME

    def test_ingested_at_uses_now_ts(self):
        doc = to_contract_doc(self._raw(), now_ts=1700000000)
        assert doc["ingested_at"] == 1700000000

    def test_ingested_at_default_is_current_time(self):
        before = int(time.time())
        doc = to_contract_doc(self._raw())
        after = int(time.time())
        assert before <= doc["ingested_at"] <= after

    def test_platform_normalized(self):
        doc = to_contract_doc(self._raw(platform="twitter"))
        assert doc["platform"] == "推特"

    def test_missing_source_platform_defaults_to_unknown(self):
        raw = self._raw()
        raw.pop("source_platform")
        doc = to_contract_doc(raw)
        assert doc["source_platform"] == "UNKNOWN"

    def test_empty_source_platform_defaults_to_unknown(self):
        doc = to_contract_doc(self._raw(source_platform=""))
        assert doc["source_platform"] == "UNKNOWN"

    def test_empty_merchant_defaults_to_weizhi(self):
        doc = to_contract_doc(self._raw(merchant=""))
        assert doc["merchant"] == "未指明"

    def test_none_merchant_defaults_to_weizhi(self):
        raw = self._raw()
        raw["merchant"] = None
        doc = to_contract_doc(raw)
        assert doc["merchant"] == "未指明"

    def test_empty_ai_analysis_defaults(self):
        doc = to_contract_doc(self._raw(AI_analysis=""))
        assert doc["AI_analysis"] == "暂无研判"

    def test_fingerprint_generated_deterministically(self):
        raw = self._raw()
        doc1 = to_contract_doc(raw, now_ts=1700000000)
        doc2 = to_contract_doc(raw, now_ts=1700000000)
        assert doc1["fingerprint"] == doc2["fingerprint"]

    def test_existing_fingerprint_preserved(self):
        doc = to_contract_doc(self._raw(fingerprint="my_custom_fp"))
        assert doc["fingerprint"] == "my_custom_fp"

    def test_source_url_normalized(self):
        doc = to_contract_doc(self._raw(source_url="https://www.bilibili.com/video/BV1xx411c7mD"))
        assert "BV1xx411c7mD" in doc["source_url"]

    def test_video_title_coalesces_from_injected_when_primary_missing(self):
        raw = {k: v for k, v in self._raw().items() if k != "video_title"}
        raw["injected_video_title"] = "爬取侧注入标题"
        doc = to_contract_doc(raw, now_ts=1700000000)
        assert doc["video_title"] == "爬取侧注入标题"

    def test_empty_video_title_string_still_uses_injected(self):
        doc = to_contract_doc(
            self._raw(video_title="", injected_video_title="笔记标题"),
            now_ts=1700000000,
        )
        assert doc["video_title"] == "笔记标题"

    def test_all_required_fields_present(self):
        doc = to_contract_doc(self._raw())
        required = [
            "schema_version", "contract", "fingerprint", "source_platform",
            "video_title", "source_url", "original_content", "platform",
            "merchant", "AI_analysis", "ingested_at",
        ]
        for field in required:
            assert field in doc, f"missing field: {field}"


class TestUpgradeExistingDoc:
    def _current_doc(self):
        raw = {
            "source_platform": "xhs",
            "source_url": "https://xhs.com/note/abc123",
            "original_content": "测试内容",
            "platform": "闲鱼",
            "merchant": "某某店铺",
            "AI_analysis": "测试分析",
            "video_title": "测试",
        }
        return to_contract_doc(raw, now_ts=1700000000)

    def test_already_current_doc_not_changed(self):
        doc = self._current_doc()
        _, changed = upgrade_existing_doc(doc)
        assert not changed

    def test_legacy_schema_version_triggers_change(self):
        doc = self._current_doc()
        doc["schema_version"] = "1.0.0"
        _, changed = upgrade_existing_doc(doc)
        assert changed

    def test_unnormalized_platform_triggers_change(self):
        doc = self._current_doc()
        doc["platform"] = "twitter"  # 尚未归一的别名，升级应触发改写
        _, changed = upgrade_existing_doc(doc)
        assert changed

    def test_upgrade_fixes_platform(self):
        doc = self._current_doc()
        doc["platform"] = "twitter"
        upgraded, _ = upgrade_existing_doc(doc)
        assert upgraded["platform"] == "推特"

    def test_upgrade_injects_schema_version(self):
        doc = self._current_doc()
        doc["schema_version"] = "0.9.0"
        upgraded, _ = upgrade_existing_doc(doc)
        assert upgraded["schema_version"] == LEAD_SCHEMA_VERSION

    def test_returns_tuple_of_dict_and_bool(self):
        doc = self._current_doc()
        result = upgrade_existing_doc(doc)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], dict)
        assert isinstance(result[1], bool)
