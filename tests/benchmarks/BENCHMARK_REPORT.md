# RxSentinel Benchmark Report

## Backend API Benchmark

- endpoint: `/api/sentinel/leads?page=1&page_size=500`
- generated_at: `1777301382`

| dataset | runs | p50(ms) | p95(ms) | avg(ms) | max(ms) | rss_before(MB) | rss_after(MB) | rss_delta(MB) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5000 | 15 | 16.62 | 38.38 | 22.55 | 38.38 | nan | nan | nan |
| 10000 | 15 | 36.93 | 54.53 | 34.04 | 54.53 | nan | nan | nan |
| 50000 | 15 | 170.43 | 183.32 | 171.0 | 183.32 | nan | nan | nan |
