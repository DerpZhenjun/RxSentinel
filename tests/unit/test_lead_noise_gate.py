"""lead_noise_gate：空话 / 楼中楼双承接硬闸。"""

from lead_noise_gate import is_obvious_noise_lead, should_suppress_lead


def _ai(ok: bool, text: str, merchant: str = "无") -> dict:
    return {
        "is_valid_trade": ok,
        "original_content": text,
        "merchant": merchant,
        "AI_analysis": "测",
    }


def test_obvious_parent_private_me_child_invite():
    assert is_obvious_noise_lead("拉我，我也想进群😭", "私我") is True


def test_obvious_parent_private_me_child_dm_ack():
    """父：私我 → 子：私聊你了（无交易实质）。"""
    assert is_obvious_noise_lead("私聊你了", "私我") is True
    row = {"content": "私聊你了", "thread_parent_content": "私我"}
    assert should_suppress_lead(row, _ai(True, row["content"])) is True


def test_suppress_private_me_chain():
    row = {"content": "拉我，我也想进群😭", "thread_parent_content": "私我"}
    assert should_suppress_lead(row, _ai(True, row["content"])) is True


def test_suppress_both_invite_noise():
    assert is_obvious_noise_lead("还有群吗", "拉我进群") is True


def test_keep_when_actionable_shop():
    row = {"content": "闲鱼搜糖舱店铺现货", "thread_parent_content": "私我"}
    assert should_suppress_lead(row, _ai(True, row["content"], "糖舱")) is False
    assert is_obvious_noise_lead(row["content"], row["thread_parent_content"]) is False


def test_suppress_otc_pointer():
    row = {"content": "PDD上买国产仿制的就行挺便宜", "thread_parent_content": ""}
    assert should_suppress_lead(row, _ai(True, row["content"])) is True


def test_invalid_not_suppressed():
    row = {"content": "私我", "thread_parent_content": ""}
    assert should_suppress_lead(row, _ai(False, "私我")) is False


def test_obvious_false_for_sugarlane_demo():
    """演示数据含 SugarLane，属可检索线索，不得当废话删。"""
    t = "vx：SugarLane2026，说是贴吧来的给批发价"
    assert is_obvious_noise_lead(t, "") is False


def test_keep_when_private_me_is_substring_not_solo_chaff():
    """含「私我」但整句有实质，不是「仅私我+拉群」类承接。"""
    t = "想买保法止非那雄胺的话私我详聊，别进那些群"
    assert is_obvious_noise_lead(t, "") is False
    assert is_obvious_noise_lead(t, "同问") is False


def test_keep_parent_private_me_child_substantive():
    assert is_obvious_noise_lead("私我详聊走闲鱼面交", "私我") is False
