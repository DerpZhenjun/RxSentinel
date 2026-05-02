"""`/api/sentinel/leads` 假集合压测：汇总延迟写 `tests/benchmarks/`。"""
import json
import math
import random
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import sentinel_api


@dataclass
class BenchResult:
    dataset_size: int
    page_size: int
    runs: int
    p50_ms: float
    p95_ms: float
    avg_ms: float
    max_ms: float
    rss_mb_before: float
    rss_mb_after: float
    rss_mb_delta: float


def _get_rss_mb() -> float:
    try:
        import psutil  # type: ignore

        proc = psutil.Process()
        return proc.memory_info().rss / (1024 * 1024)
    except Exception:
        return float("nan")


class _Cursor:
    def __init__(self, docs):
        self.docs = list(docs)

    def sort(self, key, direction):
        reverse = direction == -1
        self.docs.sort(key=lambda x: x.get(key, 0), reverse=reverse)
        return self

    def skip(self, n):
        self.docs = self.docs[n:]
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    def __iter__(self):
        return iter(self.docs)


class _FakeCollection:
    def __init__(self, docs):
        self.docs = list(docs)

    def create_index(self, *args, **kwargs):
        return None

    def find(self, _query, _projection):
        return _Cursor(self.docs)

    def count_documents(self, _query):
        return len(self.docs)

    def bulk_write(self, _ops, ordered=False):
        return SimpleNamespace(modified_count=0)

    def aggregate(self, pipeline):
        rows = [dict(d) for d in self.docs]
        for stage in pipeline:
            if "$match" in stage:
                cond = stage["$match"] or {}
                if "merchant" in cond and isinstance(cond["merchant"], dict) and "$nin" in cond["merchant"]:
                    deny = set(cond["merchant"]["$nin"])
                    rows = [r for r in rows if r.get("merchant") not in deny]
            elif "$sort" in stage:
                for key, direction in reversed(list(stage["$sort"].items())):
                    reverse = direction == -1
                    rows.sort(key=lambda x: x.get(key, 0), reverse=reverse)
            elif "$group" in stage:
                group_spec = stage["$group"]
                gid = group_spec.get("_id")
                if isinstance(gid, dict):
                    grouped = {}
                    for r in rows:
                        key = (
                            r.get("source_platform", "UNKNOWN"),
                            r.get("source_url", ""),
                            r.get("original_content", ""),
                            r.get("platform", "无"),
                            r.get("merchant", "未指明"),
                            r.get("video_title", ""),
                        )
                        if key not in grouped:
                            grouped[key] = {"doc": r}
                    rows = [v for v in grouped.values()]
                else:
                    counter = {}
                    platform_map = {}
                    for r in rows:
                        key = r.get(gid.lstrip("$")) if isinstance(gid, str) and gid.startswith("$") else r.get(gid)
                        counter[key] = counter.get(key, 0) + 1
                        if key not in platform_map:
                            platform_map[key] = r.get("platform", "无")
                    rows = [{"_id": k, "count": v, "platform": platform_map.get(k, "无")} for k, v in counter.items()]
            elif "$replaceRoot" in stage:
                rows = [r.get("doc", r) for r in rows]
            elif "$skip" in stage:
                rows = rows[stage["$skip"] :]
            elif "$limit" in stage:
                rows = rows[: stage["$limit"]]
            elif "$count" in stage:
                rows = [{"total": len(rows)}]
        return iter(rows)


def _make_docs(n: int):
    docs = []
    for i in range(n):
        merchant = f"merchant_{i % 300}"
        platform = ["推特", "Telegram", "微信", "闲鱼", "淘宝"][i % 5]
        source_platform = ["BILI", "WB", "DY", "XHS", "KS"][i % 5]
        docs.append(
            {
                "_id": i + 1,
                "schema_version": "2.0.0",
                "contract": "sentinel_leads.v2",
                "fingerprint": f"fp_{i}",
                "video_title": f"title_{i % 1200}",
                "source_url": f"https://example.com/video/{i}",
                "original_content": f"content_{i % 2000}_{random.randint(1, 9999)}",
                "platform": platform,
                "merchant": merchant,
                "AI_analysis": f"analysis_{i % 500}",
                "source_platform": source_platform,
                "ingested_at": 1_700_000_000 + i,
            }
        )
    return docs


def run_case(dataset_size: int, page_size: int = 500, runs: int = 15) -> BenchResult:
    docs = _make_docs(dataset_size)
    fake_col = _FakeCollection(docs)
    fake_client = SimpleNamespace(close=lambda: None)

    old_get_collection = sentinel_api.get_collection
    sentinel_api.get_collection = lambda: (fake_client, fake_col)  # type: ignore
    try:
        client = TestClient(sentinel_api.app)
        client.get(f"/api/sentinel/leads?page=1&page_size={page_size}")

        rss_before = _get_rss_mb()
        elapsed = []
        for _ in range(runs):
            t0 = time.perf_counter()
            resp = client.get(f"/api/sentinel/leads?page=1&page_size={page_size}")
            if resp.status_code != 200:
                raise RuntimeError(f"unexpected status: {resp.status_code}")
            elapsed.append((time.perf_counter() - t0) * 1000)
        rss_after = _get_rss_mb()
    finally:
        sentinel_api.get_collection = old_get_collection  # type: ignore

    elapsed_sorted = sorted(elapsed)
    p50 = statistics.median(elapsed_sorted)
    p95_idx = max(0, min(len(elapsed_sorted) - 1, math.ceil(len(elapsed_sorted) * 0.95) - 1))
    p95 = elapsed_sorted[p95_idx]
    avg = statistics.mean(elapsed_sorted)
    max_v = max(elapsed_sorted)

    return BenchResult(
        dataset_size=dataset_size,
        page_size=page_size,
        runs=runs,
        p50_ms=round(p50, 2),
        p95_ms=round(p95, 2),
        avg_ms=round(avg, 2),
        max_ms=round(max_v, 2),
        rss_mb_before=round(rss_before, 2),
        rss_mb_after=round(rss_after, 2),
        rss_mb_delta=round((rss_after - rss_before), 2) if not math.isnan(rss_before) and not math.isnan(rss_after) else float("nan"),
    )


def main():
    sizes = [5000, 10000, 50000]
    results = [run_case(s) for s in sizes]
    payload = {
        "generated_at": int(time.time()),
        "endpoint": "/api/sentinel/leads?page=1&page_size=500",
        "results": [r.__dict__ for r in results],
    }
    out_dir = Path("tests/benchmarks")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "backend_benchmark_result.json"
    out_md = out_dir / "BENCHMARK_REPORT.md"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# RxSentinel Benchmark Report",
        "",
        "## Backend API Benchmark",
        "",
        "- endpoint: `/api/sentinel/leads?page=1&page_size=500`",
        f"- generated_at: `{payload['generated_at']}`",
        "",
        "| dataset | runs | p50(ms) | p95(ms) | avg(ms) | max(ms) | rss_before(MB) | rss_after(MB) | rss_delta(MB) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        lines.append(
            f"| {r.dataset_size} | {r.runs} | {r.p50_ms} | {r.p95_ms} | {r.avg_ms} | {r.max_ms} | "
            f"{r.rss_mb_before} | {r.rss_mb_after} | {r.rss_mb_delta} |"
        )

    lines.extend(
        [
            "",
            "## Frontend Benchmark",
            "",
            "- FPS / 首屏加载请执行 `tests/benchmarks/frontend_benchmark.mjs`（需本机已安装 Playwright）。",
        ]
    )
    out_md.write_text("\n".join(lines), encoding="utf-8")

    print(f"backend benchmark done: {out_json}")
    print(f"report updated: {out_md}")


if __name__ == "__main__":
    main()
