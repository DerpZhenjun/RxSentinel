"""无 Streamlit 的业务内核：阶段文件 → Mongo upsert，指纹键与集合映射收口于此。

单测 / `pipeline_runner` 直连本模块；Streamlit 只做日志转发包装。"""

import csv
import hashlib
import json
import logging
import os
import time

from pymongo import MongoClient, UpdateOne

logger = logging.getLogger(__name__)

# 阶段 → Mongo 集合；键须与 pipeline_runner `_sync` 传入的 stage 对齐。
STAGE_COLLECTION_MAP: dict[str, str] = {
    "crawler": "raw_comments",
    "filter": "filtered_comments",
    "ai": "ai_extracted_comments",
}


def build_fingerprint(stage: str, platform: str, file_path: str, line_no: int, raw_line: str) -> str:
    """行号 + 原始行字节参与哈希：同文件 replay 不重键，篡改行即新指纹。"""
    seed = f"{stage}|{platform}|{file_path}|{line_no}|{raw_line}"
    return hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()


# filter / ai：同步前先删该平台旧快照，否则「从库读」会把历次运行堆成倍数流量。
# crawler：追加语义，禁止 purge。
_STAGE_REPLACE_EXISTING = {"filter", "ai"}


def sync_stage_files_to_mongo(
    stage: str,
    platform: str,
    file_paths: list[str],
    mongo_uri: str,
    mongo_db_name: str,
) -> tuple[int, list[str]]:
    """JSONL / CSV 批量 `$set` upsert。

    filter、ai：`delete_many(stage, platform)` 后再写，免得中间集合无限叠加。
    crawler：直接 upsert。

    返回：
        `(写入操作条数, 日志文案列表)` —— 日志供上层终端打印。
    """
    if stage not in STAGE_COLLECTION_MAP:
        raise ValueError(f"Unknown stage '{stage}'. Must be one of {list(STAGE_COLLECTION_MAP)}")

    if not file_paths:
        return 0, []

    coll_name = STAGE_COLLECTION_MAP[stage]
    logger.info(
        "sync_stage_files_to_mongo: stage=%s platform=%s files=%d collection=%s",
        stage, platform, len(file_paths), coll_name,
    )

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    try:
        db = client[mongo_db_name]
        col = db[coll_name]
        col.create_index("fingerprint", unique=True)
        col.create_index("platform")
        col.create_index("stage")
        col.create_index("ingested_at")

        # filter / ai：先清空该平台中间快照，再 bulk upsert 本轮产物。
        if stage in _STAGE_REPLACE_EXISTING:
            deleted = col.delete_many({"stage": stage, "platform": platform}).deleted_count
            if deleted:
                logger.info(
                    "sync_stage_files_to_mongo: cleared %d stale docs for stage=%s platform=%s",
                    deleted, stage, platform,
                )

        ops: list[UpdateOne] = []
        now_ts = int(time.time())
        logs: list[str] = []

        for fp in file_paths:
            ext = os.path.splitext(fp)[1].lower()

            if ext == ".jsonl":
                try:
                    with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                        for idx, line in enumerate(f, start=1):
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                payload = json.loads(line)
                            except json.JSONDecodeError:
                                payload = {"_raw_line": line}
                            fp_hash = build_fingerprint(stage, platform, fp, idx, line)
                            ops.append(
                                UpdateOne(
                                    {"fingerprint": fp_hash},
                                    {"$set": {
                                        "fingerprint": fp_hash,
                                        "stage": stage,
                                        "platform": platform,
                                        "source_file": fp,
                                        "line_no": idx,
                                        "payload": payload,
                                        "ingested_at": now_ts,
                                    }},
                                    upsert=True,
                                )
                            )
                except OSError as exc:
                    logger.warning("Cannot open %s: %s", fp, exc)
                    logs.append(f"⚠️ 文件读取失败: {fp} — {exc}")
                    continue

            elif ext == ".csv":
                try:
                    with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                        reader = csv.DictReader(f)
                        for idx, row in enumerate(reader, start=1):
                            raw_line = json.dumps(row, ensure_ascii=False, sort_keys=True)
                            fp_hash = build_fingerprint(stage, platform, fp, idx, raw_line)
                            ops.append(
                                UpdateOne(
                                    {"fingerprint": fp_hash},
                                    {"$set": {
                                        "fingerprint": fp_hash,
                                        "stage": stage,
                                        "platform": platform,
                                        "source_file": fp,
                                        "line_no": idx,
                                        "payload": row,
                                        "ingested_at": now_ts,
                                    }},
                                    upsert=True,
                                )
                            )
                except OSError as exc:
                    logger.warning("Cannot open %s: %s", fp, exc)
                    logs.append(f"⚠️ 文件读取失败: {fp} — {exc}")
                    continue

        if ops:
            col.bulk_write(ops, ordered=False)
            logger.info("Upserted %d docs into %s.%s", len(ops), mongo_db_name, coll_name)

        summary = f"🗄️ [{stage.upper()}] 已入库到 {mongo_db_name}.{coll_name}，upsert {len(ops)} 条。"
        logs.append(summary)
        return len(ops), logs

    finally:
        client.close()
