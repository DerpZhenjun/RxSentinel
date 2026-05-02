"""本地 Ollama `/api/generate` 推理入口；输出 JSON 靠 prompt `format` + 正则兜底抽取。

与 DeepSeek 共用 `run_platform_pipeline`，差别仅在 HTTP 客户端形态。"""
import sys
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

import json
import logging
import os
import re
import time
import requests
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

from ai_processor_common import (
    DEFAULT_AI_PROMPT_BODY,
    compose_prompt_template,
    load_prompt_template,
    load_input_lines,
    run_platform_pipeline,
)

@dataclass
class OllamaConfig:
    base_dir: str
    model_name: str
    ollama_url: str
    prompt_template: str
    max_process_count: int | None = None
    read_source: str = "local"
    mongo_uri: str = "mongodb://127.0.0.1:27017"
    mongo_db_name: str = "Oestrogen"


# CLI 直连默认（WebUI 注入覆盖）。
PLATFORMS = ["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"]
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_BASE_DIR = os.path.join(CURRENT_DIR, "data")
_DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"
_DEFAULT_MODEL = "qwen3:8b"


def _wait_for_ollama(base_url: str, timeout: float = 30.0) -> bool:
    """推理前探测：`/api/tags` 连续可达视为进程活着。

    说明：中断残留生成任务时 tags 仍可能 200，但不足以证明推理队列清空；
    此处只做粗粒度连通性门禁，真正的 stall 靠单次请求超时兜。"""
    probe_url = base_url.replace("/api/generate", "").rstrip("/") + "/api/tags"
    deadline = time.monotonic() + timeout
    attempt = 0
    while time.monotonic() < deadline:
        try:
            r = requests.get(probe_url, timeout=3)
            if r.status_code == 200:
                if attempt > 0:
                    logger.info("[Ollama] 已就绪（等待 %.1fs）", time.monotonic() - (deadline - timeout))
                return True
        except Exception:
            pass
        attempt += 1
        time.sleep(2)
    logger.warning("[Ollama] 在 %.0fs 内未能连通 %s，继续尝试推理...", timeout, probe_url)
    return False


def process_platform(platform: str, cfg: OllamaConfig) -> None:
    """单平台 HTTP 推理；`_wait_for_ollama` 先打底，`requests.post` 带全局超时。"""
    input_file = os.path.join(cfg.base_dir, platform, "jsonl", "filtered_comments.jsonl")
    output_file = os.path.join(cfg.base_dir, platform, "jsonl", "ai_extracted_channels.jsonl")
    chart_output_file = os.path.join(cfg.base_dir, platform, "jsonl", "ai_analysis_report.png")
    log_file = os.path.join(cfg.base_dir, platform, "jsonl", "ai_extract_log.txt")

    logger.info("[%s] 开始 Ollama 处理 | 模型: %s", platform.upper(), cfg.model_name)

    # 队列连通性探测：减小上次中断后因残留生成阻塞而导致首轮 POST 长时间无响应的概率。
    _wait_for_ollama(cfg.ollama_url, timeout=30.0)

    try:
        input_lines = load_input_lines(
            platform, input_file,
            cfg.read_source, cfg.mongo_uri, cfg.mongo_db_name,
            cfg.max_process_count,
        )
        if input_lines is None:
            return
    except Exception as e:
        logger.error("[%s] 读取数据出错: %s", platform.upper(), e, exc_info=True)
        return

    # 单次推理封顶等待；队列阻塞时在此处熔断而非无限挂起。
    _OLLAMA_TIMEOUT = 180

    def call_ollama(formatted_prompt: str) -> dict:
        payload = {
            "model": cfg.model_name,
            "prompt": formatted_prompt,
            "stream": False,
            "format": "json",
        }
        response = requests.post(cfg.ollama_url, json=payload, timeout=_OLLAMA_TIMEOUT)
        response.raise_for_status()
        result_text = response.json().get("response", "{}")
        match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if match:
            result_text = match.group(0)
        return json.loads(result_text)

    run_platform_pipeline(
        platform=platform,
        input_lines=input_lines,
        output_file=output_file,
        chart_output_file=chart_output_file,
        log_file=log_file,
        prompt_template=cfg.prompt_template,
        engine="Ollama",
        model_name=cfg.model_name,
        call_llm=call_ollama,
    )


def run_ai_pipeline(model_name, max_count, platforms, base_dir,
                    ollama_url="http://localhost:11434/api/generate",
                    read_source="local", mongo_uri=None, mongo_db=None,
                    custom_prompt=None):
    """组装 `OllamaConfig` 逐平台跑。"""
    prompt_template = (
        compose_prompt_template(custom_prompt)
        if isinstance(custom_prompt, str) and custom_prompt.strip()
        else load_prompt_template(DEFAULT_AI_PROMPT_BODY)
    )
    cfg = OllamaConfig(
        base_dir=os.path.join(base_dir, "ProcessCdata", "data"),
        model_name=model_name,
        ollama_url=ollama_url,
        prompt_template=prompt_template,
        max_process_count=max_count if max_count > 0 else None,
        read_source=read_source,
        mongo_uri=mongo_uri or "mongodb://127.0.0.1:27017",
        mongo_db_name=mongo_db or "Oestrogen",
    )
    for plat in platforms:
        process_platform(plat, cfg)

    return f"✅ Ollama 提取任务完成！(模型: {model_name})，请前往界面或输出目录查看分析图表。"


if __name__ == "__main__":
    import argparse as _ap

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    _p = _ap.ArgumentParser(description="Ollama 多平台 AI 分析流水线（供 WebUI 以子进程方式调用）")
    _p.add_argument("--root-dir",    default=os.path.dirname(CURRENT_DIR),
                    help="项目根目录（包含 ProcessCdata、MediaCrawler 等子目录）")
    _p.add_argument("--platforms",   nargs="+", default=PLATFORMS,   help="要处理的平台列表")
    _p.add_argument("--model",       default=_DEFAULT_MODEL,         help="Ollama 模型名称")
    _p.add_argument("--max-count",   type=int, default=0,            help="分析条数上限，0 为全量")
    _p.add_argument("--ollama-url",  default=_DEFAULT_OLLAMA_URL,    help="Ollama API 地址")
    _p.add_argument("--read-source", default="local", choices=["local", "db"], help="数据读取源")
    _p.add_argument("--mongo-uri",   default="mongodb://127.0.0.1:27017")
    _p.add_argument("--mongo-db",    default="Oestrogen")
    _args = _p.parse_args()

    logger.info("启动 Ollama 多平台批处理系统 | 模型: %s | 平台: %s", _args.model, _args.platforms)
    result = run_ai_pipeline(
        model_name=_args.model,
        max_count=_args.max_count,
        platforms=_args.platforms,
        base_dir=_args.root_dir,
        ollama_url=_args.ollama_url,
        read_source=_args.read_source,
        mongo_uri=_args.mongo_uri,
        mongo_db=_args.mongo_db,
        custom_prompt=None,  # `None` → 读 `ai_prompt_config.json`（WebUI 可先保存）
    )
    print(result)
    logger.info("所有平台的 Ollama 挖掘任务执行完毕")
