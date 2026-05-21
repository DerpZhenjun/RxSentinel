"""清洗行 → 落地 URL、楼中楼父评解析（无 matplotlib / Mongo 依赖）。

由 `ai_processor_common` 导入，避免在仅需 URL/线程工具的场景里拉起 matplotlib 等重型依赖。"""

from collections import defaultdict


def first_landing_url_from_row(data: dict) -> str:
    """爬虫/清洗行里已带作品落地链时优先使用（贴吧 `note_url`、知乎 `content_url` 等）。"""
    for key in ("content_url", "note_url", "aweme_url", "video_url", "source_url"):
        v = data.get(key)
        if v is None:
            continue
        s = str(v).strip().split()[0] if str(v).strip() else ""
        if s.startswith(("http://", "https://")):
            return s
    return ""


def build_source_url(platform: str, item_id: str, row: dict | None = None) -> str:
    """由平台 + 主键拼装规范落地页；知乎需 `row` 携带 `content_type`。"""
    if not item_id:
        return ""
    p = str(platform or "").strip().lower()

    if p == "bili":
        if item_id.startswith("BV") or item_id.startswith("av"):
            return f"https://www.bilibili.com/video/{item_id}"
        if item_id.isdigit():
            return f"https://www.bilibili.com/video/av{item_id}"
        return f"https://www.bilibili.com/video/{item_id}"
    if p in ("dy", "douyin"):
        return f"https://www.douyin.com/video/{item_id}"
    if p == "xhs":
        return f"https://www.xiaohongshu.com/explore/{item_id}"
    if p in ("wb", "weibo"):
        return f"https://weibo.com/detail/{item_id}"
    if p in ("ks", "kuaishou"):
        return f"https://www.kuaishou.com/short-video/{item_id}"
    if p == "tieba":
        return f"https://tieba.baidu.com/p/{item_id}"
    if p == "zhihu":
        row = row or {}
        ct = str(row.get("content_type") or "").strip().lower()
        cid = str(item_id).strip()
        if ct == "article":
            return f"https://zhuanlan.zhihu.com/p/{cid}"
        if ct in ("zvideo", "video"):
            return f"https://www.zhihu.com/zvideo/{cid}"
        return f"https://www.zhihu.com/answer/{cid}"
    return ""


def resolve_source_url(platform: str, data: dict) -> str:
    """清洗行 → 大屏/入库用落地链：先取行内 URL，再按平台 + 主键拼装。"""
    direct = first_landing_url_from_row(data)
    if direct:
        return direct
    item_id = extract_item_id(data, platform)
    if item_id:
        return build_source_url(platform, item_id, data)
    return ""


def extract_item_id(data: dict, platform: str) -> str:
    if platform == "bili":
        bvid = str(data.get("bvid") or "").strip()
        if bvid.startswith("BV") and len(bvid) >= 10:
            return bvid
        video_id = str(data.get("video_id") or "").strip()
        if video_id.isdigit() and int(video_id) > 0:
            return video_id
        return ""
    return str(
        data.get("note_id")
        or data.get("aweme_id")
        or data.get("bvid")
        or data.get("video_id")
        or data.get("photo_id")
        or data.get("mid")
        or data.get("content_id")
        or ""
    ).strip()


def thread_scope_key(platform: str, row: dict) -> str:
    """同一稿件/帖子下的线程键，用于在同一批数据内解析 parent_comment_id。"""
    p = (platform or "").strip().lower()
    if p == "bili":
        bv = str(row.get("bvid") or "").strip()
        if bv.startswith("BV") and len(bv) >= 10:
            return f"bili:{bv}"
        vid = str(row.get("video_id") or "").strip()
        if vid.isdigit() and int(vid) > 0:
            return f"bili:{vid}"
        return "bili:"
    if p == "xhs":
        return f"xhs:{str(row.get('note_id') or '').strip()}"
    if p in ("dy", "douyin"):
        return f"dy:{str(row.get('aweme_id') or '').strip()}"
    if p in ("wb", "weibo"):
        return f"wb:{str(row.get('note_id') or '').strip()}"
    if p == "tieba":
        return f"tieba:{str(row.get('note_id') or '').strip()}"
    if p == "zhihu":
        cid = str(row.get("content_id") or row.get("note_id") or "").strip()
        ct = str(row.get("content_type") or "").strip()
        return f"zhihu:{ct}:{cid}"
    if p in ("ks", "kuaishou"):
        return f"ks:{str(row.get('photo_id') or '').strip()}"
    return f"{p}:global"


def enrich_rows_with_parent_comments(rows: list[dict], platform: str) -> None:
    """就地写入 thread_parent_content：依赖同一批 JSONL / Mongo 回放内有父评论行。"""
    by_scope: dict[str, dict[str, str]] = defaultdict(dict)
    for row in rows:
        if not isinstance(row, dict):
            continue
        scope = thread_scope_key(platform, row)
        cid = str(row.get("comment_id") or "").strip()
        text = str(row.get("content") or row.get("original_content") or "").strip()
        if cid and text:
            by_scope[scope][cid] = text
    for row in rows:
        if not isinstance(row, dict):
            continue
        scope = thread_scope_key(platform, row)
        pid = str(row.get("parent_comment_id") or "").strip()
        if not pid or pid == "0":
            row["thread_parent_content"] = ""
            continue
        row["thread_parent_content"] = by_scope[scope].get(pid, "")
