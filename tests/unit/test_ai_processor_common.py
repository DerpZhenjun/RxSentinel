"""ai_processor_common：`build_source_url` / `extract_item_id` 跨平台回归。"""
import ai_processor_common as apc


class TestBuildSourceUrlBili:
    def test_bv_id(self):
        assert apc.build_source_url("bili", "BV1GJ411x7h7") == \
            "https://www.bilibili.com/video/BV1GJ411x7h7"

    def test_av_prefix(self):
        assert apc.build_source_url("bili", "av960904835") == \
            "https://www.bilibili.com/video/av960904835"

    def test_short_numeric_avid(self):
        url = apc.build_source_url("bili", "960904835")
        assert url == "https://www.bilibili.com/video/av960904835"

    def test_15_digit_avid_not_routed_to_t_bilibili(self):
        """15 位 avid：必须落成 www 稿件页，禁止误判动态域名。"""
        url = apc.build_source_url("bili", "116430322276178")
        assert url == "https://www.bilibili.com/video/av116430322276178"
        assert "t.bilibili.com" not in url

    def test_empty_item_id(self):
        assert apc.build_source_url("bili", "") == ""

    def test_none_item_id(self):
        # `if not item_id` 短路
        assert apc.build_source_url("bili", None) == ""  # type: ignore[arg-type]


class TestBuildSourceUrlOtherPlatforms:
    def test_douyin(self):
        assert apc.build_source_url("dy", "7123456789") == \
            "https://www.douyin.com/video/7123456789"

    def test_xhs(self):
        assert apc.build_source_url("xhs", "abcdef123456") == \
            "https://www.xiaohongshu.com/explore/abcdef123456"

    def test_weibo(self):
        assert apc.build_source_url("wb", "5001234567") == \
            "https://weibo.com/detail/5001234567"

    def test_unknown_platform_returns_empty(self):
        assert apc.build_source_url("unknown_platform", "12345") == ""


class TestExtractItemIdBili:
    def test_valid_bvid_returned(self):
        data = {"bvid": "BV1GJ411x7h7", "video_id": "123456789"}
        assert apc.extract_item_id(data, "bili") == "BV1GJ411x7h7"

    def test_bvid_priority_over_video_id(self):
        data = {"bvid": "BV1xy4y167Au", "video_id": "999999999"}
        result = apc.extract_item_id(data, "bili")
        assert result == "BV1xy4y167Au"

    def test_invalid_bvid_falls_back_to_video_id(self):
        """`bvid` 非法时退回数字 `video_id`。"""
        data = {"bvid": "not_a_bvid", "video_id": "960904835"}
        assert apc.extract_item_id(data, "bili") == "960904835"

    def test_short_bvid_rejected(self):
        """`'BV'` 前缀但总长不足规范 → 视为无效 BV。"""
        data = {"bvid": "BV123", "video_id": "960904835"}
        assert apc.extract_item_id(data, "bili") == "960904835"

    def test_non_digit_video_id_rejected(self):
        """`video_id` 混入字母 → 整条丢弃。"""
        data = {"bvid": "", "video_id": "abc123"}
        assert apc.extract_item_id(data, "bili") == ""

    def test_zero_video_id_rejected(self):
        data = {"bvid": "", "video_id": "0"}
        assert apc.extract_item_id(data, "bili") == ""

    def test_both_empty_returns_empty(self):
        data = {"bvid": "", "video_id": ""}
        assert apc.extract_item_id(data, "bili") == ""

    def test_missing_keys_returns_empty(self):
        assert apc.extract_item_id({}, "bili") == ""

    def test_15_digit_avid_accepted(self):
        """15 位 avid 必须被接受（不能因位数多而被拒绝）"""
        data = {"bvid": "", "video_id": "116430322276178"}
        assert apc.extract_item_id(data, "bili") == "116430322276178"


class TestExtractItemIdOtherPlatforms:
    def test_xhs_note_id(self):
        data = {"note_id": "6543abc", "bvid": "BV1GJ411x7h7"}
        # 小红书：`note_id` 优先于误入的 `bvid`
        assert apc.extract_item_id(data, "xhs") == "6543abc"

    def test_douyin_aweme_id(self):
        data = {"aweme_id": "7123456789012345678"}
        assert apc.extract_item_id(data, "dy") == "7123456789012345678"

    def test_empty_data_returns_empty(self):
        assert apc.extract_item_id({}, "xhs") == ""
