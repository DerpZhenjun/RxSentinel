"""data_filter：normalize / detect_keywords / 谐音语境隔离（全局模块 monkeypatch）。"""
import sys
from pathlib import Path

import data_filter as df


class TestNormalizeForDetection:
    def test_lowercase(self):
        assert df.normalize_for_detection("VX") == "vx"

    def test_strips_punctuation_and_spaces(self):
        assert df.normalize_for_detection("v . x") == "vx"

    def test_strips_separators_tang(self):
        # OBFUSCATION_REGEX_RULES：`t-a-n-g` → 糖
        result = df.normalize_for_detection("t-a-n-g")
        assert "糖" in result

    def test_obfuscation_regex_tang(self):
        # `t.a.n.g` → 糖
        result = df.normalize_for_detection("t.a.n.g")
        assert "糖" in result

    def test_obfuscation_regex_vx(self):
        result = df.normalize_for_detection("v.x")
        assert "vx" in result

    def test_chinese_preserved(self):
        result = df.normalize_for_detection("糖尿病")
        assert "糖尿病" in result

    def test_empty_string(self):
        assert df.normalize_for_detection("") == ""

    def test_pure_punctuation(self):
        assert df.normalize_for_detection("!@#$%") == ""


class TestBuildNormalizedKeywords:
    def test_basic(self):
        pairs = df.build_normalized_keywords(["VX", "tg"])
        originals = [p[0] for p in pairs]
        assert "VX" in originals
        assert "tg" in originals

    def test_empty_word_excluded(self):
        pairs = df.build_normalized_keywords(["!!", "闲鱼"])
        originals = [p[0] for p in pairs]
        assert "!!" not in originals
        assert "闲鱼" in originals


class TestDetectKeywords:
    def setup_method(self):
        self.channels = df.build_normalized_keywords(["闲鱼", "vx", "tg"])
        self.drugs = df.build_normalized_keywords(["补佳乐", "雌二醇"])
        # 测试期清空全局语境/谐音，避免与其他用例耦合
        self._orig_hints = df.TRADE_CONTEXT_HINTS
        self._orig_homo = df.HOMOPHONE_VARIANTS
        df.TRADE_CONTEXT_HINTS = []
        df.HOMOPHONE_VARIANTS = {}

    def teardown_method(self):
        df.TRADE_CONTEXT_HINTS = self._orig_hints
        df.HOMOPHONE_VARIANTS = self._orig_homo

    def test_channel_hit(self):
        channels, drugs = df.detect_keywords("可以去闲鱼买", self.channels, self.drugs)
        assert "闲鱼" in channels
        assert drugs == []

    def test_drug_hit(self):
        channels, drugs = df.detect_keywords("我在吃补佳乐", self.channels, self.drugs)
        assert "补佳乐" in drugs
        assert channels == []

    def test_no_hit(self):
        channels, drugs = df.detect_keywords("今天天气不错", self.channels, self.drugs)
        assert channels == []
        assert drugs == []

    def test_obfuscated_vx(self):
        channels, drugs = df.detect_keywords("联系方式：v.x", self.channels, self.drugs)
        assert "vx" in channels

    def test_obfuscated_tg(self):
        channels, drugs = df.detect_keywords("加我t.g", self.channels, self.drugs)
        assert "tg" in channels

    def test_multiple_hits(self):
        channels, drugs = df.detect_keywords("闲鱼私聊 要雌二醇", self.channels, self.drugs)
        assert "闲鱼" in channels
        assert "雌二醇" in drugs


class TestHomophoneContextMatching:
    def setup_method(self):
        # 最小谐音表 + 语境词，专注「语境闸」分支
        self._orig_hints = df.TRADE_CONTEXT_HINTS
        self._orig_homo = df.HOMOPHONE_VARIANTS
        df.TRADE_CONTEXT_HINTS = ["私信", "联系"]
        df.HOMOPHONE_VARIANTS = {"糖": "补佳乐"}  # 「糖」映射到药品 canonical

    def teardown_method(self):
        df.TRADE_CONTEXT_HINTS = self._orig_hints
        df.HOMOPHONE_VARIANTS = self._orig_homo

    def test_homophone_triggered_by_context(self):
        drugs = df.build_normalized_keywords(["补佳乐"])
        channels = df.build_normalized_keywords([])
        _, matched_drugs = df.detect_keywords("私信我买糖", channels, drugs)
        assert "补佳乐" in matched_drugs

    def test_homophone_NOT_triggered_without_context(self):
        drugs = df.build_normalized_keywords(["补佳乐"])
        channels = df.build_normalized_keywords([])
        _, matched_drugs = df.detect_keywords("想吃点糖", channels, drugs)
        # 无语境命中 → 谐音扩展不点火
        assert "补佳乐" not in matched_drugs
