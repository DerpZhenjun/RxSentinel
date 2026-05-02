"""
start.py — RxSentinel 统一启动器

用法：
    python start.py               # 启动全套（WebUI + API + 前端）
    python start.py --no-frontend # 仅启动 WebUI + API
    python start.py --no-api      # 仅启动 WebUI（API 由 WebUI 内自动拉起）
    python start.py --api-only    # 仅启动后台 API（不启动 WebUI）

启动顺序：
    1. Sentinel FastAPI  → http://127.0.0.1:8000
    2. Vue 前端 dev server → http://localhost:5173  （--no-frontend 跳过）
    3. Streamlit WebUI   → http://localhost:8501   （--api-only 跳过，阻塞运行）

WebUI 退出（Ctrl+C）时，所有后台子进程自动清理。
"""

import argparse
import os
import subprocess
import sys
import time

import requests

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
RXSERVER_DIR = os.path.join(ROOT_DIR, "RxServer")
SENTINEL_API = os.path.join(RXSERVER_DIR, "sentinel_api.py")
WEBUI = os.path.join(RXSERVER_DIR, "webui.py")
DASHBOARD_DIR = os.path.join(ROOT_DIR, "SentinelDashboard")

API_HOST = "127.0.0.1"
API_PORT = 8000
WEBUI_PORT = 8501
FRONTEND_PORT = 5173


# ---------------------------------------------------------------------------
# 辅助：检查端口是否已有服务
# ---------------------------------------------------------------------------

def _probe_http(url: str, timeout: float = 1.5) -> bool:
    try:
        return requests.get(url, timeout=timeout).ok
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 各服务启动函数
# ---------------------------------------------------------------------------

def start_api(background_procs: list) -> bool:
    """启动 Sentinel FastAPI；若已在线则跳过。返回是否成功在线。"""
    ping_url   = f"http://{API_HOST}:{API_PORT}/ping"
    health_url = f"http://{API_HOST}:{API_PORT}/api/health"

    if _probe_http(ping_url):
        print(f"[RxSentinel] ✅ Sentinel API already online  →  {health_url}")
        return True

    if not os.path.exists(SENTINEL_API):
        print(f"[RxSentinel] ⚠️  sentinel_api.py not found: {SENTINEL_API}")
        return False

    print(f"[RxSentinel] 🚀 Starting Sentinel API on :{API_PORT} ...")
    log_path = os.path.join(ROOT_DIR, "sentinel_api.log")
    log_file = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, SENTINEL_API, "--host", API_HOST, "--port", str(API_PORT)],
        cwd=ROOT_DIR,
        stdout=log_file,
        stderr=log_file,
    )
    background_procs.append(proc)

    # 等待 API 就绪（最多 20 秒）；用 /ping 探测，不依赖 MongoDB
    for i in range(20):
        time.sleep(1)
        if proc.poll() is not None:
            log_file.flush()
            print(f"[RxSentinel] ✖  Sentinel API process exited early (code {proc.returncode}).")
            print(f"[RxSentinel]    Check log for details: {log_path}")
            return False
        if _probe_http(ping_url):
            print(f"[RxSentinel] ✅ Sentinel API ready       →  {health_url}")
            return True

    print(f"[RxSentinel] ⚠️  Sentinel API did not respond within 20s.")
    print(f"[RxSentinel]    Check log for details: {log_path}")
    return False


def start_frontend(background_procs: list) -> None:
    """后台启动 Vue dev server（需要 Node.js + npm）。"""
    if _probe_http(f"http://localhost:{FRONTEND_PORT}"):
        print(f"[RxSentinel] ✅ Vue frontend already online →  http://localhost:{FRONTEND_PORT}")
        return

    if not os.path.exists(DASHBOARD_DIR):
        print(f"[RxSentinel] ⚠️  SentinelDashboard dir not found: {DASHBOARD_DIR}")
        return

    print(f"[RxSentinel] 🚀 Starting Vue frontend on :{FRONTEND_PORT} ...")
    proc = subprocess.Popen(
        "npm run dev",
        cwd=DASHBOARD_DIR,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    background_procs.append(proc)
    time.sleep(2)
    print(f"[RxSentinel] 🌐 Vue frontend →  http://localhost:{FRONTEND_PORT}")


def start_webui() -> None:
    """前台启动 Streamlit WebUI（阻塞直到用户 Ctrl+C）。"""
    print(f"[RxSentinel] 🚀 Starting WebUI on :{WEBUI_PORT} ...")
    print(f"[RxSentinel] 🌐 WebUI        →  http://localhost:{WEBUI_PORT}")
    print()
    subprocess.run(
        [
            sys.executable, "-m", "streamlit", "run", WEBUI,
            "--server.port", str(WEBUI_PORT),
            "--server.headless", "true",
        ],
        cwd=ROOT_DIR,
    )


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="RxSentinel unified launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--no-api",      action="store_true", help="Skip starting Sentinel API")
    parser.add_argument("--no-frontend", action="store_true", help="Skip starting Vue frontend")
    parser.add_argument("--api-only",    action="store_true", help="Start only the Sentinel API (no WebUI)")
    args = parser.parse_args()

    background_procs: list[subprocess.Popen] = []

    print()
    print("══════════════════════════════════════════")
    print("  RxSentinel — Unified Launcher")
    print("══════════════════════════════════════════")

    try:
        if not args.no_api:
            start_api(background_procs)

        if not args.no_frontend and not args.api_only:
            start_frontend(background_procs)

        if args.api_only:
            print("[RxSentinel] Running in API-only mode. Press Ctrl+C to stop.")
            while True:
                time.sleep(5)
        else:
            start_webui()  # blocking

    except KeyboardInterrupt:
        print("\n[RxSentinel] Shutting down ...")
    finally:
        for proc in background_procs:
            try:
                proc.terminate()
            except Exception:
                pass
        print("[RxSentinel] All background processes stopped. Goodbye.")


if __name__ == "__main__":
    main()
