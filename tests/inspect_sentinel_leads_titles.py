"""一次性检查 sentinel_leads 中标题相关字段分布（用于排查大屏「标题未收录」）。

用法（仓库根目录）：
    python tests/inspect_sentinel_leads_titles.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

URI = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
DB_NAME = os.getenv("MONGODB_DB", "Oestrogen")
COLLECTION = os.getenv("MONGODB_COLLECTION", "sentinel_leads")


def nonempty(s: object) -> bool:
    return bool(s is not None and str(s).strip())


def main() -> None:
    client = MongoClient(URI, serverSelectionTimeoutMS=8000)
    col = client[DB_NAME][COLLECTION]
    total = col.estimated_document_count()
    print(f"URI={URI}")
    print(f"DB={DB_NAME} collection={COLLECTION} approx_docs={total}\n")

    n_vt = col.count_documents({"video_title": {"$regex": r"\S"}})
    n_inj = col.count_documents({"injected_video_title": {"$regex": r"\S"}})
    n_title = col.count_documents({"title": {"$regex": r"\S"}})
    n_any = col.count_documents({
        "$or": [
            {"video_title": {"$regex": r"\S"}},
            {"injected_video_title": {"$regex": r"\S"}},
            {"title": {"$regex": r"\S"}},
        ]
    })

    print("非空字段计数（简单正则 \\S）：")
    print(f"  video_title          : {n_vt}")
    print(f"  injected_video_title : {n_inj}")
    print(f"  title                : {n_title}")
    print(f"  任一路非空            : {n_any}")

    print("\n--- 最新 5 条（含标题相关键）---")
    cur = col.find().sort("ingested_at", -1).limit(5)
    for d in cur:
        doc = {
            "_id": str(d.get("_id")),
            "video_title": d.get("video_title", ""),
            "injected_video_title": d.get("injected_video_title", ""),
            "title": d.get("title", ""),
            "source_url": (d.get("source_url") or "")[:80],
            "platform": d.get("platform", ""),
        }
        print(json.dumps(doc, ensure_ascii=False))


if __name__ == "__main__":
    main()
