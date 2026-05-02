# Benchmark Suite

## Backend (5k / 10k / 50k)

```bash
python tests/benchmarks/backend_benchmark.py
```

Outputs:

- `tests/benchmarks/backend_benchmark_result.json`
- `tests/benchmarks/BENCHMARK_REPORT.md`

Metrics:

- `/api/sentinel/leads` p50/p95/avg/max latency (ms)
- process RSS before/after/delta (MB)
